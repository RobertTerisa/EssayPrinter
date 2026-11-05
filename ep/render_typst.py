"""AST -> Typst 源码。

只做「结构 -> 文本」的翻译，不做任何样式决策；
所有样式查表来自 themes/<theme>.typ。

注：本文中反斜杠一律用 BS = chr(92) 表示，避免文档里的多层转义歧义。
"""
from __future__ import annotations

BS = chr(92)                                # 反斜杠
NL, CR = chr(10), chr(13)
_ESC = set('#$*_`<>@~[]') | {BS}            # Typst 标记模式下需要转义的字符


def _q(s: str) -> str:
    """转成 Typst 字符串字面量。"""
    return (s.replace(BS, BS * 2).replace('"', BS + '"')
             .replace(NL, BS + "n").replace(CR, ""))


def esc(s: str) -> str:
    """转义纯文本，避免被当成 Typst 标记。"""
    out = "".join(BS + c if c in _ESC else c for c in s)
    # 行首的列表/标题/术语标记（- + = / 以及 "1."）会触发重新解析
    if out and (out[0] in "-+=/" or (len(out) > 1 and out[0].isdigit() and out[1] == ".")):
        out = BS + out
    return out


def collect_ref_kinds(doc: dict) -> dict[str, str]:
    """ref 目标 id -> sec/fig/tbl；renderer 用它决定 xref 的 kind。"""
    from . import ast as astmod
    out: dict[str, str] = {}
    for h in astmod.headings(doc):
        if h.get("id"):
            out[h["id"]] = "sec"
    for b in astmod.iter_blocks(doc):
        if b.get("id") and b.get("type") == "figure":
            out[b["id"]] = "fig"
        if b.get("id") and b.get("type") == "table":
            out[b["id"]] = "tbl"
        if b.get("id") and b.get("type") == "math":
            out[b["id"]] = "eq"
    return out


def inline(runs, ref_kinds: dict[str, str] | None = None) -> str:
    out: list[str] = []
    ref_kinds = ref_kinds or {}
    for r in runs or []:
        if "ref" in r:
            target = r["ref"]
            kind = ref_kinds.get(target, "unknown")
            out.append(f'#xref("{kind}", <{target}>)')
        elif "fn" in r:
            out.append(f"#footnote[{esc(r['fn'])}]")
        elif "math" in r:
            # 行内数学不能写成 `$ ... $`（两侧留空格会被 Typst 当成块公式）；
            # 块公式由 block() 的 math 分支负责。
            out.append(f"${str(r['math']).strip()}$")
        elif "link" in r:
            label = r.get("t") or r["link"]
            out.append(f'#link("{_q(r["link"])}")[{esc(label)}]')
        elif r.get("code"):
            out.append(f'#raw("{_q(r.get("t", ""))}")')
        elif r.get("strong"):
            out.append(f'#strong[{esc(r.get("t", ""))}]')
        elif r.get("em"):
            out.append(f'#emph[{esc(r.get("t", ""))}]')
        else:
            out.append(esc(r.get("t", "")))
    return "".join(out)


def _cell(c, ref_kinds: dict[str, str] | None) -> str:
    if isinstance(c, list):
        return f"[{inline(c, ref_kinds)}]"
    return f"[{esc(str(c))}]"


def block(b: dict, indent: int = 0, ref_kinds: dict[str, str] | None = None) -> str:
    pad = "  " * indent
    t = b.get("type")

    if t == "h":
        lvl = int(b.get("level", 1))
        label = f" <{b['id']}>" if b.get("id") else ""
        return f"{pad}#h{lvl}[{esc(b.get('text', ''))}]{label}"

    if t == "p":
        return f"{pad}#para[{inline(b.get('runs'), ref_kinds)}]"

    if t == "list":
        fn = "numlist" if b.get("ordered") else "bulletlist"
        item_fn = "nitem" if b.get("ordered") else "bitem"
        parts: list[str] = []
        for item in b.get("items", []) or []:
            blocks = item if isinstance(item, list) else [item]
            inner: list[str] = []
            for x in blocks:
                if isinstance(x, dict) and "type" in x:
                    inner.append(block(x, indent + 2, ref_kinds))
                elif isinstance(x, dict):
                    inner.append(f"{'  ' * (indent + 2)}#para[{inline([x], ref_kinds)}]")
                else:
                    inner.append(f"{'  ' * (indent + 2)}#para[{esc(str(x))}]")
            parts.append(f"{pad}  #{item_fn}[{NL}" + NL.join(inner) + f"{NL}{pad}  ]")
        return f"{pad}#{fn}[{NL}" + NL.join(parts) + f"{NL}{pad}]"

    if t in {"quote", "callout"}:
        body = NL.join(block(x, indent + 1, ref_kinds) for x in b.get("blocks", []))
        if t == "callout":
            head = f'{pad}#callout(tone: "{b.get("tone", "note")}")[{NL}'
        else:
            head = f"{pad}#quote[{NL}"
        return head + body + f"{NL}{pad}]"

    if t == "figure":
        cap = inline(b.get("caption_runs"), ref_kinds)
        w = b.get("width_pct", 100)
        label = f" <{b['id']}>" if b.get("id") else ""
        return f'{pad}#fig("{_q(b.get("src", ""))}", width: {w}%, caption: [{cap}]){label}'

    if t == "table":
        header = b.get("header") or []
        rows = b.get("rows") or []
        cols = len(header) or (len(rows[0]) if rows else 1)
        cells: list[str] = []
        if header:
            cells.append("table.header(repeat: true, "
                         + ", ".join(_cell(c, ref_kinds) for c in header) + ")")
        for r in rows:
            cells.extend(_cell(c, ref_kinds) for c in r)
        cap = inline(b.get("caption_runs"), ref_kinds)
        label = f" <{b['id']}>" if b.get("id") else ""
        return f'{pad}#tbl(columns: {cols}, caption: [{cap}], {", ".join(cells)}){label}'

    if t == "code":
        return (f'{pad}#codeblock(lang: "{_q(b.get("lang", ""))}", '
                f'content: "{_q(b.get("content", ""))}")')

    if t == "math":
        # P3-3：带 id 时把 label 放在 matheq 的 body 内、紧贴 equation，
        # 这样 ref(<id>) 能拿到公式编号。
        label = f" <{b['id']}>" if b.get("id") else ""
        return f"{pad}#matheq[$ {b.get('content', '')} ${label}]"

    if t == "note":
        return f"{pad}#mnote[{inline(b.get('runs'), ref_kinds)}]"

    if t == "toc":
        return (f'{pad}#tocblock(title: "{_q(b.get("title", "目录"))}", '
                f'depth: {int(b.get("depth", 2))})')

    if t == "pagebreak":
        return f"{pad}#pagebreak()"

    if t == "hr":
        return f"{pad}#hrule()"

    return f'{pad}#unknown("{_q(str(t))}")'      # 未知类型不静默丢弃


def render(doc: dict, theme: str = "article-annotated",
           theme_import: str | None = None, asset_prefix: str = "") -> str:
    """theme_import: 生成的 doc.typ 里 import 的主题文件路径（默认 ./<theme>.typ）。

    asset_prefix: 图片资源相对 doc.typ 的前缀（例如 "assets/"）。
    AST 里的 figure.src 始终保存“相对 doc.json 所在目录的本地路径”，由渲染器统一前缀化；
    不支持 http(s) 远程图。
    """
    import copy
    from . import ast as astmod

    theme_import = theme_import or f"{theme}.typ"
    if asset_prefix:
        doc = copy.deepcopy(doc)
        for b in astmod.iter_blocks(doc):
            if b.get("type") == "figure" and b.get("src"):
                # P2-8：Typst 只接受正斜杠路径；这里再做一层兜底。
                src = str(b["src"]).replace(chr(92), "/")
                if not (src.startswith(("/", "http://", "https://"))
                        or src.startswith(asset_prefix)):
                    src = asset_prefix + src
                b["src"] = src
    ref_kinds = collect_ref_kinds(doc)
    meta = doc.get("meta", {})
    meta_lines = [
        f'    {k}: "{_q(str(meta[k]))}",'
        for k in ("title", "subtitle", "subtitle_latin", "author",
                  "date", "source", "url", "lang")
        if meta.get(k)
    ]
    out = [
        "// generated by EssayPrinter -- do not edit by hand",
        f'#import "{theme_import}": (article, cover, h1, h2, h3, h4, h5, h6, para,',
        "  bulletlist, numlist, quote, callout, fig, tbl, codeblock, mnote,",
        "  tocblock, hrule, xref, bitem, nitem, matheq, unknown)",
        "",
        "#show: article.with(",
        "  meta: (",
        *meta_lines,
        "  ),",
        ")",
        "",
        "#cover(meta: (",
        *meta_lines,
        "))",
        "",
    ]

    for b in doc.get("blocks", []):
        out.append(block(b, ref_kinds=ref_kinds))
        out.append("")
    return NL.join(out)
