from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from .parser import NoteContent


PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"


@dataclass(frozen=True, slots=True)
class SelectorSet:
    """
    存储小红书页面各组件的选择器集合。
    """
    login_button: str = 'button:has-text("登录"), text=APP扫一扫登录, text=扫码登录'
    long_article_entry: str = '.creator-tab:has-text("写长文"), span.title:has-text("写长文"), text=写长文'
    new_article_button: str = '.new-btn, button:has-text("新的创作"), text=新的创作'
    title_input: str = 'textarea[placeholder*="输入标题"], input[placeholder*="标题"], textarea[placeholder*="标题"]'
    body_editor: str = '[contenteditable="true"], textarea[placeholder*="正文"]'
    image_input: str = 'input[type="file"][accept*="image"], input[type="file"]'
    publish_button: str = 'button:has-text("发布"), button:has-text("立即发布"), [role="button"]:has-text("发布")'
    format_button: str = '.next-btn, button:has-text("一键排版")'
    next_step_button: str = 'button:has-text("下一步")'
    tag_suggestion: str = '[class*="tag"], [class*="mention"], [class*="suggest"]'
    publish_success_hint: str = "text=/发布成功|笔记发布成功|发布完成/"


@dataclass(frozen=True, slots=True)
class SceneSpec:
    """
    定义页面场景及其识别特征。
    """
    scene_name: str
    label: str
    detectors: tuple[str, ...]
    description: str


@dataclass(frozen=True, slots=True)
class SelectorSpec:
    """
    定义特定动作对应的选择器规格。
    """
    field_name: str
    scene_name: str
    action_name: str
    selectors: tuple[str, ...]
    description: str


@dataclass(frozen=True, slots=True)
class PageFeature:
    """
    存储单个页面元素的特征信息，用于调试。
    """
    scene_name: str
    action_name: str
    field_name: str
    candidates: tuple[str, ...]
    matched_selector: str
    description: str
    match_count: int
    first_tag: str
    first_text: str


@dataclass(frozen=True, slots=True)
class PageFeatureReport:
    """
    页面特征采集报告。
    """
    requested_url: str
    final_url: str
    page_title: str
    detected_scene: str
    features: tuple[PageFeature, ...]


SCENE_SPECS = (
    SceneSpec(
        "publish_result",
        "发布结果页",
        ("text=发布成功", "text=笔记发布成功", "text=查看笔记"),
        "表单已经提交，页面处于结果确认态。",
    ),
    SceneSpec(
        "article_hub",
        "长文创作入口页",
        ('.new-btn', 'button:has-text("新的创作")', '.import-link-btn'),
        "已进入长文入口，但还需要新建一篇长文。",
    ),
    SceneSpec(
        "editor",
        "长文编辑页",
        ('textarea[placeholder*="输入标题"]', '.next-btn', '[contenteditable="true"]'),
        "可以直接填写长文标题、正文并上传图片。",
    ),
    SceneSpec(
        "login",
        "登录页",
        ("text=APP扫一扫登录", "text=扫码登录", 'button:has-text("登录")'),
        "需要人工扫码或账号登录。",
    ),
    SceneSpec(
        "studio_home",
        "创作平台导航页",
        ('.creator-tab', '.upload-input', "text=发布笔记"),
        "已进入创作平台，但还未进入长文编辑器。",
    ),
)

SELECTOR_SPECS = (
    SelectorSpec(
        "login_button",
        "login",
        "触发登录",
        ('button:has-text("登录")', 'text=APP扫一扫登录', 'text=扫码登录'),
        "登录入口，Cookie 失效时需要人工扫码。",
    ),
    SelectorSpec(
        "long_article_entry",
        "studio_home",
        "进入长文创作入口",
        ('.creator-tab:has-text("写长文")', 'span.title:has-text("写长文")', "text=写长文"),
        "从导航页进入长文创作流。",
    ),
    SelectorSpec(
        "new_article_button",
        "article_hub",
        "新建长文",
        ('.new-btn', 'button:has-text("新的创作")', "text=新的创作"),
        "在长文入口页创建一篇新的长文。",
    ),
    SelectorSpec(
        "title_input",
        "editor",
        "填写标题",
        ('textarea[placeholder*="输入标题"]', 'input[placeholder*="标题"]', 'textarea[placeholder*="标题"]'),
        "标题输入框。",
    ),
    SelectorSpec(
        "body_editor",
        "editor",
        "填写正文",
        ('[contenteditable="true"]', 'textarea[placeholder*="正文"]'),
        "正文编辑区域。",
    ),
    SelectorSpec(
        "image_input",
        "editor",
        "上传图片",
        ('input[type="file"][accept*="image"]', 'input[type="file"]'),
        "图片上传 input。",
    ),
    SelectorSpec(
        "publish_button",
        "publish_result",
        "提交发布",
        ('button:has-text("立即发布")', 'button:has-text("发布")', '[role="button"]:has-text("发布")'),
        "发布按钮。",
    ),
    SelectorSpec(
        "format_button",
        "editor",
        "生成排版预览",
        ('.next-btn', 'button:has-text("一键排版")'),
        "将长文内容生成图片化排版。",
    ),
    SelectorSpec(
        "next_step_button",
        "publish_result",
        "进入发布确认页",
        ('button:has-text("下一步")',),
        "完成排版后进入最终发布确认页。",
    ),
    SelectorSpec(
        "tag_suggestion",
        "editor",
        "确认标签联想",
        ('[class*="tag"]', '[class*="suggest"]', '[class*="mention"]'),
        "标签建议项，可选。",
    ),
    SelectorSpec(
        "publish_success_hint",
        "publish_result",
        "识别发布成功",
        ("text=发布成功", "text=笔记发布成功", "text=发布完成"),
        "发布完成提示。",
    ),
)

DEFAULT_SELECTORS = SelectorSet(**{spec.field_name: ", ".join(spec.selectors) for spec in SELECTOR_SPECS})


def selector_reference_markdown(selectors: SelectorSet = DEFAULT_SELECTORS) -> str:
    lines = [
        "| 场景 | 动作 | 变量名 | 默认选择器 | 说明 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for spec in SELECTOR_SPECS:
        selector = getattr(selectors, spec.field_name)
        scene_label = _scene_label(spec.scene_name)
        lines.append(f"| {scene_label} | {spec.action_name} | `{spec.field_name}` | `{selector}` | {spec.description} |")
    return "\n".join(lines)


def page_feature_markdown(report: PageFeatureReport) -> str:
    lines = [
        "# 小红书页面特征表",
        "",
        f"- 请求地址：`{report.requested_url}`",
        f"- 最终地址：`{report.final_url}`",
        f"- 页面标题：`{report.page_title}`",
        f"- 当前场景：`{_scene_label(report.detected_scene)}`",
        "",
        "## 场景检测",
        "",
        "| 场景 | 说明 |",
        "| --- | --- |",
    ]
    for scene in SCENE_SPECS:
        lines.append(f"| {scene.label} | {scene.description} |")

    lines.extend(
        [
            "",
            "## 动作元素映射",
            "",
            "| 场景 | 动作 | 变量名 | 候选选择器 | 命中选择器 | 命中数 | 首个标签 | 首个文本 | 说明 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for feature in report.features:
        lines.append(
            "| {scene} | {action} | `{field}` | `{candidates}` | `{matched}` | {count} | `{tag}` | {text} | {desc} |".format(
                scene=_scene_label(feature.scene_name),
                action=feature.action_name,
                field=feature.field_name,
                candidates=_markdown_cell(" | ".join(feature.candidates)),
                matched=_markdown_cell(feature.matched_selector or "-"),
                count=feature.match_count,
                tag=_markdown_cell(feature.first_tag or "-"),
                text=_markdown_cell(feature.first_text or "-"),
                desc=feature.description,
            )
        )
    return "\n".join(lines)


class XhsPublisher:
    """
    负责执行小红书笔记发布流程。
    
    使用 Playwright 驱动浏览器完成登录检查、进入编辑器、填写内容、排版和发布动作。
    """
    def __init__(
        self,
        selectors: SelectorSet = DEFAULT_SELECTORS,
        cookies_path: str | Path | None = None,
        headless: bool = False,
        slow_mo_ms: int = 0,
        timeout_ms: int = 15_000,
    ) -> None:
        """
        初始化发布器。
        
        Args:
            selectors: 选择器配置。
            cookies_path: Playwright 状态文件路径（用于保持登录态）。
            headless: 是否以无头模式运行浏览器。
            slow_mo_ms: 操作延迟（毫秒），便于观察。
            timeout_ms: 默认等待超时（毫秒）。
        """
        self.selectors = selectors
        self.cookies_path = Path(cookies_path).expanduser().resolve() if cookies_path else None
        self.headless = headless
        self.slow_mo_ms = slow_mo_ms
        self.timeout_ms = timeout_ms

    def publish(self, note: NoteContent) -> None:
        """
        发布一篇笔记。
        
        流程包括：
        1. 启动浏览器并加载登录态。
        2. 打开创作平台主页。
        3. 确保已登录（若未登录则提示人工扫码）。
        4. 进入长文编辑器。
        5. 填写标题、正文和上传图片。
        6. 执行排版并提交发布。
        7. 保存最新的登录态。
        """
        _ensure_images_exist(note.images)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless, slow_mo=self.slow_mo_ms)
            context = self._create_context(browser)
            context.set_default_timeout(self.timeout_ms)

            page = context.new_page()
            self._log(f"开始发布：{note.title}")
            self._open_home(page)
            self._ensure_login(page)
            self._open_editor(page)
            self._fill_form(page, note)
            self._submit(page, note)
            self._log(f"发布流程结束，当前页面：{page.url}")

            if self.cookies_path:
                self._save_cookies(context)
            browser.close()

    def inspect_page(self, url: str = PUBLISH_URL) -> PageFeatureReport:
        """
        采集指定页面的特征，用于排查选择器失效或页面结构变化。
        """
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless, slow_mo=self.slow_mo_ms)
            context = self._create_context(browser)
            context.set_default_timeout(self.timeout_ms)

            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2_000)

            features = tuple(self._collect_page_features(page))
            report = PageFeatureReport(
                requested_url=url,
                final_url=page.url,
                page_title=page.title(),
                detected_scene=self._detect_scene(page),
                features=features,
            )

            if self.cookies_path:
                self._save_cookies(context)
            browser.close()
            return report

    def _open_home(self, page: Page) -> None:
        """打开发布主页。"""
        self._log(f"打开发布页：{PUBLISH_URL}")
        page.goto(PUBLISH_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1_500)

    def _ensure_login(self, page: Page) -> None:
        """
        检查并确保已登录。如果处于登录页，会等待用户手动完成扫码。
        """
        scene = self._detect_scene(page)
        if scene != "login":
            return

        self._click_action_if_found(page, "login_button")
        self._log("当前处于登录页，请在浏览器中完成登录。")
        # 默认等待 120 秒让人工扫码登录
        self._wait_for_scene(page, ("studio_home", "editor"), timeout_ms=120_000)
        self._log(f"登录完成，当前场景：{_scene_label(self._detect_scene(page))}")

    def _open_editor(self, page: Page) -> None:
        """
        从当前页面导航到长文编辑页。
        """
        scene = self._detect_scene(page)
        if scene == "editor":
            self._log("已在长文编辑页。")
            return

        page.goto(PUBLISH_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1_500)

        scene = self._detect_scene(page)
        if scene == "editor":
            self._log("刷新后已进入长文编辑页。")
            return
        if scene == "login":
            raise RuntimeError("仍停留在登录页，无法进入长文编辑器。请先完成登录。")

        self._log(f"准备进入长文入口，当前场景：{_scene_label(scene)}")
        self._click_action_if_found(page, "long_article_entry")
        page.wait_for_timeout(1_500)

        scene = self._wait_for_scene(page, ("article_hub", "editor"), timeout_ms=30_000)
        if scene == "article_hub":
            self._log("已进入长文入口页，准备点击“新的创作”。")
            self._require_locator(page, "new_article_button").click()
            self._wait_for_scene(page, ("editor",), timeout_ms=30_000)
        self._log("已进入长文编辑页。")

    def _fill_form(self, page: Page, note: NoteContent) -> None:
        """
        在编辑器中填写标题、正文并上传图片。
        """
        self._log("开始填写标题和正文。")
        title_input = self._require_locator(page, "title_input")
        title_input.fill(note.title)

        editor = self._require_locator(page, "body_editor")
        editor.click()
        editor.fill(note.body)

        if note.images:
            self._log(f"开始上传图片，共 {len(note.images)} 张。")
            self._require_locator(page, "image_input").set_input_files([str(path) for path in note.images])
            self._wait_for_upload_settle(page)
        self._log("内容填写完成。")

    def _submit(self, page: Page, note: NoteContent) -> None:
        """
        执行排版、补充标签/话题并最终发布。
        """
        self._log("开始排版。")
        self._require_locator(page, "format_button").click()
        self._wait_for_action(page, "next_step_button", timeout_ms=30_000)
        self._log("进入发布确认页。")
        self._require_locator(page, "next_step_button").click()
        page.wait_for_timeout(1_500)
        self._fill_publish_description(page, note)
        self._wait_for_action(page, "publish_button", timeout_ms=30_000)
        self._log("点击发布按钮。")
        self._require_locator(page, "publish_button").click()
        try:
            self._wait_for_scene(page, ("publish_result",), timeout_ms=20_000)
            self._log(f"检测到发布成功结果页：{page.url}")
        except PlaywrightTimeoutError:
            self._log(f"未捕获到明确的发布成功结果页，请人工确认页面状态：{page.url}")

    def _confirm_tag(self, page: Page, tag: str) -> None:
        """处理标签输入后的自动建议确认。"""
        suggestions = self._find_first_matching_locator(page, "tag_suggestion")
        if suggestions is not None:
            try:
                suggestions.filter(has_text=tag.lstrip("#")).first.click(timeout=1_500)
                return
            except PlaywrightTimeoutError:
                pass
        page.keyboard.press("Enter")

    def _wait_for_upload_settle(self, page: Page) -> None:
        """等待所有图片上传和处理完成。"""
        page.wait_for_timeout(2_000)
        for _ in range(20):
            pending = page.locator('text=/上传中|处理中|封面生成中/')
            if pending.count() == 0:
                return
            page.wait_for_timeout(1_000)

    def _fill_publish_description(self, page: Page, note: NoteContent) -> None:
        """
        在发布确认页补充笔记标签和参与话题。
        """
        editor = self._require_locator(page, "body_editor")
        editor.click()
        if note.tags:
            self._log(f"补充标签：{' '.join(note.tags)}")
            editor.press("End")
            for tag in note.tags:
                editor.type(f"{tag} ")
                page.wait_for_timeout(500)
                self._confirm_tag(page, tag)
        if note.topics:
            self._log(f"补充话题：{' '.join(note.topics)}")
            editor.press("End")
            for topic in note.topics:
                normalized = topic.strip().lstrip("#").strip()
                if not normalized:
                    continue
                editor.type(f"#{normalized} ")
                page.wait_for_timeout(500)
                self._confirm_tag(page, f"#{normalized}")

    def _apply_topics(self, page: Page, topics: list[str]) -> None:
        """
        尝试在页面中查找并点击指定的话题。
        """
        for topic in topics:
            normalized = topic.strip().lstrip("#").strip()
            if not normalized:
                continue
            if self._is_topic_added(page, normalized):
                continue
            if not self._click_topic_add_button(page, normalized):
                print(f"未找到活动话题“{normalized}”对应的添加入口，请人工确认页面候选项。")
                continue
            page.wait_for_timeout(1_000)
            if not self._is_topic_added(page, normalized):
                print(f"活动话题“{normalized}”点击后未确认写入，请人工检查页面状态。")

    def _is_topic_added(self, page: Page, topic: str) -> bool:
        """
        检查话题是否已被添加。
        """
        escaped = re.escape(topic)
        indicators = (
            f'text=/已添加.*{escaped}|{escaped}.*已添加/',
            f'text=/已参与.*{escaped}|{escaped}.*已参与/',
        )
        for selector in indicators:
            if page.locator(selector).count() > 0:
                return True
        item = page.locator(f"xpath={_topic_item_xpath(topic)}")
        if item.count() == 0:
            return False
        add_entry = item.first.locator("xpath=.//*[contains(normalize-space(.), '添加话题')]")
        if add_entry.count() == 0:
            return True
        return False

    def _click_topic_add_button(self, page: Page, topic: str) -> bool:
        """
        点击话题旁边的“添加”按钮。
        """
        for xpath in _topic_button_xpaths(topic):
            locator = page.locator(f"xpath={xpath}")
            if locator.count() == 0:
                continue
            try:
                locator.first.click(timeout=3_000)
                return True
            except PlaywrightTimeoutError:
                continue

        fallback = page.locator('button:has-text("添加话题"), [role="button"]:has-text("添加话题")')
        for index in range(fallback.count()):
            button = fallback.nth(index)
            try:
                container_text = button.locator("xpath=ancestor::*[self::div or self::section][1]").inner_text(timeout=1_000)
            except Exception:
                container_text = ""
            if topic in container_text:
                button.click(timeout=3_000)
                return True
        return False

    def _create_context(self, browser: Any) -> Any:
        """创建浏览器上下文。"""
        storage_state = self._storage_state_value()
        if storage_state is not None:
            return browser.new_context(storage_state=storage_state)
        return browser.new_context()

    def _storage_state_value(self) -> str | dict[str, Any] | None:
        """解析并返回 Playwright storage_state 的值。"""
        if not self.cookies_path or not self.cookies_path.exists():
            return None
        raw = self.cookies_path.read_text(encoding="utf-8")
        if not raw.strip():
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return str(self.cookies_path)
        if isinstance(payload, list):
            return {"cookies": payload, "origins": []}
        if isinstance(payload, dict) and "cookies" in payload:
            return payload
        return str(self.cookies_path)

    def _load_cookies(self, context: Any) -> None:
        """加载 Cookie。"""
        if not self.cookies_path or not self.cookies_path.exists():
            return
        cookies = json.loads(self.cookies_path.read_text(encoding="utf-8"))
        if cookies:
            context.add_cookies(cookies)

    def _save_cookies(self, context: Any) -> None:
        """保存当前登录状态到文件。"""
        if not self.cookies_path:
            return
        context.storage_state(path=str(self.cookies_path))

    def _detect_scene(self, page: Page) -> str:
        """
        识别当前页面所处的场景。
        """
        if "published=true" in page.url:
            return "publish_result"
        for scene in SCENE_SPECS:
            for detector in scene.detectors:
                if page.locator(detector).count() > 0:
                    return scene.scene_name
        return "unknown"

    def _log(self, message: str) -> None:
        """打印带前缀的日志。"""
        print(f"[RedNoteBot] {message}")

    def _wait_for_scene(self, page: Page, scene_names: tuple[str, ...], timeout_ms: int) -> str:
        """等待页面进入指定的场景之一。"""
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            scene = self._detect_scene(page)
            if scene in scene_names:
                return scene
            page.wait_for_timeout(500)
        expected = ", ".join(_scene_label(name) for name in scene_names)
        raise PlaywrightTimeoutError(f"等待场景超时，期望进入：{expected}")

    def _wait_for_action(self, page: Page, field_name: str, timeout_ms: int) -> Locator:
        """等待指定的动作元素在页面上可见。"""
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            locator = self._find_first_matching_locator(page, field_name)
            if locator is not None and locator.first.is_visible():
                return locator.first
            page.wait_for_timeout(500)
        raise PlaywrightTimeoutError(f"等待动作 `{field_name}` 对应元素超时。")

    def _collect_page_features(self, page: Page) -> list[PageFeature]:
        """采集当前页面所有预定义动作元素的特征。"""
        features: list[PageFeature] = []
        for spec in SELECTOR_SPECS:
            matched_selector, match_count, first_tag, first_text = self._probe_selectors(page, spec.selectors)
            features.append(
                PageFeature(
                    scene_name=spec.scene_name,
                    action_name=spec.action_name,
                    field_name=spec.field_name,
                    candidates=spec.selectors,
                    matched_selector=matched_selector,
                    description=spec.description,
                    match_count=match_count,
                    first_tag=first_tag,
                    first_text=first_text[:80],
                )
            )
        return features

    def _click_action_if_found(self, page: Page, field_name: str) -> bool:
        """如果找到了指定动作的元素，则点击它。"""
        locator = self._find_first_matching_locator(page, field_name)
        if locator is None:
            return False
        locator.first.click()
        return True

    def _require_locator(self, page: Page, field_name: str) -> Locator:
        """
        获取指定动作的元素，如果未找到则抛出异常。
        """
        locator = self._find_first_matching_locator(page, field_name)
        if locator is None:
            raise RuntimeError(f"未找到动作 `{field_name}` 对应元素，请先重新采集页面特征。")
        return locator.first

    def _find_first_matching_locator(self, page: Page, field_name: str) -> Locator | None:
        """
        在页面中按顺序查找匹配指定动作候选选择器的第一个元素。
        """
        spec = _selector_spec(field_name)
        for selector in spec.selectors:
            locator = page.locator(selector)
            if locator.count() > 0:
                return locator
        return None

    def _probe_selectors(self, page: Page, selectors: tuple[str, ...]) -> tuple[str, int, str, str]:
        """
        探测一组选择器，返回第一个命中的选择器及其元素特征。
        """
        for selector in selectors:
            locator = page.locator(selector)
            count = locator.count()
            if count == 0:
                continue
            first = locator.first
            try:
                first_tag = first.evaluate("element => element.tagName.toLowerCase()")
            except Exception:
                first_tag = ""
            try:
                first_text = first.inner_text(timeout=1_500).strip().replace("\n", " ")
            except Exception:
                first_text = ""
            return selector, count, first_tag, first_text
        return "", 0, "", ""


def _ensure_images_exist(images: list[Path]) -> None:
    """确保所有待上传的图片文件都存在。"""
    missing = [str(path) for path in images if not path.exists()]
    if missing:
        joined = "\n".join(missing)
        raise FileNotFoundError(f"以下图片不存在：\n{joined}")


def _selector_spec(field_name: str) -> SelectorSpec:
    """根据变量名查找其对应的选择器规格。"""
    for spec in SELECTOR_SPECS:
        if spec.field_name == field_name:
            return spec
    raise KeyError(f"未知动作字段：{field_name}")


def _scene_label(scene_name: str) -> str:
    """将场景内部标识符转换为人类可读的标签。"""
    for scene in SCENE_SPECS:
        if scene.scene_name == scene_name:
            return scene.label
    return "未知场景"


def _markdown_cell(value: str) -> str:
    """转义 Markdown 表格单元格中的特殊字符。"""
    return value.replace("|", "\\|")


def _topic_button_xpaths(topic: str) -> tuple[str, ...]:
    """生成查找话题添加按钮的 XPath。"""
    literal = _xpath_literal(topic)
    return (
        f"{_topic_item_xpath(topic)}//*[self::button or @role='button' or self::span][contains(normalize-space(.), '添加话题')]",
        f"//*[contains(@class, 'events')]//*[contains(normalize-space(.), {literal})]//*[self::button or @role='button' or self::span][contains(normalize-space(.), '添加话题')]",
    )


def _topic_container_xpaths(topic: str) -> tuple[str, ...]:
    """生成查找话题容器的 XPath。"""
    literal = _xpath_literal(topic)
    return (
        f"//*[contains(normalize-space(.), {literal})]/ancestor::*[self::div or self::section][1]",
        f"//*[contains(normalize-space(.), {literal})]",
    )


def _xpath_literal(value: str) -> str:
    """处理 XPath 中的引号转义。"""
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    quoted = ", \"'\", ".join(f"'{part}'" for part in parts)
    return f"concat({quoted})"


def _topic_item_xpath(topic: str) -> str:
    """生成查找话题条目的 XPath。"""
    literal = _xpath_literal(topic)
    return "//*[contains(@class, 'event') or contains(@class, 'item')][.//*[contains(normalize-space(.), {literal})]]".format(
        literal=literal
    )
