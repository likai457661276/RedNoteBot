from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


@dataclass(slots=True)
class NoteContent:
    source_path: Path
    title: str
    body: str
    tags: list[str]
    topics: list[str]
    images: list[Path]


def parse_markdown_note(note_path: str | Path) -> NoteContent:
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
    return bool(re.fullmatch(r"[-*_]{3,}", value))


def _parse_images(base_dir: Path, body: str, extra_lines: list[str]) -> list[Path]:
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
