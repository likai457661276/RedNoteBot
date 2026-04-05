from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


@dataclass(slots=True)
class NoteContent:
    """
    存储从 Markdown 文件解析出的笔记结构化数据。
    
    Attributes:
        source_path: Markdown 文件的原始路径。
        title: 笔记标题（由 # 一级标题定义）。
        body: 笔记正文内容（由 ## 正文 段落定义）。
        tags: 标签列表（由 ## 标签 段落定义）。
        topics: 话题列表（由 ## 活动话题 或 ## 话题 段落定义）。
        images: 笔记中引用的图片文件路径列表。
    """
    source_path: Path
    title: str
    body: str
    tags: list[str]
    topics: list[str]
    images: list[Path]


def parse_markdown_note(note_path: str | Path) -> NoteContent:
    """
    解析指定路径的 Markdown 笔记文件。
    
    该方法会读取 Markdown 文件并识别以下结构：
    - # 一级标题: 作为笔记标题。
    - ## 正文: 提取该段落下的内容作为笔记主体。
    - ## 标签: 提取该段落下的内容并解析为标签列表。
    - ## 活动话题 / ## 话题: 提取并解析为话题列表。
    - ## 附加图片: 提取该段落中引用的图片路径。
    
    Args:
        note_path: Markdown 文件的路径。
        
    Returns:
        NoteContent: 包含解析后所有信息的对象。
        
    Raises:
        ValueError: 如果缺少一级标题或正文内容。
    """
    path = Path(note_path).expanduser().resolve()
    raw = path.read_text(encoding="utf-8")

    title = ""
    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    for line in raw.splitlines():
        heading = HEADING_RE.match(line.strip())
        if heading:
            level, text = heading.groups()
            if level == "#":
                title = text.strip()
                current_section = None
                continue
            if level == "##":
                current_section = text.strip()
                sections.setdefault(current_section, [])
                continue
        if current_section is not None:
            sections[current_section].append(line)

    if not title:
        raise ValueError("Markdown 缺少一级标题，例如：# 笔记标题")

    body = "\n".join(sections.get("正文", [])).strip()
    if not body:
        raise ValueError("Markdown 缺少正文内容，请提供 ## 正文 段落")

    tags = _parse_tags(sections.get("标签", []))
    topics = _parse_topics(sections.get("活动话题", []), sections.get("话题", []))
    images = _parse_images(path.parent, body, sections.get("附加图片", []))

    return NoteContent(
        source_path=path,
        title=title,
        body=body,
        tags=tags,
        topics=topics,
        images=images,
    )


def _parse_tags(lines: list[str]) -> list[str]:
    """
    从文本行中解析标签。
    
    支持以空格、逗号或中文逗号分隔的标签。如果标签不以 # 开头，会自动补全。
    
    Args:
        lines: 包含标签的文本行列表。
        
    Returns:
        list[str]: 处理后的标签列表。
    """
    tags: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or _is_separator_line(stripped):
            continue
        candidates = re.split(r"[\s,，]+", stripped)
        for candidate in candidates:
            normalized = candidate.strip()
            if not normalized or _is_separator_line(normalized):
                continue
            if not normalized.startswith("#"):
                normalized = f"#{normalized}"
            tags.append(normalized)
    return tags


def _parse_topics(*sections: list[str]) -> list[str]:
    """
    从多个段落中解析并合并话题。
    
    会自动去重并移除 # 前缀，返回纯净的话题名称。
    
    Args:
        *sections: 包含话题文本行的多个列表。
        
    Returns:
        list[str]: 合并并去重后的话题列表。
    """
    topics: list[str] = []
    seen: set[str] = set()
    for lines in sections:
        for line in lines:
            stripped = line.strip()
            if not stripped or _is_separator_line(stripped):
                continue
            candidates = re.split(r"[\s,，]+", stripped)
            for candidate in candidates:
                normalized = candidate.strip().lstrip("#").strip()
                if not normalized or _is_separator_line(normalized):
                    continue
                key = normalized.casefold()
                if key in seen:
                    continue
                topics.append(normalized)
                seen.add(key)
    return topics


def _is_separator_line(value: str) -> bool:
    """
    判断一行是否为 Markdown 分隔符（如 ---, ***, ___）。
    """
    return bool(re.fullmatch(r"[-*_]{3,}", value))


def _parse_images(base_dir: Path, body: str, extra_lines: list[str]) -> list[Path]:
    """
    从正文和附加图片段落中解析出图片文件路径。
    
    Args:
        base_dir: Markdown 文件所在的目录，用于解析相对路径。
        body: 笔记正文。
        extra_lines: 附加图片段落的文本行。
        
    Returns:
        list[Path]: 解析出的图片绝对路径列表。
    """
    image_paths: list[Path] = []
    seen: set[Path] = set()

    markdown_sources = [body, "\n".join(extra_lines)]
    for source in markdown_sources:
        for match in IMAGE_RE.findall(source):
            candidate = (base_dir / match).resolve()
            if candidate not in seen:
                image_paths.append(candidate)
                seen.add(candidate)
    return image_paths
