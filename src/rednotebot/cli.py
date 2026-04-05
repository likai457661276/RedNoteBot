from __future__ import annotations

import argparse
from pathlib import Path

from .parser import parse_markdown_note
from .publisher import DEFAULT_SELECTORS, DEFAULT_LOGIN_URL, XhsPublisher, page_feature_markdown, selector_reference_markdown


def build_parser() -> argparse.ArgumentParser:
    """
    构建命令行参数解析器。
    
    定义了以下主要参数：
    - note: Markdown 笔记的路径。
    - --storage-state: 存储登录态的 Playwright state 文件路径。
    - --login: 仅执行人工扫码登录并保存状态。
    - --confirm-publish: 显式确认真正提交发布。
    - --stop-before-publish: 跑到发布确认页后停止，不真正提交。
    - --startup-delay-min / --startup-delay-max: 发布前的随机延迟分钟数。
    - --inspect-page: 用于采集页面特征，排查选择器失效问题。
    """
    parser = argparse.ArgumentParser(description="根据 Markdown 模板自动发布小红书笔记")
    parser.add_argument("note", nargs="?", default="notes/sample_note.md", help="Markdown 笔记路径")
    parser.add_argument("--storage-state", default="playwright-state.json", help="Playwright storage_state 文件路径")
    parser.add_argument("--timeout", type=int, default=15_000, help="Playwright 默认超时毫秒数")
    parser.add_argument("--login", action="store_true", help="打开浏览器手动扫码登录并保存 storage_state")
    parser.add_argument("--login-url", default=DEFAULT_LOGIN_URL, help="手动登录时打开的地址")
    parser.add_argument("--login-wait", type=int, default=180, help="手动登录最大等待秒数")
    parser.add_argument("--confirm-publish", action="store_true", help="显式确认真正点击发布按钮")
    parser.add_argument("--stop-before-publish", action="store_true", help="跑到发布确认页后停止，不真正点击发布")
    parser.add_argument("--startup-delay-min", type=int, default=0, help="发布前最小随机等待分钟数")
    parser.add_argument("--startup-delay-max", type=int, default=0, help="发布前最大随机等待分钟数")
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
    2. 根据参数选择执行：打印选择器、登录初始化、采集页面特征 或 执行发布流程。
    """
    parser = build_parser()
    args = parser.parse_args()

    if args.startup_delay_min > args.startup_delay_max:
        parser.error("--startup-delay-min 不能大于 --startup-delay-max")
    if args.confirm_publish and args.stop_before_publish:
        parser.error("--confirm-publish 与 --stop-before-publish 不能同时使用")

    if args.print_selectors:
        print(selector_reference_markdown(DEFAULT_SELECTORS))
        return

    publisher = XhsPublisher(
        selectors=DEFAULT_SELECTORS,
        storage_state_path=args.storage_state,
        timeout_ms=args.timeout,
        launch_delay_range=(args.startup_delay_min, args.startup_delay_max),
    )

    if args.login:
        publisher.login_and_save_state(login_url=args.login_url, wait_timeout_ms=args.login_wait * 1000)
        return

    if args.inspect_page:
        report = publisher.inspect_page(args.feature_url)
        output_path = Path(args.feature_output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(page_feature_markdown(report), encoding="utf-8")
        print(f"页面特征已写入：{output_path}")
        return

    note = parse_markdown_note(Path(args.note))
    stop_before_publish = args.stop_before_publish or not args.confirm_publish
    publisher.publish_note(note, stop_before_publish=stop_before_publish)


if __name__ == "__main__":
    main()
