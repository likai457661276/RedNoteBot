from __future__ import annotations

import argparse
from pathlib import Path

from .parser import parse_markdown_note
from .publisher import DEFAULT_SELECTORS, XhsPublisher, page_feature_markdown, selector_reference_markdown


def build_parser() -> argparse.ArgumentParser:
    """
    构建命令行参数解析器。
    
    定义了以下主要参数：
    - note: Markdown 笔记的路径。
    - --cookies: 存储登录态的 JSON 文件路径。
    - --headless: 是否使用无头模式运行（生产环境建议开启）。
    - --slow-mo: 步骤间的延迟，用于调试时观察。
    - --inspect-page: 用于采集页面特征，排查选择器失效问题。
    """
    parser = argparse.ArgumentParser(description="根据 Markdown 模板自动发布小红书笔记")
    parser.add_argument("note", nargs="?", default="notes/sample_note.md", help="Markdown 笔记路径")
    parser.add_argument("--cookies", default="playwright-state.json", help="Cookie JSON 文件路径")
    parser.add_argument("--headless", action="store_true", help="使用无头浏览器执行")
    parser.add_argument("--slow-mo", type=int, default=300, help="浏览器每步操作的延迟毫秒数")
    parser.add_argument("--timeout", type=int, default=15_000, help="Playwright 默认超时毫秒数")
    parser.add_argument("--print-selectors", action="store_true", help="打印当前使用的选择器表")
    parser.add_argument("--inspect-page", action="store_true", help="打开页面并导出当前动作元素特征表")
    parser.add_argument(
        "--feature-url",
        default="https://creator.xiaohongshu.com/publish/publish",
        help="采集页面特征时使用的 URL",
    )
    parser.add_argument(
        "--feature-output",
        default="docs/xhs-page-features.md",
        help="页面特征 Markdown 输出路径",
    )
    return parser


def main() -> None:
    """
    CLI 程序入口。
    
    负责：
    1. 解析命令行参数。
    2. 根据参数选择执行：打印选择器、采集页面特征 或 执行发布流程。
    """
    parser = build_parser()
    args = parser.parse_args()

    if args.print_selectors:
        print(selector_reference_markdown(DEFAULT_SELECTORS))
        return

    publisher = XhsPublisher(
        selectors=DEFAULT_SELECTORS,
        cookies_path=args.cookies,
        headless=args.headless,
        slow_mo_ms=args.slow_mo,
        timeout_ms=args.timeout,
    )

    if args.inspect_page:
        report = publisher.inspect_page(args.feature_url)
        output_path = Path(args.feature_output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(page_feature_markdown(report), encoding="utf-8")
        print(f"页面特征已写入：{output_path}")
        return

    note = parse_markdown_note(Path(args.note))
    publisher.publish(note)


if __name__ == "__main__":
    main()
