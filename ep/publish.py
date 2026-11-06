"""发布门禁：仅有「全有或全无」两种结果。

核心契约
--------
1. 自检不通过 -> **不发布任何交付物**（exit 1，只有诊断包）。
2. 交付物只有一条出口：`release/<标题>-<artifact_id>.pdf`，由本模块独占写入。
   标题按 `meta.title -> 第一个 h1 -> build_dir.name` 确定性回退，并做跨平台文件名清洗；
   `artifact_id` 始终保留在文件名末尾，用于防伪、防覆盖和 verify。
3. 产物自我标识：artifact_id = hash(AST) + hash(完整 tokens) + 字体指纹 + typst 版本，
   以及 AST/tokens/PDF 内容 hash，写入 PDF 元数据。
   这样「拿上一轮的旧 PDF 冒充本轮产物」在文件系统层面即可被检出。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ARTIFACT_KEY = "/EssayPrinterArtifactId"
AST_HASH_KEY = "/EssayPrinterAstHash"
TOKENS_HASH_KEY = "/EssayPrinterTokensHash"
FONT_FP_KEY = "/EssayPrinterFontFingerprint"
PDF_HASH_KEY = "/EssayPrinterPdfContentSha256"

# 文件名中标题部分的最大字符数（不含 artifact_id 与扩展名）。
# 限制长度是为了避免 Windows 长路径、某些同步盘和压缩工具的路径限制。
MAX_TITLE_CHARS = 60
_INVALID_FILENAME_CHARS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


def _cjson(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------------
# 交付物文件名
# ---------------------------------------------------------------------
def _display_title(doc: dict, build_dir: Path) -> str:
    """按 meta.title -> 第一个 h1 -> build_dir.name 取人类可读标题。"""
    meta = doc.get("meta") if isinstance(doc, dict) else None
    if isinstance(meta, dict):
        title = str(meta.get("title") or "").strip()
        if title:
            return title

    blocks = doc.get("blocks", []) if isinstance(doc, dict) else []
    for b in blocks:
        if not isinstance(b, dict) or b.get("type") != "h":
            continue
        try:
            level = int(b.get("level", 0))
        except (TypeError, ValueError):
            continue
        if level == 1:
            title = str(b.get("text") or "").strip()
            if title:
                return title

    return build_dir.name or "document"


def _safe_filename(title: str, max_chars: int = MAX_TITLE_CHARS) -> str:
    """把任意标题清洗成跨平台安全的文件名主体。

    规则：NFC 归一化；Windows 非法字符替换为 `-`；空白折叠；去掉首尾的
    空格/点/连字符；避开 Windows 保留设备名；最后按字符数截断。
    """
    s = unicodedata.normalize("NFC", str(title or ""))
    parts: list[str] = []
    for ch in s:
        if ch in _INVALID_FILENAME_CHARS:
            parts.append("-")
        elif ch.isspace():
            parts.append(" ")
        elif not ch.isprintable() or unicodedata.category(ch).startswith("C"):
            parts.append("-")
        else:
            parts.append(ch)

    s = "".join(parts)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip(" .-")

    if s.upper() in _WINDOWS_RESERVED_NAMES:
        s = "_" + s

    s = s[:max(1, int(max_chars))].rstrip(" .-")
    return s or "document"


def _manifest_doc_key(m: dict) -> str:
    """从 manifest 取稳定的文档 key；兼容旧版没有 doc_key 的 manifest。"""
    key = m.get("doc_key")
    if key:
        return str(key)
    inp = m.get("input")
    if not inp:
        return ""
    stem = Path(str(inp)).stem
    if stem.endswith(".ast"):
        stem = stem[:-4]
    return stem.replace(" ", "-") or "doc"


# ---------------------------------------------------------------------
# 产物标识
# ---------------------------------------------------------------------
def ast_hash(doc: dict) -> str:
    return hashlib.sha256(_cjson(doc)).hexdigest()


def tokens_hash(tokens: dict) -> str:
    return hashlib.sha256(_cjson(tokens)).hexdigest()


def font_fingerprint(tokens: dict, typst_bin: str = "typst") -> str:
    """尽量稳定地指纹化“本机实际可用的字体变体”。

    先 hash 主题声明的字体名；如果 typst CLI 可用，再把 `typst fonts --variants`
    中与这些字体相关的行一起 hash。这样换字体/换字重会改变 artifact_id。
    """
    names = sorted({
        v
        for f in (tokens.get("font") or {}).values()
        for v in (f.get("latin"), f.get("cjk"))
        if v
    })
    h = hashlib.sha256("\n".join(names).encode("utf-8"))
    if shutil.which(typst_bin):
        try:
            out = subprocess.run([typst_bin, "fonts", "--variants"],
                                 capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=15)
            for line in (out.stdout or "").splitlines():
                if any(n in line for n in names):
                    h.update(line.encode("utf-8"))
        except Exception:
            pass
    return h.hexdigest()[:16]


def pdf_content_hash(pdf: Path) -> str:
    """hash 页面内容流（不含元数据），用于检测“内容被换掉”。"""
    from pypdf import PdfReader
    r = PdfReader(str(pdf))
    h = hashlib.sha256()
    h.update(str(len(r.pages)).encode())
    for page in r.pages:
        c = page.get_contents()
        if c is not None:
            h.update(c.get_data())
    return h.hexdigest()


def artifact_id(doc: dict, tokens: dict, fonts_fp: str = "",
                typst_version: str = "") -> str:
    """由 AST + **完整 tokens 内容** + 字体指纹 + typst 版本派生，12 位十六进制。"""
    h = hashlib.sha256()
    h.update(_cjson(doc))
    h.update(_cjson(tokens))
    h.update(fonts_fp.encode("utf-8"))
    h.update(typst_version.encode("utf-8"))
    return h.hexdigest()[:12]


# ---------------------------------------------------------------------
# 发布
# ---------------------------------------------------------------------
def publish(build_dir: Path, doc: dict, tokens: dict, report: dict,
            release_dir: Path, fonts_fp: str = "", typst_version: str = "",
            manifest: dict | None = None, doc_key: str | None = None,
            owned_only: bool = False) -> Path | None:
    """自检通过才发布；否则返回 None，且 release 目录不发生任何变化。"""
    doc_key = doc_key or build_dir.name or "document"
    if not report.get("ok"):
        _mark_release_stale(release_dir, doc_key=doc_key, owned_only=owned_only)
        return None

    src = build_dir / "work" / "out.pdf"
    if not src.exists():
        return None                                    # 编译阶段就已失败

    ast_h = ast_hash(doc)
    tok_h = tokens_hash(tokens)
    pdf_h = pdf_content_hash(src)
    aid = artifact_id(doc, tokens, fonts_fp, typst_version)
    title = _display_title(doc, build_dir)
    target = release_dir / f"{_safe_filename(title)}-{aid}.pdf"
    tmp = target.with_name(target.name + ".part")

    release_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, tmp)
        _stamp(tmp, aid, ast_h, tok_h, fonts_fp, pdf_h)  # 写入产物标识 + hash
        os.replace(tmp, target)                         # 原子改名，绝不出现半成品
    except Exception:
        tmp.unlink(missing_ok=True)                     # 失败时清掉 .part，release 不留半成品
        raise

    # PDF + manifest 是必交付物；manifest 与 PDF 同名，放在 release/
    if manifest is not None:
        m = dict(manifest)
        m.update({
            "doc_key": doc_key,
            "display_title": title,
            "artifact_id": aid,
            "ast_sha256": ast_h,
            "tokens_sha256": tok_h,
            "font_fingerprint": fonts_fp,
            "pdf_content_sha256": pdf_h,
            "pdf": target.name,
        })
        (release_dir / f"{target.stem}.manifest.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    # 成功发布后，清掉同一文档的旧版本。标题会变，不能再靠文件名前缀判断，
    # 因此以 manifest 的 doc_key 为主，同时兼容旧版 `<slug>-<aid>.pdf` 命名。
    _purge_doc_versions(release_dir, doc_key=doc_key,
                        keep_names={target.name, target.stem + ".manifest.json"},
                        owned_only=owned_only)
    return target


def recycle_failed(build_dir: Path, attempt: int = 1) -> Path:
    """把失败候选产物移到 work/recycle/attempt-N/，不污染 release。"""
    work = build_dir / "work"
    dest = work / "recycle" / f"attempt-{attempt}"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("out.pdf", "doc.typ"):
        for base in (work, build_dir):
            src = base / name
            if src.exists():
                shutil.move(str(src), dest / name)
                break
    for d in ("preview", "raster"):
        for base in (work, build_dir):
            src = base / d
            if src.exists():
                shutil.move(str(src), dest / d)
                break
    return dest


def write_diagnostic(build_dir: Path, report: dict,
                     manifest: dict | None = None) -> Path:
    """失败时生成 diagnostic.zip：report/manifest/doc/typ/回收产物/环境信息。"""
    diag = build_dir / "diagnostic.zip"
    files: list[Path] = []
    for p in (build_dir / "report.json", build_dir / "manifest.json",
              build_dir / "work" / "doc.json", build_dir / "doc.json",
              build_dir / "work" / "doc.typ", build_dir / "doc.typ"):
        if p.exists():
            files.append(p)
    env = build_dir / "work" / "env.txt"
    env.parent.mkdir(parents=True, exist_ok=True)
    env.write_text(
        f"built_at={datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        + "\n".join(str(p) for p in sorted(build_dir.glob("**/*")) if p.is_file()),
        encoding="utf-8")
    files.append(env)
    with zipfile.ZipFile(diag, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(build_dir))
        for base in (build_dir / "work" / "recycle", build_dir / "recycle"):
            if base.exists():
                for p in base.glob("**/*"):
                    if p.is_file():
                        z.write(p, p.relative_to(build_dir))
    return diag


def _mark_release_stale(release_dir: Path, keep: Path | None = None,
                        doc_key: str | None = None,
                        owned_only: bool = False) -> None:
    """本轮失败：把上一轮遗留的交付物标记为过期，避免被冒充。

    - legacy（owned_only=False）：保持旧行为，处理 release 目录内全部 PDF；
    - workspace（owned_only=True）：只处理同名 manifest 存在且 doc_key 相同的 PDF；
      没有 manifest 的 PDF（例如用户自己的文件）一律不动。
    """
    if not release_dir.exists():
        return
    if owned_only and not doc_key:
        print("[publish] owned_only 模式缺少 doc_key，跳过 stale 标记", file=sys.stderr)
        return

    for pdf in release_dir.glob("*.pdf"):
        if pdf.name.endswith(".stale.pdf"):
            continue
        if keep is not None and pdf.resolve() == keep.resolve():
            continue

        man = pdf.with_name(pdf.stem + ".manifest.json")
        if owned_only:
            if not man.is_file():
                print(f"[publish] 跳过无 manifest 的 PDF: {pdf.name}", file=sys.stderr)
                continue
            try:
                m = json.loads(man.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                print(f"[publish] 跳过不可读 manifest 的 PDF: {pdf.name}: {e}",
                      file=sys.stderr)
                continue
            if not isinstance(m, dict) or _manifest_doc_key(m) != doc_key:
                continue

        target = pdf.with_name(pdf.stem + ".stale.pdf")
        try:
            os.replace(pdf, target)      # 跨平台覆盖；不要用 pdf.rename(target)
            # 同名 manifest 一起标记为 stale，避免它继续描述一个已过期 PDF
            if man.exists():
                os.replace(man, pdf.with_name(pdf.stem + ".stale.manifest.json"))
        except OSError as e:
            # 不抛 traceback：失败时仍要继续写 report/diagnostic
            print(f"[publish] 无法标记 stale: {pdf.name}: {e}", file=sys.stderr)


def _purge_doc_versions(release_dir: Path, doc_key: str,
                        keep_names: set[str] | None = None,
                        owned_only: bool = False) -> None:
    """成功发布后清理同一文档的旧交付物。

    - legacy（owned_only=False）：主路径读 manifest 的 doc_key；同时兼容旧版
      `<doc_key>-<12位artifact_id>[.stale].pdf/manifest.json` 命名。
    - workspace（owned_only=True）：只删除 manifest 明确引用的文件和 manifest
      自身；没有 manifest 的旧文件、用户 PDF 一律不动，也不按文件名正则清理。
    """
    if not release_dir.exists():
        return

    keep = keep_names or set()
    doomed: set[str] = set()

    for man in list(release_dir.glob("*.manifest.json")):
        if man.name in keep:
            continue
        try:
            m = json.loads(man.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(m, dict) or _manifest_doc_key(m) != doc_key:
            continue

        doomed.add(man.name)
        pdf_name = m.get("pdf")
        if pdf_name:
            doomed.add(str(pdf_name))
        if not owned_only:
            # legacy 兼容：manifest 与 PDF 同名；旧版 stale manifest 也能通过
            # basename 找到 stale PDF。
            base = man.name[:-len(".manifest.json")]
            doomed.add(base + ".pdf")

    if not owned_only:
        # 旧版命名没有 doc_key 时也要能清理；只匹配精确的 artifact_id 形状。
        legacy = re.compile(
            rf"^{re.escape(doc_key)}-[0-9a-f]{{12}}(?:\.stale)?\.(?:pdf|manifest\.json)$")
        for p in release_dir.iterdir():
            if p.name in keep:
                continue
            if legacy.match(p.name):
                doomed.add(p.name)

    for name in doomed:
        if not name or name in keep:
            continue
        # manifest 里的 pdf 字段理论上是文件名；防止异常/被篡改的 manifest
        # 通过 ../ 或绝对路径删到 release 目录之外。
        if Path(name).name != name:
            continue
        try:
            (release_dir / name).unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------
# 校验（用户侧可独立复核）
# ---------------------------------------------------------------------
def verify(pdf: Path, expected_doc: dict | None = None,
           expected_tokens: dict | None = None,
           fonts_fp: str = "", typst_version: str = "",
           source_toc: dict | None = None) -> tuple[str, str]:
    """复核 PDF。

    返回 (status, detail)：
      ok          -> artifact_id / AST / tokens / PDF 内容全部对得上
      provenance  -> 只确认是本工具产物；未传 expected_doc 时无法比对 AST
      mismatch    -> hash 不一致（内容被换 / 旧产物冒充）
      missing     -> 没有 EssayPrinter 元数据

    注意：build 存的是 **gate 之后 canonical AST** 的 hash；
    所以 verify --doc 必须先用同一套 gate.ingest()（含 source_toc）再算 hash。
    """
    import copy
    from . import gate

    try:
        from pypdf import PdfReader  # noqa: F401
    except ImportError:
        return "missing", "需要安装 pypdf"
    meta = _read_stamp(pdf)
    if not meta or not meta.get(ARTIFACT_KEY):
        return "missing", "该 PDF 不含 EssayPrinter 产物标识，不是本工具产出的交付物"

    stored_pdf = meta.get(PDF_HASH_KEY)
    if stored_pdf:
        actual = pdf_content_hash(pdf)
        if actual != stored_pdf:
            return "mismatch", f"PDF 内容 hash 不一致：stored={stored_pdf[:12]} actual={actual[:12]}"

    if expected_doc is None:
        return "provenance", f"artifact_id={meta[ARTIFACT_KEY]}（未传 --doc，仅验证来源元数据）"

    canonical, greport = gate.ingest(copy.deepcopy(expected_doc), source_toc=source_toc)
    if greport.errors:
        return "mismatch", f"gate 失败：{greport.to_llm_text()}"
    ast_h = ast_hash(canonical)
    if meta.get(AST_HASH_KEY) and meta[AST_HASH_KEY] != ast_h:
        return "mismatch", f"AST hash 不一致：stored={meta[AST_HASH_KEY][:12]} expected={ast_h[:12]}"
    if expected_tokens is None:
        return "ok", f"artifact_id={meta[ARTIFACT_KEY]}（AST 已比对；未传 tokens，未复算完整 artifact_id）"
    tok_h = tokens_hash(expected_tokens)
    if meta.get(TOKENS_HASH_KEY) and meta[TOKENS_HASH_KEY] != tok_h:
        return "mismatch", "tokens hash 不一致"
    expect_aid = artifact_id(canonical, expected_tokens, fonts_fp, typst_version)
    if expect_aid != meta[ARTIFACT_KEY]:
        return "mismatch", f"artifact_id 不一致：stored={meta[ARTIFACT_KEY]} expected={expect_aid}"
    return "ok", f"artifact_id={meta[ARTIFACT_KEY]}"


def _stamp(pdf: Path, aid: str, ast_h: str, tok_h: str,
           fonts_fp: str, pdf_h: str) -> None:
    """把 artifact_id 与 hash 写进 PDF 元数据（不改变页面内容）。"""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return
    reader = PdfReader(str(pdf))
    writer = PdfWriter(clone_from=reader)
    writer.add_metadata({
        "/Producer": "EssayPrinter",
        ARTIFACT_KEY: aid,
        AST_HASH_KEY: ast_h,
        TOKENS_HASH_KEY: tok_h,
        FONT_FP_KEY: fonts_fp,
        PDF_HASH_KEY: pdf_h,
    })
    with open(pdf, "wb") as fh:
        writer.write(fh)


def _read_stamp(pdf: Path) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError:
        return {}
    meta = PdfReader(str(pdf)).metadata or {}
    return {k: meta.get(k) for k in (ARTIFACT_KEY, AST_HASH_KEY, TOKENS_HASH_KEY,
                                     FONT_FP_KEY, PDF_HASH_KEY) if meta.get(k)}
