"""六项确定性自检。任何一项 error 都会中止交付并把报告回灌 LLM。"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from . import ast as astmod
from .fontenv import font_args
from .report import Issue, Report


def _run(cmd: list, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          cwd=str(cwd) if cwd else None)


def load_tokens(theme: str, themes_dir: Path) -> dict:
    return json.loads((themes_dir / f"{theme}.tokens.json").read_text(encoding="utf-8"))


_TOKEN_TOP_LEVEL_KEYS = frozenset({
    "name", "version", "mode", "numbers", "derivedFrom",
    "page", "font", "ink", "type", "para", "list", "grid",
})
_NUMBER_TYPES = frozenset({"lining", "old-style", "auto"})
_NUMBER_WIDTHS = frozenset({"proportional", "tabular", "auto"})
_TEXT_STYLES = frozenset({
    "body", "note", "caption", "header", "footer", "tocTitle", "toc1", "toc2",
    "coverKicker", "coverTitle", "coverSub", "coverLatin", "coverMeta",
})
_HEADING_STYLES = frozenset({f"h{i}" for i in range(1, 7)})


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _tokens_error(message: str, hint: str = "") -> Issue:
    return Issue("THEME_TOKENS_INVALID", "error", message,
                 hint=hint or "修正 themes/*.tokens.json；这是主题资产错误，不要改 AST",
                 where="themes/*.tokens.json", category="env")


def validate_tokens(tokens: dict) -> list[Issue]:
    """编译前校验 tokens 结构与必需键，避免拼错键值被误判成 AST 内容错误。"""
    issues: list[Issue] = []
    if not isinstance(tokens, dict):
        return [_tokens_error("tokens 顶层必须是 JSON 对象")]

    for key in sorted(set(tokens) - _TOKEN_TOP_LEVEL_KEYS):
        issues.append(Issue(
            "THEME_TOKENS_UNKNOWN_KEY", "warn",
            f"未知 tokens 顶层键：{key}",
            hint="未读取键不会生效；确认是否为拼写错误",
            where="themes/*.tokens.json", category="env"))

    def require(condition: bool, message: str) -> None:
        if not condition:
            issues.append(_tokens_error(message))

    version = tokens.get("version")
    require(isinstance(version, str) and bool(version.strip()),
            "version 必须是非空字符串")

    page = tokens.get("page")
    require(isinstance(page, dict), "page 必须存在且为对象")
    if isinstance(page, dict):
        require(isinstance(page.get("size"), str) and bool(page["size"].strip()),
                "page.size 必须是非空字符串")
        for key in ("width", "height", "bodyColumn"):
            require(_is_number(page.get(key)) and page[key] > 0,
                    f"page.{key} 必须是正数")
        for margin_key in ("margin", "coverMargin", "tocMargin"):
            margin = page.get(margin_key)
            require(isinstance(margin, dict), f"page.{margin_key} 必须存在且为对象")
            if isinstance(margin, dict):
                for side in ("t", "b", "l", "r"):
                    require(_is_number(margin.get(side)),
                            f"page.{margin_key}.{side} 必须是数字")

    font = tokens.get("font")
    require(isinstance(font, dict) and bool(font), "font 必须存在且为非空对象")
    if isinstance(font, dict):
        for family, spec in font.items():
            require(isinstance(spec, dict), f"font.{family} 必须是对象")
            if isinstance(spec, dict):
                for key in ("latin", "cjk"):
                    value = spec.get(key)
                    require(isinstance(value, str) and bool(value.strip()),
                            f"font.{family}.{key} 必须是非空字符串")

    type_tokens = tokens.get("type")
    require(isinstance(type_tokens, dict), "type 必须存在且为对象")
    if isinstance(type_tokens, dict):
        for style in sorted(_TEXT_STYLES | _HEADING_STYLES):
            spec = type_tokens.get(style)
            require(isinstance(spec, dict), f"type.{style} 必须存在且为对象")
            if not isinstance(spec, dict):
                continue
            require(_is_number(spec.get("size")) and spec["size"] > 0,
                    f"type.{style}.size 必须是正数")
            require(_is_number(spec.get("leading")) and spec["leading"] > 0,
                    f"type.{style}.leading 必须是正数")
            if style in _HEADING_STYLES:
                require(_is_number(spec.get("spaceBefore")) and spec["spaceBefore"] >= 0,
                        f"type.{style}.spaceBefore 必须是非负数字")
                require(_is_number(spec.get("spaceAfter")) and spec["spaceAfter"] >= 0,
                        f"type.{style}.spaceAfter 必须是非负数字")

    numbers = tokens.get("numbers")
    require(isinstance(numbers, dict), "numbers 必须存在且为对象")
    if isinstance(numbers, dict):
        require(numbers.get("type") in _NUMBER_TYPES,
                "numbers.type 必须是 lining / old-style / auto 之一")
        require(numbers.get("width") in _NUMBER_WIDTHS,
                "numbers.width 必须是 proportional / tabular / auto 之一")

    return issues


MIN_TYPST_VERSION = (0, 15, 1)


def check_typst_version(min_version: tuple[int, int, int] = MIN_TYPST_VERSION) -> list[Issue]:
    """编译前检查 Typst 版本；number-type / number-width 需要较新版本。"""
    if shutil.which("typst") is None:
        return []                     # 交给 check_compile 报 ENV_TYPST_MISSING
    proc = _run(["typst", "--version"])
    if proc.returncode != 0:
        return []
    match = re.search(r"typst\s+(\d+)\.(\d+)\.(\d+)", proc.stdout or "", re.IGNORECASE)
    if not match:
        return []
    found = tuple(int(x) for x in match.groups())
    if found < tuple(min_version):
        have = ".".join(str(x) for x in found)
        need = ".".join(str(x) for x in min_version)
        return [Issue(
            "ENV_TYPST_TOO_OLD", "error",
            f"Typst 版本过低：{have}，最低要求 {need}",
            hint="升级 Typst 到 0.15.1 或更高；这是环境问题，不要改 AST",
            where="typst", category="env")]
    return []


# ------------------------------------------------------------------ 1
def check_ast(doc: dict, schema_path: Path | None = None) -> list[Issue]:
    return astmod.validate_schema(doc, schema_path) + astmod.lint(doc)


# ------------------------------------------------------------------ 2
def check_toc(doc: dict) -> list[Issue]:
    """目录专检：数量 / 位置 / detected 取值（锚点一致性在 lint 里）。"""
    issues: list[Issue] = []
    blocks = doc.get("blocks", [])
    tocs = [(i, b) for i, b in enumerate(blocks) if b.get("type") == "toc"]
    if not tocs:
        if any(b.get("type") == "h" for b in blocks):
            issues.append(Issue("TOC_MISSING", "warn",
                                "文档有标题层级但没有生成目录",
                                hint="toc 应由 gate 从 headings 自动生成；不要由 agent 手写"))
        return issues
    idx, toc = tocs[0]
    first_h = next((i for i, b in enumerate(blocks) if b.get("type") == "h"), len(blocks))
    if idx > first_h:
        issues.append(Issue("TOC_POSITION", "error", "toc 节点位于第一个标题之后",
                            hint="toc 必须在封面之后、第一个 h1 之前"))
    if toc.get("detected") not in {"original", "extracted"}:
        issues.append(Issue("TOC_DETECTED_INVALID", "error",
                            f"toc.detected 取值非法：{toc.get('detected')}"))
    return issues


# ------------------------------------------------------------------ 3
def check_compile(typ_path: Path, out_pdf: Path, raster_dir: Path,
                  preview_dir: Path | None = None, ppi: int = 144):
    """编译 + **始终**栅格化到 raster_dir；preview 只决定是否额外保留一份。

    校验（列边界溢出、空页）依赖栅格图，因此 raster 与 --preview 解耦：
    即使调用方没传 --preview，也必须生成 raster_dir。
    """
    issues: list[Issue] = []
    if shutil.which("typst") is None:
        issues.append(Issue("ENV_TYPST_MISSING", "error",
                            "未找到 typst 可执行文件",
                            hint="安装 typst 并加入 PATH；这是环境问题，不要改 AST",
                            category="env"))
        return issues, 0

    # 先清掉上一轮候选产物，避免编译失败时读到旧 PDF / 旧 PNG
    for p in (out_pdf,):
        if p.exists():
            p.unlink()
    if raster_dir.exists():
        shutil.rmtree(raster_dir)
    raster_dir.mkdir(parents=True, exist_ok=True)

    proc = _run(["typst", "compile", typ_path, out_pdf, *font_args()],
                cwd=typ_path.parent)
    if proc.returncode != 0:
        issues.append(Issue("COMPILE_FAILED", "error",
                            (proc.stderr or "").strip()[:2000],
                            hint="检查 doc.typ 语法：文本转义、label 重复或模板函数签名"))
        return issues, 0

    for line in (proc.stderr or "").splitlines():
        low = line.lower()
        if "unknown font" in low or "font family" in low:
            issues.append(Issue("ENV_FONT_MISSING", "error", line.strip(),
                                hint="字体未安装或名称拼错；这是环境问题，不要改 AST",
                                category="env"))

    # 始终栅格化到 work/raster；--preview 只是“保留一份给人看”
    raster_proc = _run(["typst", "compile", typ_path, raster_dir / "page-{p}.png",
                        "--format", "png", "--ppi", str(ppi), *font_args()],
                        cwd=typ_path.parent)
    if raster_proc.returncode != 0:
        issues.append(Issue("RASTER_FAILED", "error",
                            (raster_proc.stderr or "").strip()[:1000],
                            hint="栅格化失败会跳过溢出校验；先修编译/资源路径"))
    if preview_dir is not None and raster_dir.exists():
        preview_dir.mkdir(parents=True, exist_ok=True)
        for png in raster_dir.glob("page-*.png"):
            shutil.copy2(png, preview_dir / png.name)

    pages = 0
    try:
        from pypdf import PdfReader
        pages = len(PdfReader(str(out_pdf)).pages)
    except Exception:
        pass
    return issues, pages


def check_margin_overflow(png_dir: Path, margin_mm: float = 5.0,
                          ppi: int = 144, tol: float = 0.001) -> list[Issue]:
    """扫描四边不可打印区内是否有墨迹 —— 最可靠的排版溢出检测手段。"""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return [Issue("ENV_PIL_MISSING", "error",
                      "未安装 Pillow/numpy，无法执行页边溢出检测",
                      hint="pip install pillow numpy；这是环境问题，不要改 AST",
                      category="env")]

    band = max(1, round(margin_mm / 25.4 * ppi))
    issues: list[Issue] = []
    for png in sorted(png_dir.glob("page-*.png")):
        arr = np.asarray(Image.open(png).convert("L"))
        h, w = arr.shape
        bands = [arr[0:band, :], arr[h - band:, :], arr[:, 0:band], arr[:, w - band:]]
        ink = sum(int((b < 250).sum()) for b in bands)
        total = sum(b.size for b in bands)
        ratio = ink / total if total else 0.0
        if ratio > tol:
            issues.append(Issue("MARGIN_OVERFLOW", "error",
                                f"{png.name} 在 {margin_mm}mm 不可打印区检出墨迹（{ratio:.3%}）",
                                hint="缩小超宽图片 / 让长表格断行 / 缩短长 URL",
                                where=png.name))
    return issues


def check_layout_overflow(png_dir: Path, tokens: dict,
                          ppi: int = 144, max_depth_mm: float = 1.0) -> list[Issue]:
    """检查正文列 / 批注栏 / 外侧白边是否互相侵入。

    判据是“越界深度”：从允许的内容边界算起，墨迹必须深入禁区 > 1mm 才报错。
    这样 callout/quote 左边线、表格边框这种描边居中造成的 0.2–0.5mm 溢出会被忽略。
    只对“有批注栏竖线”的正文页生效，封面/目录页自动跳过。
    """
    try:
        from PIL import Image
        import numpy as np
        import re
    except ImportError:
        return [Issue("ENV_PIL_MISSING", "error",
                      "未安装 Pillow/numpy，无法执行列边界检测",
                      hint="pip install pillow numpy；这是环境问题，不要改 AST",
                      category="env")]

    page = tokens["page"]
    width_mm = float(page.get("width", 210))
    height_mm = float(page.get("height", 297))
    margin = page["margin"]
    body_mm = float(page["bodyColumn"])
    note = page["note"]
    note_w = float(note["width"])
    gap = float(note["gap"])
    outer = float(note.get("outer", max(0.0, margin["r"] - note_w - gap)))
    top_mm, bottom_mm = float(margin["t"]), float(margin["b"])
    px_per_mm = ppi / 25.4

    issues: list[Issue] = []
    for png in sorted(png_dir.glob("page-*.png")):
        m = re.search(r"page-(\d+)", png.stem)
        if not m:
            continue
        page_no = int(m.group(1))
        # 只有主题开启镜像时才区分奇偶页；固定右侧主题（mirror=false）恒用左侧版心。
        even = page_no % 2 == 0 and bool(page.get("mirror", True))

        body_left = margin["r"] if even else margin["l"]
        body_right = body_left + body_mm
        note_left = outer if even else width_mm - outer - note_w
        note_right = note_left + note_w
        rule_x = note_right if even else note_left

        # 只检查正文页：正文页应有批注栏竖线；封面/目录没有
        arr = np.asarray(Image.open(png).convert("L"))
        h, w = arr.shape
        rx = int(round(rule_x * px_per_mm))
        rule_band = max(2, int(round(1.0 * px_per_mm)))
        rule_cols = arr[:, max(0, rx - rule_band):min(w, rx + rule_band + 1)]
        if not (rule_cols < 200).any(axis=1).mean() > 0.8:
            continue

        y0, y1 = int(top_mm * px_per_mm), int((height_mm - bottom_mm) * px_per_mm)

        # (band_start, band_end, boundary, side, opposite)
        # side="left"  -> 允许内容在 boundary 右侧，越界深度 = boundary - x
        # side="right" -> 允许内容在 boundary 左侧，越界深度 = x - boundary
        # opposite 只用于 gap 带：离另一侧边界 <= max_depth 的墨迹归属另一栏，
        # 不能算本栏越界（否则代码块/表格 2pt 描边会被误判成对侧侵入）。
        checks: list[tuple[float, float, float, str, float | None]] = []
        if even:
            checks += [
                (0.0, outer, outer, "left", None),                        # 左侧外白边
                (note_right, body_left, note_right, "right", body_left),  # note 向右侵入 gap
                (note_right, body_left, body_left, "left", note_right),   # 正文向左侵入 gap
                (body_right, width_mm, body_right, "right", None),        # 右侧外边距
            ]
        else:
            checks += [
                (0.0, body_left, body_left, "left", None),                # 左侧外边距
                (body_right, note_left, body_right, "right", note_left),  # 正文向右侵入 gap
                (body_right, note_left, note_left, "left", body_right),   # note 向左侵入 gap
                (note_right, width_mm, note_right, "right", None),        # 右侧外白边
            ]

        for x0, x1, boundary, side, opposite in checks:
            if x1 <= x0:
                continue
            a, b = int(x0 * px_per_mm), int(x1 * px_per_mm)
            if b <= a:
                continue
            sub = arr[y0:y1, a:b].copy()
            # 排除竖线自身：用掩码涂白，不能用 np.delete（会打乱 xs 索引，
            # 让后续 a+xs 坐标整体左移，产生假越界）。
            ra = max(0, int((rule_x - 1.0) * px_per_mm) - a)
            rb = min(b - a, int((rule_x + 1.0) * px_per_mm) - a)
            if rb > ra:
                sub[:, ra:rb] = 255
            ys, xs = np.nonzero(sub < 250)
            if len(xs) == 0:
                continue
            abs_x = a + xs
            if opposite is not None:
                # gap 带归属判定：离另一侧边界不超过容差的墨迹，
                # 属于另一栏的描边/字身，不计入本侧越界深度。
                keep = np.abs(abs_x - opposite * px_per_mm) > max_depth_mm * px_per_mm
                abs_x = abs_x[keep]
                if len(abs_x) == 0:
                    continue
            boundary_px = boundary * px_per_mm
            if side == "left":
                depths = boundary_px - abs_x
            else:
                depths = abs_x - boundary_px
            depth_mm = float(depths.max()) / px_per_mm
            if depth_mm > max_depth_mm:
                issues.append(Issue(
                    "COLUMN_OVERFLOW", "error",
                    f"{png.name} 在 {x0:.1f}-{x1:.1f}mm 越界 {depth_mm:.2f}mm（>{max_depth_mm}mm）",
                    hint="图片/表格宽度不得超过正文列；旁注不得越出批注栏",
                    where=png.name))
    return issues


def check_empty_pages(png_dir: Path, tol: float = 0.0005) -> list[Issue]:
    """整页无墨迹 -> warn EMPTY_PAGE（封面/目录页也允许有内容，故只提示）。"""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return [Issue("ENV_PIL_MISSING", "error",
                      "未安装 Pillow/numpy，无法执行空页检测",
                      hint="pip install pillow numpy；这是环境问题，不要改 AST",
                      category="env")]
    issues: list[Issue] = []
    for png in sorted(png_dir.glob("page-*.png")):
        arr = np.asarray(Image.open(png).convert("L"))
        if float((arr < 250).mean()) < tol:
            issues.append(Issue("EMPTY_PAGE", "warn",
                                f"{png.name} 几乎没有墨迹，可能是空页",
                                where=png.name))
    return issues


# ------------------------------------------------------------------ 4
def check_fonts(pdf_path: Path) -> list[Issue]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return [Issue("PYPDF_MISSING", "warn", "未安装 pypdf，跳过字体嵌入检测")]
    issues: list[Issue] = []
    seen: set = set()
    for page in PdfReader(str(pdf_path)).pages:
        fonts = (page.get("/Resources") or {}).get("/Font") or {}
        for _, ref in fonts.items():
            f = ref.get_object()
            name = str(f.get("/BaseFont", "?"))
            if name in seen:
                continue
            seen.add(name)
            if not _is_embedded(f):
                issues.append(Issue("FONT_NOT_EMBEDDED", "error",
                                    f"字体未嵌入：{name}",
                                    hint="换可嵌入字体（当前 tokens：Source Han Serif SC / Noto Sans SC / Georgia / Segoe UI / Consolas），并确认 typst 找到字体文件"))
    return issues


def _is_embedded(font: dict) -> bool:
    if font.get("/Subtype") == "/Type3":
        return True
    desc = font.get("/FontDescriptor")
    descs = [desc.get_object()] if desc else []
    for d in font.get("/DescendantFonts") or []:
        dd = d.get_object().get("/FontDescriptor")
        if dd:
            descs.append(dd.get_object())
    return any(any(k in d for k in ("/FontFile", "/FontFile2", "/FontFile3"))
               for d in descs)


# ------------------------------------------------------------------ 5
def check_images(doc: dict, base_dir: Path, text_width_mm: float,
                 min_dpi: int = 300, hard_min: int = 150) -> list[Issue]:
    """base_dir 固定为 work/assets；figure.src 是相对 doc.json 目录的路径。"""
    try:
        from PIL import Image
    except ImportError:
        return [Issue("ENV_PIL_MISSING", "error",
                      "未安装 Pillow，无法执行图片 DPI 检测",
                      hint="pip install pillow；这是环境问题，不要改 AST",
                      category="env")]
    issues: list[Issue] = []
    for b in astmod.iter_blocks(doc):
        if b.get("type") != "figure" or not b.get("src"):
            continue
        rel = str(b["src"]).replace(chr(92), "/")
        p = (base_dir / rel).resolve()
        if not p.exists():
            issues.append(Issue("IMAGE_MISSING", "error", f"图片不存在：{b['src']}"))
            continue
        with Image.open(p) as im:
            px = im.size[0]
        width_mm = text_width_mm * (b.get("width_pct", 100) / 100)
        dpi = px / (width_mm / 25.4)
        if dpi < hard_min:
            issues.append(Issue("IMAGE_LOW_DPI", "error",
                                f"{b['src']} 有效分辨率仅 {dpi:.0f} dpi（<{hard_min}）",
                                hint="换更高分辨率原图，或缩小显示宽度"))
        elif dpi < min_dpi:
            issues.append(Issue("IMAGE_LOW_DPI", "warn",
                                f"{b['src']} 有效分辨率 {dpi:.0f} dpi（<{min_dpi}）",
                                hint="打印可用但偏软；截图类图片可接受"))
    return issues


# ------------------------------------------------------------------ 6
COVER_FIT_LABEL = "<ep-cover-fit>"


def check_cover_fit(typ_path: Path, tol_pt: float = 1.0) -> list[Issue]:
    """封面单页守卫：读主题在渲染期量出的封面"最小所需高度"与"可用高度"。

    cover 用 `v(1fr)` 做弹性留白，一旦内容比可用高度还高，Typst 不会让内容
    重叠，而是把溢出部分排到第 2 页，把目录 / 正文整体后移 —— 这种破版
    不能用栅格墨迹类检查发现，所以在渲染期由主题 `measure` 量好报上来。
    判为 warn：封面文字来自 AST 的 meta，agent 无权为版式改写正文。
    """
    if shutil.which("typst") is None or not typ_path.exists():
        return []

    # 0.15.1 起推荐 eval；query 已标记 deprecated，作兜底。
    proc = _run(["typst", "eval",
                 f"query({COVER_FIT_LABEL}).first().value",
                 "--in", typ_path.name, *font_args()], cwd=typ_path.parent)
    if proc.returncode != 0:
        proc = _run(["typst", "query", typ_path.name, COVER_FIT_LABEL,
                     "--field", "value", "--one", *font_args()],
                     cwd=typ_path.parent)
    if proc.returncode != 0:
        return [Issue("COVER_FIT_UNMEASURED", "warn",
                      "无法读取封面高度度量，封面单页守卫本次跳过",
                      hint="主题 cover() 应带 <ep-cover-fit> 度量；此项只影响提示，不影响交付",
                      where=typ_path.name, category="env")]

    try:
        value = json.loads((proc.stdout or "").strip() or "{}")
        need_pt = float(value["need_pt"])
        avail_pt = float(value["avail_pt"])
    except Exception:
        return [Issue("COVER_FIT_UNMEASURED", "warn",
                      "封面高度度量格式无法解析，封面单页守卫本次跳过",
                      hint="主题 cover() 的 metadata 应为 (need_pt:, avail_pt:)，不影响交付",
                      where=typ_path.name, category="env")]

    if need_pt <= avail_pt + tol_pt:
        return []
    mm = 72.0 / 25.4
    return [Issue("COVER_OVERFLOW", "warn",
                  f"封面内容需要 {need_pt / mm:.1f}mm，可用 {avail_pt / mm:.1f}mm，"
                  f"超出 {(need_pt - avail_pt) / mm:.1f}mm；溢出部分会被排到第 2 页，"
                  f"把目录 / 正文整体后移",
                  hint="缩短封面标题或副标题，或调小 themes 的 coverTitle / coverSub 字号与行距；"
                       "封面文字来自 AST meta，不得为凑版式改写正文",
                  where="cover")]


def pdf_text_stats(pdf_path: Path) -> dict:
    """页数 / 总字数 / 每页字数；字数 = 去掉空白后的字符数。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        return {}
    try:
        pages = PdfReader(str(pdf_path)).pages
        per_page = [len("".join((p.extract_text() or "").split())) for p in pages]
        return {"pages": len(per_page), "chars_total": sum(per_page),
                "chars_per_page": per_page}
    except Exception:
        return {}


# ------------------------------------------------------------------ 汇总
def run_all(doc: dict, work_dir: Path, project_root: Path,
            theme: str = "article-annotated", preview: bool = False) -> dict:
    """work_dir = build/<slug>/work；report.json 固定写到 build/<slug>/report.json。"""
    themes_dir = project_root / "themes"
    tokens = load_tokens(theme, themes_dir)

    issues: list[Issue] = validate_tokens(tokens) + check_typst_version()
    if any(i.severity == "error" and i.category == "env" for i in issues):
        report = Report(build_dir=str(work_dir.parent))
        report.extend(issues)
        report.write(work_dir.parent / "report.json")
        return report.to_dict()

    issues += check_ast(doc, project_root / "schema" / "ast.schema.json")
    issues += check_toc(doc)

    typ, pdf = work_dir / "doc.typ", work_dir / "out.pdf"
    raster_dir = work_dir / "raster"
    preview_dir = work_dir / "preview" if preview else None
    compile_issues, pages = check_compile(typ, pdf, raster_dir, preview_dir)
    issues += compile_issues

    if pdf.exists():
        issues += check_cover_fit(typ)
        issues += check_fonts(pdf)
    if raster_dir.exists():
        issues += check_margin_overflow(raster_dir)
        issues += check_layout_overflow(raster_dir, tokens)
        issues += check_empty_pages(raster_dir)
    # 资源目录固定为 work/assets；AST 里的 src 保持源相对路径
    issues += check_images(doc, work_dir / "assets", tokens["page"]["bodyColumn"])

    stats = pdf_text_stats(pdf) if pdf.exists() else {}
    if pdf.exists() and not stats:
        issues.append(Issue("STATS_UNAVAILABLE", "warn",
                            "无法统计页数/字数（pypdf 缺失或 PDF 解析失败）",
                            hint="安装 pypdf；stats 为空不影响交付", where="stats"))
    report = Report(pages=pages, stats=stats, build_dir=str(work_dir.parent))
    report.extend(issues)
    report.write(work_dir.parent / "report.json")
    return report.to_dict()
