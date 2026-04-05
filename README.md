# RedNoteBot

`RedNoteBot` 是一个基于 Python 3.12、`uv` 和 Playwright 的小红书自动发布项目。当前仓库只聚焦“小红书长文模式”一条发布链路：它从 `notes/` 目录读取 Markdown 模板，解析标题、正文、标签、活动话题与可选附加图片，然后驱动小红书网页版完成进入长文编辑器、填写内容、上传图片和发布。

> 注意：小红书网页版的 DOM 结构会变动，脚本中已将选择器集中管理，实际使用时通常需要根据页面最新结构做一次调整。
>
> `docs/` 和 `notes/` 目录默认视为本地示例与调试产物目录，用于放页面采样、截图、HTML 快照、特征表和待发布 Markdown。这两个目录已加入 `.gitignore`，不作为仓库正式提交内容。

## 项目目录结构

```text
RedNoteBot/
├── .gitignore
├── .python-version
├── README.md
├── publish_xhs.py
├── pyproject.toml
├── uv.lock
├── notes/
│   └── sample_note.md
└── src/
    └── rednotebot/
        ├── __init__.py
        ├── cli.py
        ├── parser.py
        └── publisher.py
```

## 功能说明

- 从 Markdown 模板中解析：
  - `# 标题`
  - `## 正文`
  - `## 标签`（可选）
  - `## 活动话题` / `## 话题`（可选）
  - `## 附加图片`（可选）
- 支持在正文和附加图片区块中使用 Markdown 图片语法（可选）
- 支持首次人工扫码登录并保存 Playwright `storage_state`
- 后续发布流程复用 `playwright-state.json`，避免重复登录
- 使用 Playwright 自动打开小红书创作中心，并只走长文模式发布链路
- 将页面选择器和场景检测规则集中在 `src/rednotebot/publisher.py` 中，便于后续替换
- 页面操作默认采用“语义定位优先 + CSS fallback”策略
- 内置随机延迟、逐字输入、悬停点击和滚动模拟，降低机械操作特征

## 本地示例目录说明

项目约定保留两个本地目录用于示例和排障：

- `notes/`：存放待发布 Markdown、草稿和本地测试样例，例如 `notes/sample_note.md`
- `docs/`：存放页面截图、HTML 快照、特征采样表和排障记录，例如 `docs/xhs-page-features.md`

这两个目录的用途是“本地可观察、可调试”，不是仓库正式资产：

- 可以放临时样例、草稿、截图和页面探测结果
- 可以作为运行流程说明中的示例路径
- 默认不提交到 Git，避免把个人内容、调试垃圾和页面采样带进版本库

如果只是给团队成员说明目录结构，建议在本文档中描述这些路径，而不是依赖仓库中长期保留真实样例文件。

## Markdown 写法说明

`notes/` 目录中的 Markdown 建议按下面结构书写，下面是一个本地示例：

```md
# 周末咖啡店探店分享

## 正文
这是一段正文。

## 标签
#咖啡店探店 #上海周末 #拍照打卡

## 活动话题
上海咖啡地图
```

约定说明：

- 一级标题 `#` 作为笔记标题
- `## 正文` 为必填
- `## 标签` 可选，支持空格、中文逗号、英文逗号分隔
- `## 活动话题` 或 `## 话题` 可选，支持空格、中文逗号、英文逗号分隔；会在发布确认页尝试点击对应的“添加话题”
- `## 附加图片` 可选
- 如果使用图片，路径相对当前 Markdown 文件解析

`docs/` 目录则适合放脚本运行过程中生成的说明文件，例如：

- 页面元素特征表：`docs/xhs-page-features.md`
- 调试截图：`docs/*.png`
- 页面快照：`docs/*.html`

这些文件主要用于本地排障、选择器核对和流程回放，默认不提交。

## 运行方式约定

- 本项目当前仅支持在 Windows 本机运行，使用有界面浏览器进行登录、调试和发布
- 首次登录必须人工扫码完成，并把登录态保存为 `playwright-state.json`
- 后续发布只复用 `storage_state`，如果登录态失效，脚本会直接报错并提示重新登录
- 选择器维护、页面联调和发布执行都以 Windows 本地环境为准，不再提供 Docker 运行方式

## 如何通过命令运行程序

项目当前有两个等价的命令入口：

- 入口 1：`uv run python publish_xhs.py`
- 入口 2：`uv run rednotebot-publish`

推荐优先使用 `uv run rednotebot-publish`，因为它直接走 `pyproject.toml` 中声明的 CLI 入口；如果你只是临时调试脚本文件，也可以继续使用 `uv run python publish_xhs.py`。

## Windows 本地开发

建议直接在 Windows Terminal、PowerShell 或 CMD 中运行。

1. 确保 Windows 已安装 Python 3.12 和 `uv`
2. 安装依赖

```powershell
uv sync
```

3. 安装 Playwright Chromium 浏览器

```powershell
uv run playwright install chromium
```

4. 查看命令帮助

```powershell
uv run rednotebot-publish --help
```

如果你更习惯脚本文件入口，也可以执行：

```powershell
uv run python publish_xhs.py --help
```

5. 首次初始化登录态

```powershell
uv run rednotebot-publish --login --storage-state playwright-state.json
```

命令会打开浏览器并等待你手动扫码登录；成功后会把 Playwright 状态保存到 `playwright-state.json`。该文件属于敏感登录凭证，应本地持久化保存，不要提交到仓库。

如果你更习惯脚本文件入口，对应命令是：

```powershell
uv run python publish_xhs.py --login --storage-state playwright-state.json
```

6. 发布一篇 Markdown 笔记

```powershell
uv run rednotebot-publish notes/sample_note.md --storage-state playwright-state.json
```

默认情况下，这个命令只会跑到发布确认页，不会真正点击发布按钮。

如果你确认要真正发出内容，必须显式传入：

```powershell
uv run rednotebot-publish notes/sample_note.md --storage-state playwright-state.json --confirm-publish
```

如果你只想显式联调到发布确认页，不真正发出内容，可以使用：

```powershell
uv run rednotebot-publish notes/sample_note.md --storage-state playwright-state.json --stop-before-publish
```

如果希望降低固定时间触发的风险，可以增加启动前随机等待：

```powershell
uv run rednotebot-publish notes/sample_note.md --storage-state playwright-state.json --startup-delay-min 0 --startup-delay-max 30
```

7. 打印当前脚本使用的选择器表

```powershell
uv run rednotebot-publish --print-selectors
```

8. 自动采集当前页面特征并生成 Markdown 表

```powershell
uv run rednotebot-publish --inspect-page --storage-state playwright-state.json --feature-output docs/xhs-page-features.md
```

说明：

- 默认采集地址是 `https://creator.xiaohongshu.com/publish/publish`
- 如果状态文件无效或登录态失效，最终页面可能跳转到登录页，生成的表格会按实际命中结果记录
- 这个命令适合在 Windows 本地开发时做“场景 -> 动作 -> 元素 -> 命中情况”核对

常用命令速查：

```powershell
# 查看帮助
uv run rednotebot-publish --help

# 初始化登录态
uv run rednotebot-publish --login --storage-state playwright-state.json

# 发布指定 Markdown
uv run rednotebot-publish notes/sample_note.md --storage-state playwright-state.json

# 真正发布
uv run rednotebot-publish notes/sample_note.md --storage-state playwright-state.json --confirm-publish

# 跑到发布确认页后停止
uv run rednotebot-publish notes/sample_note.md --storage-state playwright-state.json --stop-before-publish

# 发布前随机等待 0-30 分钟
uv run rednotebot-publish notes/sample_note.md --storage-state playwright-state.json --startup-delay-min 0 --startup-delay-max 30

# 调整超时
uv run rednotebot-publish notes/sample_note.md --storage-state playwright-state.json --timeout 30000

# 输出页面特征表
uv run rednotebot-publish --inspect-page --storage-state playwright-state.json --feature-output docs/xhs-page-features.md
```

## 场景化选择器策略

脚本内置的默认选择器和场景检测集中在 `src/rednotebot/publisher.py` 的 `SCENE_SPECS`、`ACTION_SPECS` / `SelectorSet` 中。当前只维护长文模式所需动作。你也可以直接运行下面命令打印表格：

```powershell
uv run rednotebot-publish --print-selectors
```

默认动作映射如下：

| 场景 | 变量名 | 语义定位优先 | CSS fallback | 说明 |
| --- | --- | --- | --- | --- |
| 登录页 | `login_button` | `get_by_role("button", name="登录")` / `get_by_text("扫码登录")` | `button:has-text("登录")` 等 | 登录入口，仅用于人工扫码初始化 |
| 创作平台导航页 | `long_article_entry` | `get_by_role("tab", name="写长文")` / `get_by_text("写长文")` | `.creator-tab:has-text("写长文")` 等 | 从导航页进入长文创作流 |
| 长文编辑页 | `title_input` | `get_by_placeholder(...)` | `textarea[placeholder*="输入标题"]` 等 | 标题输入框 |
| 长文编辑页 | `body_editor` | `get_by_placeholder(...)` / `get_by_text(...)` | `[contenteditable="true"]` 等 | 正文编辑区域 |
| 长文编辑页 | `image_input` | 无 | `input[type="file"]` | 图片上传 input |
| 长文编辑页 | `publish_button` | `get_by_role("button", name="发布")` | `button:has-text("发布")` 等 | 发布按钮 |
| 长文编辑页 | `tag_suggestion` | 无 | `[class*="tag"]` 等 | 标签建议项，可选 |
| 发布结果页 | `publish_success_hint` | `get_by_text(/发布成功|笔记发布成功|发布完成/)` | `text=发布成功` 等 | 发布完成提示 |

默认场景如下：

| 场景 | 判定信号 | 说明 |
| --- | --- | --- |
| 登录页 | `APP扫一扫登录` / `扫码登录` / `登录` 按钮 | 需要人工登录 |
| 创作平台导航页 | `写长文` / `发布笔记` / `笔记管理` | 已登录但还未进入长文编辑器 |
| 长文编辑页 | 标题输入框 / 正文编辑器 | 可直接填写长文表单 |
| 发布结果页 | `发布成功` / `笔记发布成功` / `查看笔记` | 已完成提交流程 |

自动采集后的页面特征表默认输出到 [docs/xhs-page-features.md](D:\workspace\RedNoteBot\docs\xhs-page-features.md)，用于记录每个动作在当前页面上的实际命中情况。

## 风险与补充说明

- 小红书网页结构变化频繁，选择器可能需要更新
- 当前仓库只维护长文模式链路；图文、视频等其他入口暂不纳入选择器策略
- 某些账号登录、图片上传、标签联想和发布过程可能存在风控或弹窗，需要按实际页面补充处理逻辑
- 发布频率建议控制在单次只发 1 篇，新号每天最多 1 到 2 条
- `playwright-state.json` 属于敏感登录凭证，不应提交到仓库或输出到日志
- 如果页面轻微改版，优先先跑 `--inspect-page` 导出特征表，再更新 `ACTION_SPECS` 中的语义定位和 fallback 规则
