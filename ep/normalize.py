"""[1] 归一化：确定性，不调用模型。"""
from __future__ import annotations

from pathlib import Path


class UnsupportedFormatError(ValueError):
    """输入格式不支持。exit 5。"""


class InputUnreadableError(ValueError):
    """文件存在但读不了 / 解析依赖缺失。exit 3。"""


MD_SUFFIXES = {".md", ".markdown"}
ALL2MD_SUFFIXES = {".html", ".htm", ".docx", ".pdf"}


def _all2md_to_markdown(src: Path) -> str:
    try:
        import all2md  # type: ignore
    except ImportError as e:
        raise InputUnreadableError(
            "未安装 all2md；请 pip install 'all2md[html,pdf,docx]'") from e
    try:
        return all2md.to_markdown(str(src))
    except Exception as e:
        raise InputUnreadableError(f"all2md 解析失败：{e}") from e


def normalize(src: str | Path, out: str | Path) -> list[str]:
    src = Path(src).resolve()
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower()

    if not src.exists():
        raise InputUnreadableError(f"输入不存在：{src}")

    if suffix in MD_SUFFIXES:
        # 透传必须逐字节一致：Windows 文本模式会把 LF 改写成 CRLF，
        # 因此用二进制复制，保证跨平台可复现。
        try:
            out.write_bytes(src.read_bytes())
        except (OSError, UnicodeError) as e:
            raise InputUnreadableError(f"读取 Markdown 失败：{e}") from e
        return []

    if suffix == ".pdf":
        # PDF 仅支持纯文本型：先确认有文字层，再交给 all2md。
        try:
            from pypdf import PdfReader
            text = "".join((p.extract_text() or "") for p in PdfReader(str(src)).pages[:3])
        except ImportError as e:
            raise InputUnreadableError("需要安装 pypdf 才能检测 PDF 文字层") from e
        except Exception as e:
            raise InputUnreadableError(f"读取 PDF 失败：{e}") from e
        if len(text.strip()) < 200:
            raise UnsupportedFormatError(
                "该 PDF 没有可用文字层（疑似扫描件），不在支持范围；请提供 md/html 或先 OCR")

    if suffix in ALL2MD_SUFFIXES:
        md = _all2md_to_markdown(src)
        try:
            # 固定 LF，避免 Windows 文本模式写成 CRLF，保证跨平台一致。
            with open(out, "w", encoding="utf-8", newline=chr(10)) as fh:
                fh.write(md)
        except OSError as e:
            raise InputUnreadableError(f"写入 Markdown 失败：{e}") from e
        return [f"all2md 已归一化 {suffix}；复杂表格/公式可能被拍平"]

    raise UnsupportedFormatError(f"不支持的输入格式：{suffix or '(无后缀)'}")
