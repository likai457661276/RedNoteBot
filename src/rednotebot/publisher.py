from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Browser, BrowserContext, Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from .parser import NoteContent


PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"
DEFAULT_LOGIN_URL = "https://creator.xiaohongshu.com/"


SemanticFactory = Callable[[Page], Locator]


@dataclass(frozen=True, slots=True)
class BrowserProfile:
    """定义固定浏览器环境，降低环境漂移带来的风控波动。"""

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
    viewport_width: int = 1440
    viewport_height: int = 900
    locale: str = "zh-CN"
    timezone_id: str = "Asia/Shanghai"
    color_scheme: str = "light"


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """定义页面动作的语义定位与 CSS 兜底策略。"""

    field_name: str
    scene_name: str
    action_name: str
    semantics: tuple["SemanticLocator", ...]
    css_fallbacks: tuple[str, ...]
    description: str


@dataclass(frozen=True, slots=True)
class SceneSpec:
    """定义页面场景及其识别特征。"""

    scene_name: str
    label: str
    detectors: tuple[str, ...]
    description: str


@dataclass(frozen=True, slots=True)
class PageFeature:
    """存储页面动作元素的探测结果。"""

    scene_name: str
    action_name: str
    field_name: str
    semantic_names: tuple[str, ...]
    css_fallbacks: tuple[str, ...]
    matched_strategy: str
    description: str
    match_count: int
    first_tag: str
    first_text: str


@dataclass(frozen=True, slots=True)
class PageFeatureReport:
    """页面特征采集报告。"""

    requested_url: str
    final_url: str
    page_title: str
    detected_scene: str
    features: tuple[PageFeature, ...]


@dataclass(frozen=True, slots=True)
class LocatorCandidate:
    """封装一次动作定位结果。"""

    locator: Locator
    strategy: str


@dataclass(frozen=True, slots=True)
class SemanticLocator:
    """为语义定位器提供稳定的可读名称。"""

    name: str
    factory: SemanticFactory

    def resolve(self, page: Page) -> Locator:
        """在页面上解析真实 Locator。"""
        return self.factory(page)


def _display_name(value: str | re.Pattern[str]) -> str:
    """将文本或正则转换为可读名称。"""

    if isinstance(value, re.Pattern):
        return f"/{value.pattern}/"
    return value


def _by_role(role: str, name: str | re.Pattern[str]) -> SemanticLocator:
    """生成基于 ARIA role 的语义定位器。"""

    return SemanticLocator(
        name=f'get_by_role("{role}", name="{_display_name(name)}")',
        factory=lambda page: page.get_by_role(role, name=name),
    )


def _by_text(text: str | re.Pattern[str], exact: bool = False) -> SemanticLocator:
    """生成基于文本的语义定位器。"""

    label = f'get_by_text("{_display_name(text)}")'
    if exact:
        label = f"{label} [exact]"
    return SemanticLocator(
        name=label,
        factory=lambda page: page.get_by_text(text, exact=exact),
    )


def _by_placeholder(text: str | re.Pattern[str]) -> SemanticLocator:
    """生成基于 placeholder 的语义定位器。"""

    return SemanticLocator(
        name=f'get_by_placeholder("{_display_name(text)}")',
        factory=lambda page: page.get_by_placeholder(text),
    )


def _semantic_name(locator_factory: SemanticLocator) -> str:
    """提取语义定位器名称，便于输出调试信息。"""

    return locator_factory.name


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
        ('.new-btn', 'button:has-text(\"新的创作\")', '.import-link-btn'),
        "已进入长文入口，但还需要新建一篇长文。",
    ),
    SceneSpec(
        "editor",
        "长文编辑页",
        ('textarea[placeholder*=\"输入标题\"]', '.next-btn', '[contenteditable=\"true\"]'),
        "可以直接填写长文标题、正文并上传图片。",
    ),
    SceneSpec(
        "login",
        "登录页",
        ("text=APP扫一扫登录", "text=扫码登录", 'button:has-text(\"登录\")'),
        "需要人工扫码或账号登录。",
    ),
    SceneSpec(
        "studio_home",
        "创作平台导航页",
        ('.creator-tab', '.upload-input', "text=发布笔记"),
        "已进入创作平台，但还未进入长文编辑器。",
    ),
)


ACTION_SPECS = (
    ActionSpec(
        "login_button",
        "login",
        "触发登录",
        (
            _by_role("button", "登录"),
            _by_text("APP扫一扫登录"),
            _by_text("扫码登录"),
        ),
        ('button:has-text(\"登录\")', 'text=APP扫一扫登录', 'text=扫码登录'),
        "登录入口，仅用于人工扫码登录初始化。",
    ),
    ActionSpec(
        "long_article_entry",
        "studio_home",
        "进入长文创作入口",
        (
            _by_role("tab", "写长文"),
            _by_role("button", "写长文"),
            _by_text("写长文"),
        ),
        ('.creator-tab:has-text(\"写长文\")', 'span.title:has-text(\"写长文\")', "text=写长文"),
        "从导航页进入长文创作流。",
    ),
    ActionSpec(
        "new_article_button",
        "article_hub",
        "新建长文",
        (
            _by_role("button", "新的创作"),
            _by_text("新的创作"),
        ),
        ('.new-btn', 'button:has-text(\"新的创作\")', "text=新的创作"),
        "在长文入口页创建一篇新的长文。",
    ),
    ActionSpec(
        "title_input",
        "editor",
        "填写标题",
        (
            _by_placeholder("填写标题会有更多赞哦～"),
            _by_placeholder(re.compile("标题")),
        ),
        ('textarea[placeholder*=\"输入标题\"]', 'input[placeholder*=\"标题\"]', 'textarea[placeholder*=\"标题\"]'),
        "标题输入框。",
    ),
    ActionSpec(
        "body_editor",
        "editor",
        "填写正文",
        (
            _by_placeholder(re.compile("正文|输入正文")),
            _by_text(re.compile("请输入正文|写下你的正文"), exact=False),
        ),
        ('[contenteditable=\"true\"]', 'textarea[placeholder*=\"正文\"]'),
        "正文编辑区域。",
    ),
    ActionSpec(
        "image_input",
        "editor",
        "上传图片",
        (),
        ('input[type=\"file\"][accept*=\"image\"]', 'input[type=\"file\"]'),
        "图片上传 input。",
    ),
    ActionSpec(
        "publish_button",
        "publish_result",
        "提交发布",
        (
            _by_role("button", "发布"),
            _by_role("button", "立即发布"),
            _by_text("发布"),
        ),
        ('button:has-text(\"发布\")', 'button:has-text(\"立即发布\")', '[role=\"button\"]:has-text(\"发布\")'),
        "发布按钮。",
    ),
    ActionSpec(
        "format_button",
        "editor",
        "生成排版预览",
        (
            _by_role("button", "一键排版"),
            _by_text("一键排版"),
        ),
        ('.next-btn', 'button:has-text(\"一键排版\")'),
        "将长文内容生成图片化排版。",
    ),
    ActionSpec(
        "next_step_button",
        "publish_result",
        "进入发布确认页",
        (
            _by_role("button", "下一步"),
            _by_text("下一步"),
        ),
        ('button:has-text(\"下一步\")',),
        "完成排版后进入最终发布确认页。",
    ),
    ActionSpec(
        "tag_suggestion",
        "editor",
        "确认标签联想",
        (),
        ('[class*=\"tag\"]', '[class*=\"suggest\"]', '[class*=\"mention\"]'),
        "标签建议项，可选。",
    ),
    ActionSpec(
        "publish_success_hint",
        "publish_result",
        "识别发布成功",
        (
            _by_text(re.compile("发布成功|笔记发布成功|发布完成")),
        ),
        ("text=发布成功", "text=笔记发布成功", "text=发布完成"),
        "发布完成提示。",
    ),
)


class SelectorSet:
    """兼容旧接口，便于打印当前动作配置。"""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def __getattr__(self, item: str) -> str:
        try:
            return self._values[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


DEFAULT_SELECTORS = SelectorSet({spec.field_name: ", ".join(spec.css_fallbacks) for spec in ACTION_SPECS})


def selector_reference_markdown(selectors: SelectorSet = DEFAULT_SELECTORS) -> str:
    """导出动作与选择器对照表。"""

    lines = [
        "| 场景 | 动作 | 变量名 | 语义定位 | CSS fallback | 说明 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for spec in ACTION_SPECS:
        scene_label = _scene_label(spec.scene_name)
        semantics = " / ".join(_semantic_name(item) for item in spec.semantics) or "-"
        selector = getattr(selectors, spec.field_name)
        lines.append(f"| {scene_label} | {spec.action_name} | `{spec.field_name}` | `{semantics}` | `{selector}` | {spec.description} |")
    return "\n".join(lines)


def page_feature_markdown(report: PageFeatureReport) -> str:
    """导出页面特征采集结果。"""

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
            "| 场景 | 动作 | 变量名 | 语义定位 | CSS fallback | 命中策略 | 命中数 | 首个标签 | 首个文本 | 说明 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for feature in report.features:
        lines.append(
            "| {scene} | {action} | `{field}` | `{semantic}` | `{css}` | `{matched}` | {count} | `{tag}` | {text} | {desc} |".format(
                scene=_scene_label(feature.scene_name),
                action=feature.action_name,
                field=feature.field_name,
                semantic=_markdown_cell(" | ".join(feature.semantic_names) or "-"),
                css=_markdown_cell(" | ".join(feature.css_fallbacks) or "-"),
                matched=_markdown_cell(feature.matched_strategy or "-"),
                count=feature.match_count,
                tag=_markdown_cell(feature.first_tag or "-"),
                text=_markdown_cell(feature.first_text or "-"),
                desc=feature.description,
            )
        )
    return "\n".join(lines)


class XhsPublisher:
    """负责执行小红书笔记发布与登录态初始化流程。"""

    def __init__(
        self,
        selectors: SelectorSet = DEFAULT_SELECTORS,
        storage_state_path: str | Path = "playwright-state.json",
        timeout_ms: int = 15_000,
        launch_delay_range: tuple[int, int] = (0, 0),
        profile: BrowserProfile = BrowserProfile(),
    ) -> None:
        """
        初始化发布器。

        Args:
            selectors: 选择器配置表，主要用于导出调试信息。
            storage_state_path: Playwright 登录态文件路径。
            timeout_ms: 默认等待超时毫秒数。
            launch_delay_range: 启动前随机延迟范围，单位分钟。
            profile: 固定浏览器环境配置。
        """
        self.selectors = selectors
        self.storage_state_path = Path(storage_state_path).expanduser().resolve()
        self.timeout_ms = timeout_ms
        self.launch_delay_range = launch_delay_range
        self.profile = profile
        self._rng = random.Random()

    def _relogin_command(self) -> str:
        """返回适用于当前状态文件的 Windows 重新登录命令。"""

        return f'uv run rednotebot-publish --login --storage-state "{self.storage_state_path}"'

    def _log_info(self, message: str) -> None:
        """输出信息级日志。"""

        self._log("INFO", message)

    def _log_warn(self, message: str) -> None:
        """输出警告级日志。"""

        self._log("WARN", message)

    def _log_error(self, message: str) -> None:
        """输出错误级日志。"""

        self._log("ERROR", message)

    def login_and_save_state(self, login_url: str = DEFAULT_LOGIN_URL, wait_timeout_ms: int = 180_000) -> None:
        """
        打开可视化浏览器，等待人工扫码登录并保存 storage_state。

        Args:
            login_url: 初始化登录时打开的页面。
            wait_timeout_ms: 等待人工完成登录的超时时间。
        """
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False, slow_mo=0)
            context = self._create_context(browser, storage_state_required=False)
            context.set_default_timeout(self.timeout_ms)
            page = context.new_page()
            self._log_info(f"打开登录页：{login_url}")
            page.goto(login_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2_000)
            self._log_info("请在浏览器中手动扫码登录，登录成功后程序会保存 storage_state。")
            try:
                self._wait_for_scene(page, ("studio_home", "editor", "article_hub"), timeout_ms=wait_timeout_ms)
            except PlaywrightTimeoutError as exc:
                raise RuntimeError("等待人工登录超时，未保存新的 storage_state。") from exc
            self._save_storage_state(context)
            self._log_info(f"登录态已保存：{self.storage_state_path}")
            browser.close()

    def publish(self, note: NoteContent) -> None:
        """
        仅使用已存在的 storage_state 发布一篇笔记。

        Args:
            note: 结构化笔记内容。
        """
        self.publish_note(note)

    def publish_note(self, note: NoteContent, stop_before_publish: bool = False) -> None:
        """
        执行发布流程，可选在最终点击发布前停止。

        Args:
            note: 结构化笔记内容。
            stop_before_publish: 为 True 时仅联调到发布确认页，不真正提交。
        """
        self._ensure_storage_state_exists()
        _ensure_images_exist(note.images)
        self._apply_launch_delay()

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False, slow_mo=0)
            context = self._create_context(browser, storage_state_required=True)
            context.set_default_timeout(self.timeout_ms)
            page = context.new_page()

            self._log_info(f"开始发布：{note.title}")
            self._open_home(page)
            self._ensure_logged_in(page)
            self._open_editor(page)
            self._fill_form(page, note)
            self._submit(page, note, stop_before_publish=stop_before_publish)
            self._save_storage_state(context)
            self._log_info(f"发布流程结束，当前页面：{page.url}")
            browser.close()

    def inspect_page(self, url: str = PUBLISH_URL) -> PageFeatureReport:
        """采集指定页面的特征，用于排查页面结构变化。"""

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False, slow_mo=0)
            context = self._create_context(browser, storage_state_required=False)
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

            browser.close()
            return report

    def _open_home(self, page: Page) -> None:
        """打开发布主页。"""

        self._log_info(f"打开发布页：{PUBLISH_URL}")
        page.goto(PUBLISH_URL, wait_until="domcontentloaded")
        self.human_delay(0.8, 1.5, reason="等待创作中心加载")

    def _ensure_logged_in(self, page: Page) -> None:
        """
        校验当前 storage_state 是否仍然有效。

        若仍停留在登录页，则直接报错并要求人工重新登录，不自动修复。
        """

        scene = self._detect_scene(page)
        if scene == "login":
            raise RuntimeError(
                "检测到当前仍处于登录页，storage_state 可能已失效。"
                f"\n请在 Windows 本地重新登录并覆盖当前登录态：\n{self._relogin_command()}"
            )

    def _open_editor(self, page: Page) -> None:
        """从创作中心导航到长文编辑页。"""

        scene = self._detect_scene(page)
        if scene == "editor":
            self._log_info("已在长文编辑页。")
            return

        if scene == "login":
            raise RuntimeError("当前仍停留在登录页，无法进入长文编辑器。")

        self._log_info(f"准备进入长文入口，当前场景：{_scene_label(scene)}")
        self.safe_click(page, "long_article_entry")
        self.human_delay(0.8, 1.4, reason="等待创作入口切换")

        scene = self._wait_for_scene(page, ("article_hub", "editor"), timeout_ms=30_000)
        if scene == "article_hub":
            self._log_info("已进入长文入口页，准备点击“新的创作”。")
            self.safe_click(page, "new_article_button")
            self._wait_for_scene(page, ("editor",), timeout_ms=30_000)

        self._log_info("已进入长文编辑页。")

    def _fill_form(self, page: Page, note: NoteContent) -> None:
        """在编辑器中填写标题、正文并上传图片。"""

        payload = note.to_publish_payload()
        self._log_info("开始填写标题和正文。")
        self.safe_fill(page, "title_input", str(payload["title"]), clear=True)
        self.safe_fill(page, "body_editor", str(payload["content"]), clear=True, multiline=True)

        if note.images:
            self._log_info(f"开始上传图片，共 {len(note.images)} 张。")
            upload_input = self._require_locator(page, "image_input")
            upload_input.locator.set_input_files([str(path) for path in note.images])
            self.human_delay(0.8, 1.4, reason="等待上传任务进入队列")
            self._wait_for_upload_settle(page)

        self._log_info("内容填写完成。")

    def _submit(self, page: Page, note: NoteContent, stop_before_publish: bool = False) -> None:
        """执行排版、补充标签，并按需在最终发布前停止。"""

        self._log_info("开始排版。")
        self.safe_click(page, "format_button")
        self._wait_for_action(page, "next_step_button", timeout_ms=30_000)
        self._log_info("进入发布确认页。")
        self.safe_click(page, "next_step_button")
        self.human_delay(1.0, 1.8, reason="等待发布确认页加载")
        self._fill_publish_description(page, note)
        self._wait_for_action(page, "publish_button", timeout_ms=30_000)
        if stop_before_publish:
            self._log_warn(f"已到达发布确认页，按要求在最终发布前停止：{page.url}")
            return
        self._log_info("点击发布按钮。")
        self.safe_click(page, "publish_button")

        try:
            self._wait_for_scene(page, ("publish_result",), timeout_ms=20_000)
            self._log_info(f"检测到发布成功结果页：{page.url}")
        except PlaywrightTimeoutError:
            self._log_warn(f"未捕获到明确的发布成功结果页，请人工确认页面状态：{page.url}")

    def _fill_publish_description(self, page: Page, note: NoteContent) -> None:
        """在发布确认页补充标签与话题。"""

        editor = self._require_locator(page, "body_editor").locator
        self.human_click(page, editor, description="描述编辑区")
        if note.tags:
            self._log_info(f"补充标签：{' '.join(note.tags)}")
            editor.press("End")
            self.human_delay(0.2, 0.4, reason="准备插入标签")
            for tag in note.tags:
                self.human_type(page, editor, f"{tag} ")
                self._confirm_tag(page, tag)

        if note.topics:
            self._log_info(f"补充话题：{' '.join(note.topics)}")
            editor.press("End")
            self.human_delay(0.2, 0.4, reason="准备插入话题")
            for topic in note.topics:
                normalized = topic.strip().lstrip("#").strip()
                if not normalized:
                    continue
                self.human_type(page, editor, f"#{normalized} ")
                self._confirm_tag(page, f"#{normalized}")

    def _confirm_tag(self, page: Page, tag: str) -> None:
        """处理标签输入后的自动建议确认。"""

        suggestions = self._find_first_matching_locator(page, "tag_suggestion")
        if suggestions is not None:
            candidate = suggestions.locator.filter(has_text=tag.lstrip("#")).first
            if candidate.count() > 0:
                try:
                    self.human_click(page, candidate, description=f"标签建议 {tag}", timeout_ms=1_500)
                    return
                except PlaywrightTimeoutError:
                    self._log_warn(f"标签建议点击超时，改用回车确认：{tag}")
        page.keyboard.press("Enter")
        self.human_delay(0.3, 0.6, reason="等待标签写入")

    def _wait_for_upload_settle(self, page: Page) -> None:
        """等待图片上传和处理完成。"""

        self.human_delay(1.5, 2.2, reason="等待图片上传开始")
        for _ in range(25):
            pending = page.locator('text=/上传中|处理中|封面生成中/')
            if pending.count() == 0:
                return
            self.human_delay(0.8, 1.2, reason="等待图片处理完成")

    def _create_context(self, browser: Browser, storage_state_required: bool) -> BrowserContext:
        """
        创建固定浏览器环境的上下文。

        Args:
            browser: 已启动的浏览器实例。
            storage_state_required: 是否强制要求加载已有登录态。
        """

        kwargs: dict[str, Any] = {
            "user_agent": self.profile.user_agent,
            "viewport": {"width": self.profile.viewport_width, "height": self.profile.viewport_height},
            "locale": self.profile.locale,
            "timezone_id": self.profile.timezone_id,
            "color_scheme": self.profile.color_scheme,
        }

        storage_state = self._storage_state_value(required=storage_state_required)
        if storage_state is not None:
            kwargs["storage_state"] = storage_state
        return browser.new_context(**kwargs)

    def _storage_state_value(self, required: bool) -> str | dict[str, Any] | None:
        """读取并返回 Playwright storage_state。"""

        if not self.storage_state_path.exists():
            if required:
                raise FileNotFoundError(
                    f"未找到登录态文件：{self.storage_state_path}。"
                    f"\n请先在 Windows 本地初始化登录态：\n{self._relogin_command()}"
                )
            return None

        raw = self.storage_state_path.read_text(encoding="utf-8").strip()
        if not raw:
            if required:
                raise RuntimeError(
                    f"登录态文件为空：{self.storage_state_path}。"
                    f"\n请在 Windows 本地重新登录并覆盖当前登录态：\n{self._relogin_command()}"
                )
            return None

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return str(self.storage_state_path)

        if isinstance(payload, list):
            return {"cookies": payload, "origins": []}
        if isinstance(payload, dict) and "cookies" in payload:
            return payload
        return str(self.storage_state_path)

    def _save_storage_state(self, context: BrowserContext) -> None:
        """保存当前登录状态到 storage_state 文件。"""

        self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(self.storage_state_path))

    def _ensure_storage_state_exists(self) -> None:
        """确保发布前存在可复用的登录态文件。"""

        if not self.storage_state_path.exists():
            raise FileNotFoundError(
                f"未找到登录态文件：{self.storage_state_path}。"
                f"\n请先在 Windows 本地初始化登录态：\n{self._relogin_command()}"
            )

    def _apply_launch_delay(self) -> None:
        """按配置在启动前执行随机等待，降低固定时间触发风险。"""

        minimum, maximum = self.launch_delay_range
        if maximum <= 0:
            return
        minutes = self._rng.randint(max(minimum, 0), max(maximum, 0))
        if minutes <= 0:
            return
        self._log_info(f"启动前随机等待 {minutes} 分钟。")
        time.sleep(minutes * 60)

    def human_delay(self, minimum_seconds: float = 0.2, maximum_seconds: float = 0.8, reason: str | None = None) -> None:
        """
        执行随机等待，模拟人类在阅读和确认页面。

        Args:
            minimum_seconds: 最小等待秒数。
            maximum_seconds: 最大等待秒数。
            reason: 日志用途的等待原因。
        """

        duration = self._rng.uniform(minimum_seconds, maximum_seconds)
        if reason:
            self._log_info(f"{reason}，随机停顿 {duration:.2f} 秒。")
        time.sleep(duration)

    def human_scroll(self, page: Page, distance: int | None = None) -> None:
        """
        以小步滚动页面，模拟人类浏览动作。

        Args:
            page: 当前页面。
            distance: 目标滚动距离；为空时自动随机生成。
        """

        target = distance if distance is not None else self._rng.randint(120, 420)
        step = 60 if target >= 0 else -60
        remaining = target
        while abs(remaining) > abs(step):
            page.mouse.wheel(0, step)
            remaining -= step
            self.human_delay(0.05, 0.15)
        page.mouse.wheel(0, remaining)
        self.human_delay(0.1, 0.25, reason="滚动结束后观察页面")

    def human_click(self, page: Page, locator: Locator, description: str, timeout_ms: int | None = None) -> None:
        """
        以更接近真人的方式点击元素。

        Args:
            page: 当前页面。
            locator: 目标元素。
            description: 日志中的动作说明。
            timeout_ms: 可选的定位超时。
        """

        locator.wait_for(state="visible", timeout=timeout_ms or self.timeout_ms)
        try:
            locator.scroll_into_view_if_needed(timeout=timeout_ms or self.timeout_ms)
        except Exception:
            self.human_scroll(page)
        self.human_delay(0.25, 0.75, reason=f"点击前观察 {description}")
        locator.hover(timeout=timeout_ms or self.timeout_ms)
        self.human_delay(0.08, 0.2, reason=f"悬停确认 {description}")
        locator.click(delay=self._rng.randint(40, 140), timeout=timeout_ms or self.timeout_ms)
        self.human_delay(0.18, 0.45, reason=f"点击后等待 {description} 响应")

    def human_type(self, page: Page, locator: Locator, text: str, clear: bool = False) -> None:
        """
        逐字输入内容，避免机械式瞬时填充。

        Args:
            page: 当前页面。
            locator: 目标输入元素。
            text: 待输入文本。
            clear: 是否在输入前清空现有内容。
        """

        self.human_click(page, locator, description="输入框")
        if clear:
            locator.press("Control+A")
            self.human_delay(0.05, 0.12)
            locator.press("Backspace")
            self.human_delay(0.08, 0.16)
        for char in text:
            locator.type(char, delay=self._rng.randint(40, 120))
            if char in "，。！？,.!?":
                self.human_delay(0.12, 0.28)
            elif char == "\n":
                self.human_delay(0.18, 0.35)
            else:
                self.human_delay(0.02, 0.08)

    def safe_click(self, page: Page, field_name: str, timeout_ms: int | None = None) -> None:
        """
        使用“语义定位优先 + CSS fallback”安全点击元素。

        Args:
            page: 当前页面。
            field_name: 动作字段名。
            timeout_ms: 可选超时。
        """

        candidate = self._require_locator(page, field_name)
        self._log_info(f"{field_name} 使用定位策略：{candidate.strategy}")
        try:
            self.human_click(page, candidate.locator, description=field_name, timeout_ms=timeout_ms)
        except Exception as exc:
            self._log_error(f"元素定位失败，可能页面结构已更新，请检查 selector：{field_name}")
            raise RuntimeError(f"元素定位失败，可能页面结构已更新，请检查 selector：{field_name}") from exc

    def safe_fill(
        self,
        page: Page,
        field_name: str,
        value: str,
        clear: bool = True,
        multiline: bool = False,
        timeout_ms: int | None = None,
    ) -> None:
        """
        使用统一定位与真人输入策略填写元素。

        Args:
            page: 当前页面。
            field_name: 动作字段名。
            value: 待填写文本。
            clear: 是否先清空内容。
            multiline: 是否按多行文本逐字输入。
            timeout_ms: 可选超时。
        """

        candidate = self._require_locator(page, field_name)
        locator = candidate.locator
        self._log_info(f"{field_name} 使用定位策略：{candidate.strategy}")
        locator.wait_for(state="visible", timeout=timeout_ms or self.timeout_ms)
        if multiline or "\n" in value:
            self.human_type(page, locator, value, clear=clear)
            return

        self.human_click(page, locator, description=field_name, timeout_ms=timeout_ms)
        if clear:
            locator.press("Control+A")
            self.human_delay(0.05, 0.12)
            locator.press("Backspace")
        self.human_type(page, locator, value, clear=False)

    def _detect_scene(self, page: Page) -> str:
        """识别当前页面所处的场景。"""

        if "published=true" in page.url:
            return "publish_result"
        for scene in SCENE_SPECS:
            for detector in scene.detectors:
                if page.locator(detector).count() > 0:
                    return scene.scene_name
        return "unknown"

    def _log(self, level: str, message: str) -> None:
        """打印带级别的统一前缀日志。"""

        print(f"[RedNoteBot][{level}] {message}")

    def _wait_for_scene(self, page: Page, scene_names: tuple[str, ...], timeout_ms: int) -> str:
        """等待页面进入指定场景之一。"""

        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            scene = self._detect_scene(page)
            if scene in scene_names:
                return scene
            page.wait_for_timeout(500)
        expected = ", ".join(_scene_label(name) for name in scene_names)
        raise PlaywrightTimeoutError(f"等待场景超时，期望进入：{expected}")

    def _wait_for_action(self, page: Page, field_name: str, timeout_ms: int) -> Locator:
        """等待指定动作元素在页面中出现。"""

        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            candidate = self._find_first_matching_locator(page, field_name)
            if candidate is not None and candidate.locator.first.is_visible():
                return candidate.locator.first
            page.wait_for_timeout(500)
        raise PlaywrightTimeoutError(f"等待动作 `{field_name}` 对应元素超时。")

    def _collect_page_features(self, page: Page) -> list[PageFeature]:
        """采集当前页面所有预定义动作元素的特征。"""

        features: list[PageFeature] = []
        for spec in ACTION_SPECS:
            matched_strategy, match_count, first_tag, first_text = self._probe_action(page, spec)
            features.append(
                PageFeature(
                    scene_name=spec.scene_name,
                    action_name=spec.action_name,
                    field_name=spec.field_name,
                    semantic_names=tuple(_semantic_name(item) for item in spec.semantics),
                    css_fallbacks=spec.css_fallbacks,
                    matched_strategy=matched_strategy,
                    description=spec.description,
                    match_count=match_count,
                    first_tag=first_tag,
                    first_text=first_text[:80],
                )
            )
        return features

    def _require_locator(self, page: Page, field_name: str) -> LocatorCandidate:
        """
        获取指定动作的元素；若失败则抛出带明确提示的异常。

        Args:
            page: 当前页面。
            field_name: 动作字段名。
        """

        candidate = self._find_first_matching_locator(page, field_name)
        if candidate is None:
            raise RuntimeError(f"元素定位失败，可能页面结构已更新，请检查 selector：{field_name}")
        return candidate

    def _find_first_matching_locator(self, page: Page, field_name: str) -> LocatorCandidate | None:
        """
        按“语义定位优先 + CSS fallback”顺序查找元素。

        Args:
            page: 当前页面。
            field_name: 动作字段名。
        """

        spec = _action_spec(field_name)
        for semantic in spec.semantics:
            locator = semantic.resolve(page)
            if locator.count() > 0:
                return LocatorCandidate(locator=locator.first, strategy=f"semantic:{_semantic_name(semantic)}")
        for selector in spec.css_fallbacks:
            locator = page.locator(selector)
            if locator.count() > 0:
                return LocatorCandidate(locator=locator.first, strategy=f"css:{selector}")
        return None

    def _probe_action(self, page: Page, spec: ActionSpec) -> tuple[str, int, str, str]:
        """探测动作定义，返回当前命中的策略和元素特征。"""

        for semantic in spec.semantics:
            locator = semantic.resolve(page)
            count = locator.count()
            if count == 0:
                continue
            return self._locator_probe(locator.first, f"semantic:{_semantic_name(semantic)}", count)
        for selector in spec.css_fallbacks:
            locator = page.locator(selector)
            count = locator.count()
            if count == 0:
                continue
            return self._locator_probe(locator.first, f"css:{selector}", count)
        return "", 0, "", ""

    def _locator_probe(self, locator: Locator, strategy: str, count: int) -> tuple[str, int, str, str]:
        """读取元素的标签与文本，生成调试特征。"""

        try:
            first_tag = locator.evaluate("element => element.tagName.toLowerCase()")
        except Exception:
            first_tag = ""
        try:
            first_text = locator.inner_text(timeout=1_500).strip().replace("\n", " ")
        except Exception:
            first_text = ""
        return strategy, count, first_tag, first_text


def _ensure_images_exist(images: list[Path]) -> None:
    """确保所有待上传的图片文件都存在。"""

    missing = [str(path) for path in images if not path.exists()]
    if missing:
        joined = "\n".join(missing)
        raise FileNotFoundError(f"以下图片不存在：\n{joined}")


def _action_spec(field_name: str) -> ActionSpec:
    """根据字段名查找动作配置。"""

    for spec in ACTION_SPECS:
        if spec.field_name == field_name:
            return spec
    raise KeyError(f"未知动作字段：{field_name}")


def _scene_label(scene_name: str) -> str:
    """将场景内部标识符转换为中文标签。"""

    for scene in SCENE_SPECS:
        if scene.scene_name == scene_name:
            return scene.label
    return "未知场景"


def _markdown_cell(value: str) -> str:
    """转义 Markdown 表格单元格中的特殊字符。"""

    return value.replace("|", "\\|")
