from __future__ import annotations

import argparse
from pathlib import Path

from .parser import parse_markdown_note
from .publisher import DEFAULT_SELECTORS, XhsPublisher, selector_reference_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="根据 Markdown 模板自动发布小红书笔记")
    parser.add_argument("note", nargs="?", default="notes/sample_note.md", help="Markdown 笔记路径")
    parser.add_argument("--cookies", default="playwright-state.json", help="Cookie JSON 文件路径")
    parser.add_argument("--headless", action="store_true", help="使用无头浏览器执行")
    parser.add_argument("--slow-mo", type=int, default=300, help="浏览器每步操作的延迟毫秒数")
    parser.add_argument("--timeout", type=int, default=15_000, help="Playwright 默认超时毫秒数")
    parser.add_argument("--print-selectors", action="store_true", help="打印当前使用的选择器表")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.print_selectors:
        print(selector_reference_markdown(DEFAULT_SELECTORS))
        return

    note = parse_markdown_note(Path(args.note))
    publisher = XhsPublisher(
        selectors=DEFAULT_SELECTORS,
        cookies_path=args.cookies,
        headless=args.headless,
        slow_mo_ms=args.slow_mo,
        timeout_ms=args.timeout,
    )
    publisher.publish(note)


if __name__ == "__main__":
    main()
