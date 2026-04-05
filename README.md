# RedNoteBot

`RedNoteBot` 是一个基于 Python 3.12、`uv` 和 Playwright 的小红书自动发布项目骨架。它从 `notes/` 目录读取 Markdown 模板和图片，解析标题、正文、标签与附加图片，然后驱动小红书网页版完成登录、填写内容、上传图片和发布。

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
│   ├── sample_note.md
│   └── images/
│       ├── demo-cover.jpg
│       └── demo-detail.jpg
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
  - `## 附加图片`（可选）
- 支持正文和附加图片区块中的 Markdown 图片语法，例如 `![说明](images/xxx.jpg)`
- 支持通过 Cookie 文件复用登录态
- 使用 Playwright 自动打开小红书创作中心并尝试发布笔记
- 将页面选择器集中在 `src/rednotebot/publisher.py` 中，便于后续替换

## Markdown 写法说明

示例：

```md
# 周末咖啡店探店分享

## 正文
这是一段正文。

正文里也可以直接插入图片引用：
![封面](images/demo-cover.jpg)

## 标签
#咖啡店探店 #上海周末 #拍照打卡

## 附加图片
![细节图](images/demo-detail.jpg)
```

约定说明：

- 一级标题 `#` 作为笔记标题
- `## 正文` 为必填
- `## 标签` 可选，支持空格、中文逗号、英文逗号分隔
- `## 附加图片` 可选
- 图片路径相对当前 Markdown 文件解析，例如 `notes/sample_note.md` 中的 `images/demo-cover.jpg` 会被解析为 `notes/images/demo-cover.jpg`

## uv 初始化与本地运行

1. 确保本机已安装 Python 3.12 和 `uv`
2. 安装依赖

```bash
uv sync
```

3. 安装 Playwright Chromium 浏览器

```bash
uv run playwright install chromium
```

4. 首次运行并登录

```bash
uv run python publish_xhs.py notes/sample_note.md --cookies playwright-state.json
```

首次执行时如果 Cookie 无效，脚本会等待你在打开的浏览器里手动完成登录；成功后会把最新 Cookie 保存到 `playwright-state.json`。

5. 打印当前脚本使用的选择器表

```bash
uv run python publish_xhs.py --print-selectors
```

## Docker 构建与运行

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
- 默认执行 `publish_xhs.py notes/sample_note.md`

## 选择器变量

脚本内置的默认选择器集中在 `src/rednotebot/publisher.py` 的 `SelectorSet` 中。你也可以直接运行下面命令打印表格：

```bash
uv run python publish_xhs.py --print-selectors
```

默认变量如下：

| 变量名 | 默认选择器 | 说明 |
| --- | --- | --- |
| `login_button` | `button:has-text("登录")` | 登录入口，Cookie 失效时需要人工扫码 |
| `new_note_button` | `button:has-text("发布笔记"), a:has-text("发布笔记"), div:has-text("发布笔记")` | 进入新建笔记页面 |
| `title_input` | `input[placeholder*="标题"], textarea[placeholder*="标题"]` | 标题输入框 |
| `body_editor` | `[contenteditable="true"], textarea[placeholder*="正文"]` | 正文编辑区域 |
| `image_input` | `input[type="file"][accept*="image"], input[type="file"]` | 图片上传 input |
| `publish_button` | `button:has-text("发布"), button:has-text("立即发布")` | 发布按钮 |
| `tag_suggestion` | `[class*="tag"]` | 标签建议项，可选 |
| `publish_success_hint` | `text=发布成功` | 发布完成提示 |

## 风险与补充说明

- 小红书网页结构变化频繁，选择器可能需要更新
- 某些账号登录、图片上传、标签联想和发布过程可能存在风控或弹窗，需要按实际页面补充处理逻辑
- 如果你准备长期稳定使用，建议把选择器和站点流程再抽成独立配置文件，并增加截图、重试、异常回滚和日志
