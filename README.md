# RedNoteBot

`RedNoteBot` 是一个基于 Python 3.12、`uv` 和 Playwright 的小红书自动发布项目骨架。当前仓库只聚焦“小红书长文模式”一条发布链路：它从 `notes/` 目录读取 Markdown 模板，解析标题、正文、标签、活动话题与可选附加图片，然后驱动小红书网页版完成登录、进入长文编辑器、填写内容、上传图片和发布。

> 注意：小红书网页版的 DOM 结构会变动，脚本中已将选择器集中管理，实际使用时通常需要根据页面最新结构做一次调整。

## 项目目录结构

```text
RedNoteBot/
├── .gitignore
├── .python-version
├── Dockerfile
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
- 支持通过 Playwright 状态文件复用登录态，兼容旧版仅 Cookie 文件
- 使用 Playwright 自动打开小红书创作中心，并只走长文模式发布链路
- 将页面选择器和场景检测规则集中在 `src/rednotebot/publisher.py` 中，便于后续替换

## Markdown 写法说明

示例：

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

## 运行方式约定

- 本地开发环境：Windows 本机运行，可直接拉起浏览器，便于手动登录、调试页面和测试发布流程
- 生产环境：Docker 容器运行，默认使用无头浏览器执行自动化任务
- 选择器维护：优先在 Windows 本地可视化浏览器中采集页面特征并更新脚本，Docker 只负责消费已经验证过的长文流程

## 如何通过命令运行程序

项目当前有两个等价的命令入口：

- 入口 1：`uv run python publish_xhs.py`
- 入口 2：`uv run rednotebot-publish`

推荐优先使用 `uv run rednotebot-publish`，因为它直接走 `pyproject.toml` 中声明的 CLI 入口；如果你只是临时调试脚本文件，也可以继续使用 `uv run python publish_xhs.py`。

## Windows 本地开发

建议直接在 Windows Terminal、PowerShell 或 CMD 中运行，不建议把 Docker 容器作为本地交互调试环境。

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

5. 首次运行并登录

```powershell
uv run rednotebot-publish notes/sample_note.md --cookies playwright-state.json
```

首次执行时如果登录态无效，脚本会等待你在打开的浏览器里手动完成登录；成功后会把最新 Playwright 状态保存到 `playwright-state.json`。本地开发默认使用有界面浏览器，便于直接观察和排查页面流程。

如果你更习惯脚本文件入口，对应命令是：

```powershell
uv run python publish_xhs.py notes/sample_note.md --cookies playwright-state.json
```

6. 无头运行一次发布流程

```powershell
uv run rednotebot-publish notes/sample_note.md --cookies playwright-state.json --headless
```

7. 打印当前脚本使用的选择器表

```powershell
uv run rednotebot-publish --print-selectors
```

8. 自动采集当前页面特征并生成 Markdown 表

```powershell
uv run rednotebot-publish --inspect-page --cookies playwright-state.json --feature-output docs/xhs-page-features.md
```

说明：

- 默认采集地址是 `https://creator.xiaohongshu.com/publish/publish`
- 如果状态文件无效或登录态失效，最终页面可能跳转到登录页，生成的表格会按实际命中结果记录
- 这个命令适合在 Windows 本地开发时做“场景 -> 动作 -> 元素 -> 命中情况”核对

常用命令速查：

```powershell
# 查看帮助
uv run rednotebot-publish --help

# 发布指定 Markdown
uv run rednotebot-publish notes/sample_note.md --cookies playwright-state.json

# 无头发布
uv run rednotebot-publish notes/sample_note.md --cookies playwright-state.json --headless

# 调整慢动作和超时
uv run rednotebot-publish notes/sample_note.md --cookies playwright-state.json --slow-mo 500 --timeout 30000

# 输出页面特征表
uv run rednotebot-publish --inspect-page --cookies playwright-state.json --feature-output docs/xhs-page-features.md
```

## Docker 生产运行

构建镜像：

```bash
docker build -t rednotebot:latest .
```

运行容器：

```bash
docker run --rm -it \
  -v "$(pwd)/notes:/app/notes" \
  -v "$(pwd)/playwright-state.json:/app/playwright-state.json" \
  rednotebot:latest
```

说明：

- Dockerfile 基于 `python:3.12-slim`
- 使用阿里云 PyPI 镜像：`https://mirrors.aliyun.com/pypi/simple/`
- 容器内通过 `uv sync --frozen --no-dev` 安装依赖
- 容器默认执行 `publish_xhs.py notes/sample_note.md --headless`
- 生产环境建议通过挂载 `notes/` 和 Playwright 状态文件的方式运行，不在容器内做交互式登录调试

如果你在 Windows PowerShell 中运行容器，建议使用下面的挂载写法：

```powershell
docker run --rm -it `
  -v "${PWD}\\notes:/app/notes" `
  -v "${PWD}\\playwright-state.json:/app/playwright-state.json" `
  rednotebot:latest
```

如果你希望在容器里显式传入运行命令，可以这样写：

```powershell
docker run --rm -it `
  -v "${PWD}\\notes:/app/notes" `
  -v "${PWD}\\playwright-state.json:/app/playwright-state.json" `
  rednotebot:latest `
  python publish_xhs.py notes/sample_note.md --cookies /app/playwright-state.json --headless
```

## 场景化选择器策略

脚本内置的默认选择器和场景检测集中在 `src/rednotebot/publisher.py` 的 `SCENE_SPECS`、`SELECTOR_SPECS` / `SelectorSet` 中。当前只维护长文模式所需动作。你也可以直接运行下面命令打印表格：

```powershell
uv run rednotebot-publish --print-selectors
```

默认动作映射如下：

| 场景 | 变量名 | 默认选择器 | 说明 |
| --- | --- | --- | --- |
| 登录页 | `login_button` | `button:has-text("登录"), text=APP扫一扫登录, text=扫码登录` | 登录入口，Cookie 失效时需要人工扫码 |
| 创作平台导航页 | `long_article_entry` | `text=写长文, text=长文` | 从导航页进入长文创作流 |
| 长文编辑页 | `title_input` | `input[placeholder*="标题"], textarea[placeholder*="标题"]` | 标题输入框 |
| 长文编辑页 | `body_editor` | `[contenteditable="true"], textarea[placeholder*="正文"]` | 正文编辑区域 |
| 长文编辑页 | `image_input` | `input[type="file"][accept*="image"], input[type="file"]` | 图片上传 input |
| 长文编辑页 | `publish_button` | `button:has-text("发布"), button:has-text("立即发布"), [role="button"]:has-text("发布")` | 发布按钮 |
| 长文编辑页 | `tag_suggestion` | `[class*="tag"], [class*="mention"], [class*="suggest"]` | 标签建议项，可选 |
| 发布结果页 | `publish_success_hint` | `text=/发布成功|笔记发布成功|发布完成/` | 发布完成提示 |

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
- 如果你准备长期稳定使用，建议把选择器和站点流程再抽成独立配置文件，并增加截图、重试、异常回滚和日志
- 当前仓库已经区分了“Windows 本地调试”和“Docker 生产执行”，但发布稳定性仍取决于你是否定期重新采集页面特征并校验选择器
