"""语义 AST 的定义与校验。

设计约束（违反即视为 bug）：
1. AST 只描述「这段内容是什么」，不描述「它长什么样」。
2. 图号/表号/章号一律由渲染器计算，AST 里不出现。
3. 交叉引用用 ref，不要在正文里手写「图 4」。
4. toc 节点禁止出现页码字段。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

# 任何一层出现这些键，都判定为「样式泄漏」
BANNED_KEYS = {
    "font", "fontFamily", "fontSize", "fontsize", "color", "fill",
    "size", "margin", "padding", "lineHeight", "leading", "align",
    "style", "css", "className", "indent", "weight",
    "width", "height", "position", "border", "background", "float",
}
BANNED_IN_TOC = {"page", "pageNumber", "pageno", "页码"}

# ------------------------------------------------------------------
# 字段白名单：只允许这些键；不在白名单内的键直接驳回。
# 注意：width_pct / side / depth / tone / ordered / lang 是“语义/相对布局”
# 字段，显式保留；绝对样式字段仍然由 BANNED_KEYS 拦截。
# ------------------------------------------------------------------
BLOCK_FIELDS: dict[str, set[str]] = {
    "h":         {"type", "level", "text", "id"},
    "p":         {"type", "runs"},
    "list":      {"type", "ordered", "items"},
    "quote":     {"type", "blocks"},
    "callout":   {"type", "tone", "blocks"},
    "figure":    {"type", "src", "id", "caption_runs", "width_pct"},
    "table":     {"type", "id", "caption_runs", "header", "rows"},
    "code":      {"type", "lang", "content"},
    "math":      {"type", "content", "id"},
    "note":      {"type", "side", "runs"},
    "toc":       {"type", "title", "depth", "detected", "entries"},
    "pagebreak": {"type"},
    "hr":        {"type"},
}
INLINE_FIELDS = {"t", "code", "strong", "em", "link", "ref", "fn", "math"}
META_FIELDS = {"title", "subtitle", "subtitle_latin", "author",
               "date", "source", "url", "lang"}
TOC_ENTRY_FIELDS = {"text", "level", "anchor"}
TOP_FIELDS = {"schema", "meta", "blocks"}
# Typst label 安全字符：中文/字母/数字/_/-/.；禁止空格、< > # $ [ ] 等
ID_RE = re.compile(r"^[\w.\-]+$", re.UNICODE)


from .report import Issue

# ---------------------------------------------------------------- 遍历
def iter_blocks(doc: dict) -> Iterable[dict]:
    """深度遍历所有块节点（含 list / callout / quote 的嵌套块）。"""
    for b in doc.get("blocks", []):
        yield b
        if b.get("type") == "list":
            for item in b.get("items", []):
                if isinstance(item, list):
                    yield from iter_blocks({"blocks": item})
                elif isinstance(item, dict):
                    yield from iter_blocks({"blocks": [item]})
        elif b.get("type") in {"callout", "quote"}:
            yield from iter_blocks(b)


def iter_inlines(block: dict) -> Iterable[dict]:
    for run in block.get("runs", []) or []:
        yield run


def iter_all_inlines(doc: dict) -> Iterable[dict]:
    """遍历 runs / caption_runs / 表格单元格里的所有 inline。"""
    for b in iter_blocks(doc):
        for run in b.get("runs", []) or []:
            yield run
        for run in b.get("caption_runs", []) or []:
            yield run
        if b.get("type") == "table":
            rows = [b.get("header") or []] + list(b.get("rows") or [])
            for row in rows:
                for cell in row:
                    if isinstance(cell, list):
                        yield from cell


def headings(doc: dict, depth: int = 6) -> list[dict]:
    return [b for b in iter_blocks(doc)
            if b.get("type") == "h" and b.get("level", 9) <= depth]


def toc_node(doc: dict) -> dict | None:
    for b in doc.get("blocks", []):
        if b.get("type") == "toc":
            return b
    return None


# ---------------------------------------------------------------- 校验
def _walk_keys(node: Any, where: str, issues: list[Issue]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in BANNED_KEYS:
                issues.append(Issue(
                    "AST_STYLE_LEAK", "error",
                    f"AST 中出现样式字段 `{k}`（{where}）",
                    hint="样式由 theme 决定；请删除该字段，改用语义字段（如 strong=True）",
                    where=where))
            _walk_keys(v, f"{where}.{k}", issues)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk_keys(v, f"{where}[{i}]", issues)


def _check_allowed(obj: dict, allowed: set[str], where: str,
                   issues: list[Issue]) -> None:
    for k in obj:
        if k in BANNED_KEYS:
            continue                       # 已由 _walk_keys 报 AST_STYLE_LEAK
        if k not in allowed:
            issues.append(Issue(
                "AST_UNKNOWN_FIELD", "error",
                f"AST 出现白名单外字段 `{k}`（{where}）",
                hint=f"只允许：{', '.join(sorted(allowed))}",
                where=where))


def _walk_inline_whitelist(run: Any, where: str, issues: list[Issue]) -> None:
    if not isinstance(run, dict):
        issues.append(Issue("AST_INLINE_INVALID", "error",
                            f"行内节点必须是对象（{where}）", where=where))
        return
    _check_allowed(run, INLINE_FIELDS, where, issues)
    if not any(k in run for k in ("t", "ref", "fn", "math")):
        issues.append(Issue("AST_INLINE_EMPTY", "error",
                            f"行内节点没有任何内容字段（{where}）",
                            hint="至少要有 t / ref / fn 之一", where=where))


def _walk_cell_whitelist(cell: Any, where: str, issues: list[Issue]) -> None:
    if isinstance(cell, str):
        return
    if not isinstance(cell, list):
        issues.append(Issue("AST_CELL_INVALID", "error",
                            f"表格单元格必须是 inline[] 或 string（{where}）", where=where))
        return
    for i, run in enumerate(cell):
        _walk_inline_whitelist(run, f"{where}[{i}]", issues)


def _walk_block_whitelist(b: Any, where: str, issues: list[Issue]) -> None:
    if not isinstance(b, dict):
        issues.append(Issue("AST_BLOCK_INVALID", "error",
                            f"块节点必须是对象（{where}）", where=where))
        return
    t = b.get("type")
    if t not in BLOCK_FIELDS:
        issues.append(Issue("AST_UNKNOWN_TYPE", "error",
                            f"未知块类型 `{t}`（{where}）", where=where))
        return
    _check_allowed(b, BLOCK_FIELDS[t], where, issues)

    for field in ("runs", "caption_runs"):
        for i, run in enumerate(b.get(field) or []):
            _walk_inline_whitelist(run, f"{where}.{field}[{i}]", issues)

    if t in {"quote", "callout"}:
        for i, child in enumerate(b.get("blocks") or []):
            _walk_block_whitelist(child, f"{where}.blocks[{i}]", issues)
    elif t == "list":
        for i, item in enumerate(b.get("items") or []):
            if not isinstance(item, list):
                issues.append(Issue("AST_LIST_ITEM_INVALID", "error",
                                    f"list.items[{i}] 必须是块数组", where=where))
                continue
            for j, child in enumerate(item):
                _walk_block_whitelist(child, f"{where}.items[{i}][{j}]", issues)
    elif t == "table":
        for i, cell in enumerate(b.get("header") or []):
            _walk_cell_whitelist(cell, f"{where}.header[{i}]", issues)
        for i, row in enumerate(b.get("rows") or []):
            if not isinstance(row, list):
                issues.append(Issue("AST_TABLE_ROW_INVALID", "error",
                                    f"table.rows[{i}] 必须是单元格数组", where=where))
                continue
            for j, cell in enumerate(row):
                _walk_cell_whitelist(cell, f"{where}.rows[{i}][{j}]", issues)
    elif t == "toc":
        for i, entry in enumerate(b.get("entries") or []):
            if not isinstance(entry, dict):
                issues.append(Issue("AST_TOC_ENTRY_INVALID", "error",
                                    f"toc.entries[{i}] 必须是对象", where=where))
                continue
            _check_allowed(entry, TOC_ENTRY_FIELDS, f"{where}.entries[{i}]", issues)


def check_whitelist(doc: Any) -> list[Issue]:
    """只放行白名单字段；未知字段直接 error。"""
    issues: list[Issue] = []
    if not isinstance(doc, dict):
        return [Issue("AST_NOT_OBJECT", "error", "AST 根节点必须是对象", where="$")]
    _check_allowed(doc, TOP_FIELDS, "$", issues)
    meta = doc.get("meta")
    if meta is not None:
        if not isinstance(meta, dict):
            issues.append(Issue("AST_META_INVALID", "error", "meta 必须是对象", where="$.meta"))
        else:
            _check_allowed(meta, META_FIELDS, "$.meta", issues)
    for i, b in enumerate(doc.get("blocks") or []):
        _walk_block_whitelist(b, f"$.blocks[{i}]", issues)
    return issues


def lint(doc: dict) -> list[Issue]:
    """不依赖 JSON Schema 的语义检查。"""
    issues: list[Issue] = []
    _walk_keys(doc, "$", issues)
    issues.extend(check_whitelist(doc))

    if not doc.get("blocks"):
        issues.append(Issue("AST_EMPTY", "error", "AST 没有任何块节点", where="$"))

    ids: dict[str, int] = {}
    for h in [b for b in iter_blocks(doc) if b.get("type") == "h"]:
        hid = h.get("id")
        if not hid:
            issues.append(Issue("AST_H_ID_MISSING", "error",
                                f"标题缺少 id：{str(h.get('text', ''))[:30]}",
                                hint="标题必须有稳定 id，供目录与交叉引用使用", where="h"))
            continue
        if not isinstance(hid, str) or not ID_RE.fullmatch(hid):
            issues.append(Issue("AST_ID_INVALID", "error",
                                f"标题 id 含非法字符：{hid!r}",
                                hint="id 只允许中文/字母/数字/_/-/.，不能有空格或 < > # $ [ ] 等",
                                where=f"#{hid}"))
            continue
        level = h.get("level")
        if not isinstance(level, int) or not (1 <= level <= 6):
            issues.append(Issue("AST_H_LEVEL_INVALID", "error",
                                f"heading.level 必须是 1–6：{level!r}",
                                hint="level 9 会渲染成 #h9 并导致 typst unknown variable",
                                where=f"#{hid}"))
            continue
        text = str(h.get("text", ""))
        if re.match(r"^\s*\d+(?:\.\d+)*[.、]?\s+", text):
            issues.append(Issue("AST_HEADING_HAS_NUMBER", "error",
                                f"标题 text 含手写编号：{text[:30]}",
                                hint="删除编号；编号由 Typst set heading(numbering) 自动生成",
                                where=f"#{hid}"))
        ids[hid] = ids.get(hid, 0) + 1
    for hid, n in ids.items():
        if n > 1:
            issues.append(Issue("AST_ID_DUP", "error", f"id 重复：{hid}", where=f"#{hid}"))

    # ---- 目录
    tocs = [b for b in doc.get("blocks", []) if b.get("type") == "toc"]
    if len(tocs) > 1:
        issues.append(Issue("TOC_MULTIPLE", "error", f"存在 {len(tocs)} 个 toc 节点，只允许一个",
                            where="toc"))
    toc = toc_node(doc)
    if toc is not None:
        for e in toc.get("entries", []):
            for k in BANNED_IN_TOC:
                if k in e:
                    issues.append(Issue(
                        "TOC_HAS_PAGE_NUMBER", "error",
                        f"toc 条目含页码字段 `{k}`：{str(e.get('text', ''))[:30]}",
                        hint="页码一律由 Typst 的 outline() 重算，必须丢弃原文页码", where="toc"))
            anchor = e.get("anchor")
            if anchor and (not isinstance(anchor, str) or not ID_RE.fullmatch(anchor)):
                issues.append(Issue(
                    "AST_ID_INVALID", "error",
                    f"toc anchor 含非法字符：{anchor!r}",
                    hint="anchor 必须是合法 heading id；gate 会重生成 toc", where="toc"))
        missing = [e.get("anchor") for e in toc.get("entries", [])
                   if e.get("anchor") and e.get("anchor") not in ids]
        if missing:
            issues.append(Issue(
                "TOC_MISMATCH", "warn",
                f"目录有 {len(missing)} 条无法匹配到标题：{missing[:5]}",
                hint="gate 会按 headings 重生成 entries；若仍出现说明 gate 未执行", where="toc"))

    # ---- 交叉引用
    target_ids = {b.get("id") for b in iter_blocks(doc)
                  if b.get("type") in {"figure", "table", "math"} and b.get("id")}
    for run in iter_all_inlines(doc):
        target = run.get("ref")
        if target and target not in ids and target not in target_ids:
            issues.append(Issue("REF_BROKEN", "error",
                                f"交叉引用指向不存在的目标：{target}", where="ref"))

    # ---- 图 / 表 / 代码 / 数学
    for b in iter_blocks(doc):
        t = b.get("type")
        if t in {"figure", "table"}:
            fid = b.get("id")
            if fid and (not isinstance(fid, str) or not ID_RE.fullmatch(fid)):
                issues.append(Issue(
                    "AST_ID_INVALID", "error",
                    f"{t} id 含非法字符：{fid!r}",
                    hint="id 只允许中文/字母/数字/_/-/.，不能有空格或 < > # $ [ ] 等",
                    where=t))
        if t == "figure":
            src = str(b.get("src", ""))
            if not src:
                issues.append(Issue("FIG_NO_SRC", "error", "figure 缺少 src", where="figure"))
            elif src.startswith(("http://", "https://")):
                issues.append(Issue("FIG_SRC_REMOTE", "error",
                                    f"figure.src 不支持远程图：{src[:60]}",
                                    hint="先下载到 doc.json 同目录，再用相对路径；Typst image() 不能取远程图",
                                    where="figure"))
            elif chr(92) in src:
                issues.append(Issue("AST_PATH_INVALID", "error",
                                    f"figure.src 必须用正斜杠 /，不能含反斜杠：{src[:60]}",
                                    hint="改成 media/image.png 这种正斜杠相对路径；Typst 不接受反斜杠路径",
                                    where="figure"))
            if not b.get("caption_runs"):
                issues.append(Issue("FIG_NO_CAPTION", "warn",
                                    f"figure 缺少图注：{b.get('src')}",
                                    hint="打印稿建议每张图都带图注，便于交叉引用", where="figure"))
            w = b.get("width_pct", 100)
            if not isinstance(w, (int, float)) or not (0 < w <= 100):
                issues.append(Issue("FIG_WIDTH_INVALID", "error",
                                    f"figure.width_pct 必须在 (0,100]：{w}", where="figure"))
        elif t == "table":
            header = b.get("header") or []
            rows = b.get("rows") or []
            if not isinstance(header, list) or not isinstance(rows, list):
                issues.append(Issue("AST_TABLE_SHAPE_INVALID", "error",
                                    "table.header/rows 必须是数组", where="table"))
                continue
            ncols = len(header) or (len(rows[0]) if rows and isinstance(rows[0], list) else 0)
            if ncols and header:
                for i, row in enumerate(rows):
                    if not isinstance(row, list) or len(row) != ncols:
                        issues.append(Issue(
                            "AST_TABLE_COLUMNS_MISMATCH", "error",
                            f"table.rows[{i}] 有 {len(row) if isinstance(row, list) else '?'} 格，表头是 {ncols} 格",
                            hint="每行列数必须与 header 列数一致，否则 Typst 会静默串列",
                            where="table"))
        elif t == "code" and not str(b.get("content", "")).strip():
            issues.append(Issue("CODE_EMPTY", "error", "code.content 不能为空", where="code"))
        elif t == "math" and not str(b.get("content", "")).strip():
            issues.append(Issue("MATH_EMPTY", "error", "math.content 不能为空", where="math"))
        elif t == "note" and b.get("side") not in (None, "outer", "inner"):
            issues.append(Issue("NOTE_SIDE_INVALID", "error",
                                f"note.side 只能是 outer/inner：{b.get('side')}", where="note"))
        elif t == "callout" and b.get("tone") not in (None, "note", "tip", "warn"):
            issues.append(Issue("CALLOUT_TONE_INVALID", "error",
                                f"callout.tone 只能是 note/tip/warn：{b.get('tone')}", where="callout"))
    return issues


def validate_schema(doc: dict, schema_path: str | Path | None = None) -> list[Issue]:
    """JSON Schema 校验；未安装 jsonschema 时静默跳过（只跑 lint）。"""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return []
    path = Path(schema_path or Path(__file__).resolve().parent.parent
                / "schema" / "ast.schema.json")
    if not path.exists():
        return []
    schema = json.loads(path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errs = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    return [Issue("SCHEMA_INVALID", "error",
                  f"{'/'.join(map(str, e.path)) or '$'}: {e.message}",
                  hint="按 JSON Schema 修正 AST 结构", where="schema")
            for e in errs]


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump(doc: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                          encoding="utf-8")
