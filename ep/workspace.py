"""工作区配置解析：ep.workspace.json -> 路径对象。

只读模块：不创建目录、不写文件、不调用 publish。
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

WORKSPACE_VERSION = 1
INPUT_SUFFIXES = {".md", ".markdown", ".html", ".htm", ".docx", ".pdf"}
NORMALIZED_NAME = "source.norm.md"
DEFAULT_AST_NAME = "doc.json"
SLUG_MAX_LENGTH = 64

_ALLOWED_CONFIG_KEYS = {"version", "source_dir", "output_dir"}
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_WINDOWS_INVALID_CHARS = set('*?"<>|')
_SLUG_INVALID_RE = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|／]+')
_SLUG_SPACE_RE = re.compile(r"\s+")
_SLUG_DASH_RE = re.compile(r"-{2,}")


class WorkspaceError(ValueError):
    """工作区错误基类。exit_code 由 cli 使用。"""

    exit_code = 5


class WorkspaceConfigError(WorkspaceError):
    """配置语法/字段/版本错误。exit 5。"""

    exit_code = 5


class WorkspaceInputError(WorkspaceError):
    """输入目录/文件不可读（含 source_dir/article_dir 不存在、符号链接逃逸）。exit 3。"""

    exit_code = 3


class WorkspaceUsageError(WorkspaceError):
    """CLI 用法、名称非法、多输入、--from-ast 与 ast_path 不一致。exit 5。"""

    exit_code = 5


@dataclass(frozen=True)
class WorkspaceConfig:
    version: int
    source_dir: Path
    output_dir: Path
    config_path: Path
    config_sha256: str


@dataclass(frozen=True)
class ArticlePaths:
    name: str
    slug: str
    name_hash: str
    doc_key: str
    article_dir: Path
    input_path: Path
    normalized_path: Path
    ast_path: Path
    build_dir: Path
    release_dir: Path
    config: WorkspaceConfig


def load_config(path: str | Path) -> WorkspaceConfig:
    """读取并校验配置；version 缺省为 1。"""
    config_path = Path(path).resolve()
    try:
        raw = config_path.read_bytes()
    except OSError as exc:
        raise WorkspaceConfigError(f"工作区配置不存在或不可读：{config_path}") from exc

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceConfigError(f"工作区配置不是合法 UTF-8 JSON：{config_path}") from exc

    if not isinstance(data, dict):
        raise WorkspaceConfigError("工作区配置顶层必须是 JSON 对象")

    unknown = sorted(set(data) - _ALLOWED_CONFIG_KEYS)
    if unknown:
        raise WorkspaceConfigError(
            "工作区配置包含未知字段：" + ", ".join(unknown))

    version = data.get("version", WORKSPACE_VERSION)
    if type(version) is not int or version != WORKSPACE_VERSION:
        raise WorkspaceConfigError(
            f"工作区配置 version 必须是整数 {WORKSPACE_VERSION}")

    source_value = _require_nonempty_string(data, "source_dir")
    output_value = _require_nonempty_string(data, "output_dir")

    base_dir = config_path.parent
    source_dir = (base_dir / source_value).resolve()
    output_dir = (base_dir / output_value).resolve()

    if output_dir.exists() and not output_dir.is_dir():
        raise WorkspaceConfigError(f"output_dir 存在但不是目录：{output_dir}")

    return WorkspaceConfig(
        version=version,
        source_dir=source_dir,
        output_dir=output_dir,
        config_path=config_path,
        config_sha256=hashlib.sha256(raw).hexdigest(),
    )


def validate_name(name: str) -> None:
    """拒绝空名、路径分隔符、..、盘符、Windows 保留名、非法字符、结尾点/空格。"""
    if not isinstance(name, str):
        raise WorkspaceUsageError("文章名必须是字符串")
    if not name or not name.strip() or name in {".", ".."}:
        raise WorkspaceUsageError(f"文章名非法：{name!r}")
    if "/" in name or "\\" in name or "／" in name:
        raise WorkspaceUsageError(f"文章名不能包含路径分隔符：{name!r}")
    if ":" in name:
        raise WorkspaceUsageError(f"文章名不能包含冒号或盘符：{name!r}")
    if any(ch in _WINDOWS_INVALID_CHARS for ch in name):
        raise WorkspaceUsageError(f"文章名包含 Windows 非法字符：{name!r}")
    if any(unicodedata.category(ch).startswith("C") for ch in name):
        raise WorkspaceUsageError(f"文章名包含控制字符：{name!r}")
    if name.endswith((" ", ".")):
        raise WorkspaceUsageError(f"文章名不能以空格或点结尾：{name!r}")

    device_stem = name.split(".", 1)[0].rstrip(" .").upper()
    if device_stem in _WINDOWS_RESERVED_NAMES:
        raise WorkspaceUsageError(f"文章名是 Windows 保留设备名：{name!r}")


def slugify(name: str) -> str:
    """NFC + 非法字符替换 + 空白折叠 + 截断；保留中文。"""
    text = unicodedata.normalize("NFC", str(name))
    text = _SLUG_INVALID_RE.sub("-", text)
    text = _SLUG_SPACE_RE.sub("-", text)
    text = _SLUG_DASH_RE.sub("-", text).strip(" .-")
    text = text[:SLUG_MAX_LENGTH].strip(" .-")
    return text or "doc"


def find_inputs(article_dir: Path) -> list[Path]:
    """扫描顶层输入候选，排除 NORMALIZED_NAME。"""
    article_dir = Path(article_dir)
    if not article_dir.is_dir():
        raise WorkspaceInputError(f"文章目录不存在或不是目录：{article_dir}")
    try:
        entries = list(article_dir.iterdir())
    except OSError as exc:
        raise WorkspaceInputError(f"文章目录不可读：{article_dir}") from exc

    candidates = [
        p for p in entries
        if p.is_file()
        and p.suffix.lower() in INPUT_SUFFIXES
        and p.name.casefold() != NORMALIZED_NAME.casefold()
    ]
    return sorted(candidates, key=lambda p: p.name.casefold())


def resolve_article(
    config: WorkspaceConfig,
    name: str,
    project_root: Path,
) -> ArticlePaths:
    """校验 name、扫描唯一输入、推导 build_dir/release_dir。"""
    validate_name(name)

    source_dir = config.source_dir.resolve()
    if not source_dir.is_dir():
        raise WorkspaceInputError(f"source_dir 不存在或不是目录：{source_dir}")

    article_dir = source_dir / name
    try:
        resolved_article = article_dir.resolve(strict=True)
    except OSError as exc:
        raise WorkspaceInputError(f"文章目录不存在或不可读：{article_dir}") from exc
    if not resolved_article.is_dir():
        raise WorkspaceInputError(f"文章目录不是目录：{article_dir}")
    if resolved_article.parent != source_dir:
        raise WorkspaceInputError(
            f"文章目录不能通过符号链接/快捷方式越出 source_dir：{article_dir}")

    inputs = find_inputs(resolved_article)
    if not inputs:
        raise WorkspaceInputError(f"文章目录中没有输入文件：{resolved_article}")
    if len(inputs) > 1:
        candidates = "\n".join(f"  - {p}" for p in inputs)
        raise WorkspaceUsageError(
            f"文章目录顶层只能有一个输入文件，实际找到 {len(inputs)} 个：\n{candidates}")

    name_hash = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    slug = slugify(name)
    project_root = Path(project_root).resolve()

    return ArticlePaths(
        name=name,
        slug=slug,
        name_hash=name_hash,
        doc_key=name,
        article_dir=resolved_article,
        input_path=inputs[0],
        normalized_path=resolved_article / NORMALIZED_NAME,
        ast_path=resolved_article / DEFAULT_AST_NAME,
        build_dir=project_root / ".essayprinter" / "build" / f"{slug}-{name_hash}",
        release_dir=config.output_dir / name,
        config=config,
    )


def config_to_dict(config: WorkspaceConfig) -> dict:
    """供 workspace 子命令与 manifest 使用。"""
    return {
        "version": config.version,
        "source_dir": str(config.source_dir),
        "output_dir": str(config.output_dir),
        "config_path": str(config.config_path),
        "config_sha256": config.config_sha256,
    }


def article_to_dict(article: ArticlePaths) -> dict:
    """供 workspace 子命令输出。"""
    return {
        "name": article.name,
        "slug": article.slug,
        "name_hash": article.name_hash,
        "doc_key": article.doc_key,
        "article_dir": str(article.article_dir),
        "input_path": str(article.input_path),
        "normalized_path": str(article.normalized_path),
        "ast_path": str(article.ast_path),
        "build_dir": str(article.build_dir),
        "release_dir": str(article.release_dir),
        "config": config_to_dict(article.config),
    }


def _require_nonempty_string(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceConfigError(f"工作区配置 {key} 必须是非空字符串")
    return value
