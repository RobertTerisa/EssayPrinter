"""[2] AST 门禁：确定性，不可跳过；不调用模型。"""
from __future__ import annotations

import re
from pathlib import Path

from . import ast as astmod
from . import toc as tocmod
from .report import Issue, Report


def _norm_title(s: str) -> str:
    return re.sub(r"^\s*\d+(?:\.\d+)*[.、]?\s+", "", str(s)).strip()


def ingest(doc: dict, schema_path: Path | None = None,
           source_toc: dict | None = None, depth: int = 2) -> tuple[dict, Report]:
    """返回 (canonical_doc, report)。有 error 时不要继续渲染。"""
    report = Report()
    report.extend(astmod.validate_schema(doc, schema_path))
    report.extend(astmod.lint(doc))
    if report.errors:
        return doc, report
    extra: list[Issue] = []

    # P1.7 A：TOC 的唯一来源是 h 节点；源目录只提供 detected/title
    detected = "original" if (source_toc or {}).get("present") else "extracted"
    title = (source_toc or {}).get("title") or "目录"
    node = tocmod.inject_toc(doc, detected=detected, title=title, depth=depth)
    if node is None:
        extra.append(Issue("TOC_NOT_GENERATED", "warn",
                           "全文没有标题，未生成目录",
                           hint="若需要目录，请先给正文补 heading",
                           where="toc"))

    # 源目录与 heading 对不上：只 warn，最终以 heading 为准
    if (source_toc or {}).get("present") and node is not None:
        src_texts = {_norm_title(e.get("text", "")) for e in source_toc.get("entries", [])}
        h_texts = {e["text"] for e in node.get("entries", [])}
        if src_texts and not src_texts <= h_texts:
            extra.append(Issue("TOC_SOURCE_MISMATCH", "warn",
                               "源目录条目与 heading 不一致，已按 heading 重建",
                               hint="原始目录只用于 detected/title；条目以 heading 为准",
                               where="toc"))

    # 注入 TOC 后重新校验；warnings 以重校验结果为准
    rebuilt = Report()
    rebuilt.extend(astmod.lint(doc))
    rebuilt.extend(extra)
    return doc, rebuilt


def ingest_file(path: str | Path, schema_path: Path | None = None,
                source_toc: dict | None = None, depth: int = 2) -> tuple[dict, Report]:
    return ingest(astmod.load(path), schema_path=schema_path,
                  source_toc=source_toc, depth=depth)
