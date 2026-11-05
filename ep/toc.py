"""目录（TOC）检测与工具生成。

核心原则：
  · agent 不写 toc；工具从 h 节点生成 entries。
  · 源目录只提供 detected/title 线索，页码/条目一律丢弃。
  · 页码 / 缩进 / 引导点属于样式，由 theme 决定，不进 AST。
  · 条目 anchor 必须等于 h.id。
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

TOC_TITLE_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*)?(目\s*录|目\s*次|contents?|table\s+of\s+contents)\s*[:：]?\s*$",
    re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<text>.+?)\s*#*\s*$")

# 「1.2 标题……12」「标题 .... 12」「• 标题   12」
ENTRY_WITH_PAGE_RE = re.compile(
    r"^\s*(?:[-*+•]\s+)?"
    r"(?P<label>.+?)"
    r"(?:\s*(?:\.{2,}|·{2,}|…{2,}|-{3,}|_{3,})\s*|\s{2,})"
    r"(?P<page>\d{1,4})\s*$")
MD_LINK_RE = re.compile(r"^\s*(?:[-*+]\s*)?\[(?P<text>[^\]]+)\]\((?P<href>#[^)\s]+)\)\s*$")
PLAIN_ENTRY_RE = re.compile(r"^\s*(?P<num>\d+(?:\.\d+)*)[.、]?\s+(?P<text>\S.{1,78})$")


def slugify(text: str, used: set[str] | None = None) -> str:
    """生成稳定、可读、跨语言安全的 anchor（中文保留）。"""
    s = unicodedata.normalize("NFKC", text).strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s).strip("-") or "sec"
    if used is None:
        return s
    base, i = s, 2
    while s in used:
        s = f"{base}-{i}"
        i += 1
    used.add(s)
    return s


def _leading_number(text: str) -> str | None:
    m = re.match(r"^(\d+(?:\.\d+)*)", text)
    return m.group(1) if m else None


def _level_of_number(num: str | None) -> int:
    return 1 if not num else num.count(".") + 1


def detect_toc(markdown: str, min_entries: int = 3) -> dict[str, Any]:
    """检测原文是否自带目录。返回 {present, title, entries, line_span}。"""
    lines = markdown.splitlines()
    for i, line in enumerate(lines):
        if not TOC_TITLE_RE.match(line):
            continue
        entries: list[dict] = []
        j, blank_run = i + 1, 0
        while j < len(lines):
            raw = lines[j]
            if not raw.strip():
                blank_run += 1
                if blank_run >= 2 and entries:
                    break
                j += 1
                continue
            blank_run = 0
            if HEADING_RE.match(raw) and entries:
                break

            m = MD_LINK_RE.match(raw)
            if m:
                t = m.group("text").strip()
                entries.append({"text": t,
                                "anchor": m.group("href").lstrip("#"),
                                "level": _level_of_number(_leading_number(t))})
                j += 1
                continue

            m = ENTRY_WITH_PAGE_RE.match(raw)
            if m:
                text = m.group("label").strip(" .·…-—_")       # ← page 组被丢弃
                num = _leading_number(text)
                entries.append({"text": text, "num": num,
                                "level": _level_of_number(num)})
                j += 1
                continue

            m = PLAIN_ENTRY_RE.match(raw)
            if m:
                entries.append({"text": m.group("text").strip(" .·…-—_"),
                                "num": m.group("num"),
                                "level": _level_of_number(m.group("num"))})
                j += 1
                continue

            if entries:
                break
            j += 1

        if len(entries) >= min_entries:
            return {"present": True,
                    "title": re.sub(r"^#+\s*", "", line).strip(),
                    "entries": entries,
                    "line_span": (i, j)}
    return {"present": False, "title": "目录", "entries": [], "line_span": (0, 0)}


def extract_outline(markdown: str, *, skip_span: tuple[int, int] = (0, 0),
                    depth: int = 2) -> list[dict]:
    """从标题层级提取大纲（情形 B）。"""
    lines = markdown.splitlines()
    start, end = skip_span
    used: set[str] = set()
    out: list[dict] = []
    for i, line in enumerate(lines):
        if start <= i < end:
            continue
        m = HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        if level > depth:
            continue
        text = m.group("text").strip()
        out.append({"text": text, "level": level,
                    "anchor": slugify(text, used)})
    return out


def _attach_anchors(entries: list[dict]) -> list[dict]:
    used: set[str] = set()
    return [{"text": e.get("text", ""),
             "level": e.get("level", 1),
             "anchor": e.get("anchor") or slugify(e.get("text", ""), used)}
            for e in entries]


def build_toc_node(markdown: str, depth: int = 2) -> dict | None:
    """统一入口：有目录则转换（剥离页码），无目录则提取；都不行返回 None。"""
    info = detect_toc(markdown)
    if info["present"]:
        return {"type": "toc",
                "title": info["title"] or "目录",
                "depth": depth,
                "detected": "original",
                "entries": _attach_anchors(info["entries"])}
    entries = extract_outline(markdown, depth=depth)
    if not entries:
        return None
    return {"type": "toc", "title": "目录", "depth": depth,
            "detected": "extracted", "entries": entries}


def build_toc_from_headings(doc: dict, detected: str = "extracted",
                            title: str = "目录", depth: int = 2) -> dict | None:
    """P1.7 A：TOC 的唯一权威来源是 h 节点，不是 LLM。"""
    from . import ast as astmod
    entries = [
        {"text": h.get("text", ""),
         "level": int(h.get("level", 1)),
         "anchor": h.get("id", "")}
        for h in astmod.headings(doc, depth=depth)
        if h.get("id")
    ]
    if not entries:
        return None
    return {"type": "toc", "title": title or "目录", "depth": depth,
            "detected": detected, "entries": entries}


def inject_toc(doc: dict, detected: str = "extracted",
               title: str = "目录", depth: int = 2) -> dict | None:
    """删掉 agent 写的所有 toc，按 headings 重建，并插到 blocks[0]。"""
    blocks = [b for b in doc.get("blocks", []) if b.get("type") != "toc"]
    node = build_toc_from_headings(doc, detected=detected, title=title, depth=depth)
    if node is not None:
        blocks.insert(0, node)
    doc["blocks"] = blocks
    return node


TOC_AGENT_RULES = """\
关于目录，你必须遵守以下规则：

1. 不要输出 toc 节点；工具会从 heading 自动生成目录。
2. 原文目录（包括它的页码、条目、引导点）不要作为普通 block 写进 AST；
   工具会丢弃源目录并从 heading 重建。
3. 每个 heading 必须有稳定、唯一的 id；heading.text 不含编号。
4. 正文里不要手写“图 4”“3.2 节”；用 {"ref": "<目标 id>"}。
5. 不要输出页码、缩进、引导点（......）等任何样式信息。
"""
