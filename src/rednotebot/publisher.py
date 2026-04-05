from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from .parser import NoteContent


@dataclass(frozen=True, slots=True)
class SelectorSet:
    login_button: str = 'button:has-text("登录")'
    new_note_button: str = 'button:has-text("发布笔记"), a:has-text("发布笔记"), div:has-text("发布笔记")'
    title_input: str = 'input[placeholder*="标题"], textarea[placeholder*="标题"]'
    body_editor: str = '[contenteditable="true"], textarea[placeholder*="正文"]'
    image_input: str = 'input[type="file"][accept*="image"], input[type="file"]'
    publish_button: str = 'button:has-text("发布"), button:has-text("立即发布")'
    tag_suggestion: str = '[class*="tag"]'
    publish_success_hint: str = 'text=发布成功'


DEFAULT_SELECTORS = SelectorSet()


def selector_reference_markdown(selectors: SelectorSet = DEFAULT_SELECTORS) -> str:
    rows = [
        ("login_button", selectors.login_button, "登录入口，Cookie 失效时需要人工扫码"),
        ("new_note_button", selectors.new_note_button, "进入新建笔记页面"),
        ("title_input", selectors.title_input, "标题输入框"),
        ("body_editor", selectors.body_editor, "正文编辑区域"),
        ("image_input", selectors.image_input, "图片上传 input"),
        ("publish_button", selectors.publish_button, "发布按钮"),
        ("tag_suggestion", selectors.tag_suggestion, "标签建议项，可选"),
        ("publish_success_hint", selectors.publish_success_hint, "发布完成提示"),
    ]
    lines = [
        "| 变量名 | 默认选择器 | 说明 |",
        "| --- | --- | --- |",
    ]
    for name, selector, desc in rows:
        lines.append(f"| `{name}` | `{selector}` | {desc} |")
    return "\n".join(lines)


class XhsPublisher:
    def __init__(
        self,
        selectors: SelectorSet = DEFAULT_SELECTORS,
        cookies_path: str | Path | None = None,
        headless: bool = False,
        slow_mo_ms: int = 0,
        timeout_ms: int = 15_000,
    ) -> None:
        self.selectors = selectors
        self.cookies_path = Path(cookies_path).expanduser().resolve() if cookies_path else None
        self.headless = headless
        self.slow_mo_ms = slow_mo_ms
        self.timeout_ms = timeout_ms

    def publish(self, note: NoteContent) -> None:
        _ensure_images_exist(note.images)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless, slow_mo=self.slow_mo_ms)
            context = browser.new_context()
            context.set_default_timeout(self.timeout_ms)
            if self.cookies_path:
                self._load_cookies(context)

            page = context.new_page()
            self._open_home(page)
            self._ensure_login(page)
            self._open_editor(page)
            self._fill_form(page, note)
            self._submit(page)

            if self.cookies_path:
                self._save_cookies(context)
            browser.close()

    def _open_home(self, page: Page) -> None:
        page.goto("https://creator.xiaohongshu.com/publish/publish", wait_until="domcontentloaded")

    def _ensure_login(self, page: Page) -> None:
        try:
            page.wait_for_selector(self.selectors.new_note_button, timeout=8_000)
            return
        except PlaywrightTimeoutError:
            pass

        try:
            page.click(self.selectors.login_button, timeout=3_000)
        except PlaywrightTimeoutError:
            pass

        print("未检测到已登录态，请在浏览器中完成登录。")
        page.wait_for_selector(self.selectors.new_note_button, timeout=120_000)

    def _open_editor(self, page: Page) -> None:
        page.goto("https://creator.xiaohongshu.com/publish/publish", wait_until="domcontentloaded")
        page.wait_for_selector(self.selectors.title_input)

    def _fill_form(self, page: Page, note: NoteContent) -> None:
        title_input = page.locator(self.selectors.title_input).first
        title_input.fill(note.title)

        editor = page.locator(self.selectors.body_editor).first
        editor.click()
        editor.fill(note.body)

        if note.images:
            page.locator(self.selectors.image_input).first.set_input_files([str(path) for path in note.images])
            self._wait_for_upload_settle(page)

        if note.tags:
            editor.press("End")
            for tag in note.tags:
                editor.type(f" {tag}")
                page.wait_for_timeout(500)
                self._confirm_tag(page, tag)

    def _submit(self, page: Page) -> None:
        page.locator(self.selectors.publish_button).first.click()
        try:
            page.wait_for_selector(self.selectors.publish_success_hint, timeout=20_000)
        except PlaywrightTimeoutError:
            print("未捕获到明确的发布成功提示，请人工确认页面状态。")

    def _confirm_tag(self, page: Page, tag: str) -> None:
        suggestions = page.locator(self.selectors.tag_suggestion)
        if suggestions.count() > 0:
            try:
                suggestions.filter(has_text=tag.lstrip("#")).first.click(timeout=1_500)
                return
            except PlaywrightTimeoutError:
                pass
        page.keyboard.press("Enter")

    def _wait_for_upload_settle(self, page: Page) -> None:
        page.wait_for_timeout(2_000)
        for _ in range(20):
            pending = page.locator('text=/上传中|处理中|封面生成中/')
            if pending.count() == 0:
                return
            page.wait_for_timeout(1_000)

    def _load_cookies(self, context: Any) -> None:
        if not self.cookies_path or not self.cookies_path.exists():
            return
        cookies = json.loads(self.cookies_path.read_text(encoding="utf-8"))
        if cookies:
            context.add_cookies(cookies)

    def _save_cookies(self, context: Any) -> None:
        if not self.cookies_path:
            return
        self.cookies_path.write_text(
            json.dumps(context.cookies(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _ensure_images_exist(images: list[Path]) -> None:
    missing = [str(path) for path in images if not path.exists()]
    if missing:
        joined = "\n".join(missing)
        raise FileNotFoundError(f"以下图片不存在：\n{joined}")
