"""ep 命令行入口。

流水线：[1] normalize（可选，agent 写 AST 前用） -> [2] gate -> [3] render -> [4] validate -> [5] publish
全部确定性；模型由工作区 LLM（DeepSeek Harness）提供。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import ast as astmod
from . import gate, render_typst, toc, validate, publish
from . import workspace as workspacemod
from .normalize import InputUnreadableError, UnsupportedFormatError, normalize
from .report import Issue, Report

ROOT = Path(__file__).resolve().parent.parent
BUILD_ROOT = ROOT / ".essayprinter" / "build"
RELEASE_ROOT = ROOT / ".essayprinter" / "release"


# ------------------------------------------------------------ 构建
def _typst_version() -> str:
    try:
        out = subprocess.run(["typst", "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=10)
        return (out.stdout or "").strip()
    except Exception:
        return ""


def _exit_code(report: dict) -> int:
    issues = report.get("issues", [])
    # env 只有 error 才升级为 exit 3；env warn（如 THEME_TOKENS_UNKNOWN_KEY）不阻断。
    if any(i.get("severity") == "error"
           and (i.get("category") == "env" or i.get("code", "").startswith("ENV_"))
           for i in issues):
        return 3
    if not report.get("ok"):
        return 1
    if not report.get("published_path"):
        return 1
    return 2 if report.get("counts", {}).get("warn", 0) else 0


def _fail_env(build_dir: Path, msg: str, manifest: dict | None = None) -> int:
    report = Report()
    report.add(Issue("ENV_INPUT_UNREADABLE", "error", msg, category="env"))
    report.write(build_dir / "report.json")
    if manifest is not None:
        (build_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    publish.write_diagnostic(build_dir, report.to_dict(), manifest)
    print(report.to_llm_text(), file=sys.stderr)
    return 3


def _preflight_output_dir(release_dir: Path) -> None:
    """确认 workspace 发布目录可创建且可写；不留下临时文件。"""
    release_dir.mkdir(parents=True, exist_ok=True)
    probe = release_dir / ".ep-write-test"
    try:
        probe.write_text("essayprinter write test\n", encoding="utf-8")
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass


def build(src: Path | None, out_pdf: Path | None, theme: str = "article-annotated",
          preview: bool = False, keep_work: bool = True,
          source_md: Path | None = None, workspace_config: Path | None = None,
          name: str | None = None) -> int:
    """只接受 agent 产出的 AST；工具链不调用模型。"""
    # P1-7：先初始化，避免 workspace 解析抛异常后 except 分支引用未定义变量。
    build_dir: Path | None = None
    release_dir: Path = RELEASE_ROOT
    owned_only = False
    article: workspacemod.ArticlePaths | None = None
    doc_key: str | None = None

    src_path = Path(src).resolve() if src is not None else None
    source_md_path = Path(source_md).resolve() if source_md is not None else None

    if workspace_config is None:
        if name is not None:
            print("用法错误：--name 必须与 --workspace-config 同时使用", file=sys.stderr)
            return 5
        if src_path is None:
            print("用法错误：legacy 模式必须提供 --from-ast", file=sys.stderr)
            return 5
        stem = src_path.stem[:-4] if src_path.stem.endswith(".ast") else src_path.stem
        slug = stem.replace(" ", "-") or "doc"
        build_dir = BUILD_ROOT / slug
        release_dir = RELEASE_ROOT
    else:
        if name is None:
            print("用法错误：--workspace-config 必须与 --name 同时使用", file=sys.stderr)
            return 5
        try:
            config = workspacemod.load_config(workspace_config)
            article = workspacemod.resolve_article(config, name, ROOT)
        except workspacemod.WorkspaceConfigError as e:
            print(f"workspace 配置错误：{e}", file=sys.stderr)
            return 5
        except workspacemod.WorkspaceUsageError as e:
            print(f"workspace 用法错误：{e}", file=sys.stderr)
            return 5
        except workspacemod.WorkspaceInputError as e:
            print(f"workspace 输入不可读：{e}", file=sys.stderr)
            return 3

        if src_path is not None and src_path != article.ast_path:
            print(
                "用法错误：workspace 模式下 AST 固定为 "
                f"{article.ast_path}，不能使用 {src_path}",
                file=sys.stderr,
            )
            return 5
        src_path = article.ast_path
        if source_md_path is None and article.normalized_path.exists():
            source_md_path = article.normalized_path.resolve()
        build_dir = article.build_dir
        release_dir = article.release_dir
        owned_only = True
        doc_key = article.doc_key

        try:
            _preflight_output_dir(release_dir)
        except OSError as e:
            try:
                build_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            report = Report()
            report.add(Issue(
                "ENV_OUTPUT_UNWRITABLE", "error",
                f"output_dir 不可写：{release_dir}：{e}",
                hint="检查输出目录权限、磁盘空间或换一个可写目录",
                where="output", category="env"))
            try:
                report.write(build_dir / "report.json")
            except OSError:
                pass
            print(report.to_llm_text(), file=sys.stderr)
            return 3

    src = src_path
    source_md = source_md_path
    assert build_dir is not None
    attempt = 1
    old_manifest = build_dir / "manifest.json"
    if old_manifest.exists():
        try:
            attempt = int(json.loads(old_manifest.read_text(encoding="utf-8")).get("attempts", 0)) + 1
        except Exception:
            attempt = 1
    work = build_dir / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    manifest = None
    # 输入 / 主题 / 图片资源准备全部放在 try 内（P1-3）：
    # 任何失败都应是 exit 3 的输入/环境错误，不能抛 traceback。
    try:
        if not src.is_file():
            raise InputUnreadableError(f"AST 不存在或不是文件：{src}")
        raw_doc = astmod.load(src)

        # 主题资源冻结到 work/，保证同一份构建目录可复现
        themes_dir = ROOT / "themes"
        for f in (f"{theme}.typ", f"{theme}.tokens.json"):
            shutil.copy2(themes_dir / f, work / f)

        # P0-1：只拷贝 AST 真正引用的图片，绝不整体复制 doc.json 所在目录。
        # 否则 doc.json 放在仓库根目录时，会把正在创建的 work/assets 自己递归
        # 拷进自己（.essayprinter/ 在 src.parent 内），直接崩溃。
        assets = work / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        for b in astmod.iter_blocks(raw_doc):
            if b.get("type") != "figure" or not b.get("src"):
                continue
            rel = Path(str(b["src"]).replace(chr(92), "/"))
            if rel.is_absolute() or str(b["src"]).startswith(("http://", "https://")):
                continue                     # 远程图由 lint 拦；绝对路径不复制
            src_file = (src.parent / rel).resolve()
            dest = (assets / rel).resolve()
            if assets.resolve() not in dest.parents:
                raise InputUnreadableError(
                    f"figure.src 越出 doc.json 所在目录：{b['src']}")
            if not src_file.is_file():
                continue                     # 交给 check_images / 编译阶段报 IMAGE_MISSING
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)

        workspace_manifest = None
        if article is not None:
            workspace_manifest = {
                "name": article.name,
                "slug": article.slug,
                "name_hash": article.name_hash,
                "build_dir": str(article.build_dir),
                "config_path": str(article.config.config_path),
                "config_sha256": article.config.config_sha256,
                "source_dir": str(article.config.source_dir),
                "output_dir": str(article.config.output_dir),
                "release_dir": str(article.release_dir),
            }
        manifest = {
            "input": str(src),
            "source_md": str(source_md) if source_md else None,
            "sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
            "attempts": attempt,
            "theme": theme,
            "theme_version": None,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "params": {"preview": preview, "from_ast": True},
            "doc_key": doc_key,
            "workspace": workspace_manifest,
        }

        source_toc = None
        if source_md is not None:
            source_toc = toc.detect_toc(source_md.read_text(encoding="utf-8"))
    except (InputUnreadableError, OSError) as e:
        return _fail_env(build_dir, f"输入/主题/资源不可读：{e}", manifest)
    except json.JSONDecodeError as e:
        # JSON 语法错误是内容错误（exit 1），不是环境错误（exit 3）。
        report = Report()
        report.add(Issue("AST_PARSE_FAILED", "error", f"doc.json 不是合法 JSON：{e}",
                         hint="修正 JSON 语法后重跑；不要把它当成环境问题",
                         where="input"))
        report.write(build_dir / "report.json")
        publish.write_diagnostic(build_dir, report.to_dict(), manifest)
        publish._mark_release_stale(release_dir, doc_key=doc_key, owned_only=owned_only)   # exit 1：本轮不得留下有效交付物
        return 1
    except Exception as e:
        return _fail_env(build_dir, f"输入不可读：{e}", manifest)

    try:
        doc, gate_report = gate.ingest(
            raw_doc, schema_path=ROOT / "schema" / "ast.schema.json", source_toc=source_toc)
    except Exception as e:
        report = Report()
        report.add(Issue("GATE_FAILED", "error", f"gate 异常：{e}"))
        report.write(build_dir / "report.json")
        (build_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        publish.write_diagnostic(build_dir, report.to_dict(), manifest)
        publish._mark_release_stale(release_dir, doc_key=doc_key, owned_only=owned_only)   # exit 1：本轮不得留下有效交付物
        return 1
    if gate_report.errors:
        gate_report.write(build_dir / "report.json")
        (build_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        publish.write_diagnostic(build_dir, gate_report.to_dict(), manifest)
        print(gate_report.to_llm_text(), file=sys.stderr)
        publish._mark_release_stale(release_dir, doc_key=doc_key, owned_only=owned_only)   # exit 1：本轮不得留下有效交付物
        return gate_report.exit_code(published=False)

    astmod.dump(doc, work / "doc.json")
    try:
        (work / "doc.typ").write_text(
            render_typst.render(doc, theme_import=f"./{theme}.typ",
                                asset_prefix="assets/"), encoding="utf-8")
        report = validate.run_all(doc, work, ROOT, theme=theme, preview=preview)
    except Exception as e:
        report = Report()
        report.add(Issue("PIPELINE_FAILED", "error", f"流水线异常：{e}"))
        report.write(build_dir / "report.json")
        report = report.to_dict()

    # gate 的 warn（TOC_SOURCE_MISMATCH / TOC_NOT_GENERATED）并入最终报告
    gate_warns = [i.as_dict() for i in gate_report.warns]
    if gate_warns and isinstance(report, dict) and report.get("issues") is not None:
        report["issues"].extend(gate_warns)
        report["counts"]["warn"] = report["counts"].get("warn", 0) + len(gate_warns)

    tokens = validate.load_tokens(theme, themes_dir)
    fonts_fp = publish.font_fingerprint(tokens)
    typst_version = _typst_version()
    manifest.update({
        "theme_version": tokens.get("version"),
        "fonts_fingerprint": fonts_fp,
        "typst_version": typst_version,
        "gate": {"ok": gate_report.ok(), "counts": gate_report.counts()},
        "report": {k: report.get(k) for k in ("ok", "pages", "counts", "stats")},
    })
    (build_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    published = None
    if report.get("ok"):
        # P1-4：publish() 的异常必须转成结构化 PUBLISH_FAILED，不能抛 traceback；
        # 否则 release 写权限/磁盘错误会绕过 report.json 与 diagnostic.zip。
        try:
            published = publish.publish(
                build_dir, doc, tokens, report, release_dir,
                fonts_fp=fonts_fp, typst_version=typst_version, manifest=manifest,
                doc_key=doc_key, owned_only=owned_only)
            if published is None:
                raise RuntimeError("work/out.pdf 不存在或 release 写入失败")
        except Exception as e:
            report["ok"] = False
            report.setdefault("issues", []).append({
                "code": "PUBLISH_FAILED", "severity": "error",
                "message": f"自检通过但发布失败：{e}",
                "hint": "检查 work/out.pdf、release/ 写权限与磁盘空间",
                "where": "publish", "category": "publish"})
            report["counts"]["error"] = report.get("counts", {}).get("error", 0) + 1
        else:
            report["published_path"] = str(published)
            report["artifact_id"] = published.stem.rsplit("-", 1)[-1]
            if out_pdf is not None:
                try:
                    out_pdf.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(published, out_pdf)
                except OSError as e:
                    report.setdefault("issues", []).append({
                        "code": "OUTPUT_COPY_FAILED", "severity": "warn",
                        "message": f"发布成功但复制 -o 失败：{e}",
                        "hint": "直接从 release/ 取 PDF，或换一个可写路径",
                        "where": "output", "category": "content"})
                    report["counts"]["warn"] = report.get("counts", {}).get("warn", 0) + 1

    if not report.get("ok"):
        publish._mark_release_stale(release_dir, doc_key=doc_key, owned_only=owned_only)
        publish.recycle_failed(build_dir, attempt)
        report["exit_code"] = _exit_code(report)
        (build_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        publish.write_diagnostic(build_dir, report, manifest)
    else:
        report["exit_code"] = _exit_code(report)
        (build_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if not keep_work:
            for d in ("raster", "preview"):
                p = work / d
                if p.exists():
                    shutil.rmtree(p)
            p = work / "out.pdf"
            if p.exists():
                p.unlink()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return _exit_code(report)


# ------------------------------------------------------------ 子命令
def cmd_normalize(args) -> int:
    try:
        warnings = normalize(Path(args.input).resolve(), Path(args.output).resolve())
    except UnsupportedFormatError as e:
        print(f"unsupported: {e}", file=sys.stderr)
        return 5
    except (InputUnreadableError, OSError) as e:
        print(f"input error: {e}", file=sys.stderr)
        return 3
    print(json.dumps({"output": str(Path(args.output).resolve()), "warnings": warnings},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_workspace(args) -> int:
    """只读解析工作区配置并输出路径；不创建目录、不写文件。"""
    if not args.workspace_config:
        print("用法错误：workspace 必须提供 --workspace-config", file=sys.stderr)
        return 5
    try:
        config = workspacemod.load_config(args.workspace_config)
        if args.name is not None:
            article = workspacemod.resolve_article(config, args.name, ROOT)
            payload = workspacemod.article_to_dict(article)
        else:
            if not config.source_dir.is_dir():
                raise workspacemod.WorkspaceInputError(
                    f"source_dir 不存在或不是目录：{config.source_dir}")
            try:
                articles = sorted(
                    (p.name for p in config.source_dir.iterdir() if p.is_dir()),
                    key=str.casefold,
                )
            except OSError as exc:
                raise workspacemod.WorkspaceInputError(
                    f"source_dir 不可读：{config.source_dir}") from exc
            payload = {
                "config": workspacemod.config_to_dict(config),
                "articles": articles,
            }
    except workspacemod.WorkspaceConfigError as e:
        print(f"workspace 配置错误：{e}", file=sys.stderr)
        return 5
    except workspacemod.WorkspaceUsageError as e:
        print(f"workspace 用法错误：{e}", file=sys.stderr)
        return 5
    except workspacemod.WorkspaceInputError as e:
        print(f"workspace 输入不可读：{e}", file=sys.stderr)
        return 3

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_gate(args) -> int:
    # P1-3：gate 是 agent 的预检入口，输入/结构错误也必须输出结构化 report，
    # 不能抛 traceback。
    try:
        doc = astmod.load(Path(args.input).resolve())
        source_toc = None
        if args.source_md:
            source_toc = toc.detect_toc(
                Path(args.source_md).resolve().read_text(encoding="utf-8"))
    except OSError as e:
        report = Report()
        report.add(Issue("ENV_INPUT_UNREADABLE", "error",
                         f"输入不可读：{e}", category="env"))
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 3
    except Exception as e:
        report = Report()
        report.add(Issue("GATE_FAILED", "error", f"AST 读取/解析失败：{e}",
                         hint="确认 doc.json 是合法 JSON，且结构符合 schema/ast.schema.json"))
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 1

    try:
        doc, report = gate.ingest(doc, schema_path=ROOT / "schema" / "ast.schema.json",
                                  source_toc=source_toc)
    except Exception as e:
        report = Report()
        report.add(Issue("GATE_FAILED", "error", f"gate 异常：{e}",
                         hint="AST 结构不合法；检查 blocks/runs/entries 是否为数组/对象"))
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 1

    if report.ok() and args.output:
        astmod.dump(doc, Path(args.output).resolve())
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.ok() else report.exit_code(published=False)

def cmd_check(args) -> int:
    build_dir = Path(args.input).resolve()
    work = build_dir / "work"
    doc = astmod.load(work / "doc.json")
    report = validate.run_all(doc, work, ROOT, theme=args.theme, preview=args.preview)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else report["exit_code"]


def cmd_verify(args) -> int:
    pdf = Path(args.pdf).resolve()
    doc = astmod.load(Path(args.doc).resolve()) if args.doc else None
    tokens = validate.load_tokens(args.theme, ROOT / "themes") if doc else None
    source_toc = None
    if args.source_md:
        source_toc = toc.detect_toc(Path(args.source_md).resolve().read_text(encoding="utf-8"))
    fonts_fp = publish.font_fingerprint(tokens) if tokens else ""
    typst_version = _typst_version()
    status, detail = publish.verify(
        pdf, expected_doc=doc, expected_tokens=tokens,
        fonts_fp=fonts_fp, typst_version=typst_version, source_toc=source_toc)
    print(f"{status}: {detail}")
    return 0 if status in {"ok", "provenance"} else 1


def cmd_toc(args) -> int:
    """调试用：把原文的目录判定结果打出来。"""
    md = Path(args.input).read_text(encoding="utf-8")
    node = toc.build_toc_node(md)
    print(json.dumps(node, ensure_ascii=False, indent=2))
    return 0


class _ArgParser(argparse.ArgumentParser):
    """argparse 默认用 exit 2 表示用法错误；这里改成 5，避免与“warn 且已发布”混淆。"""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(5)


def main(argv: list | None = None) -> int:
    p = _ArgParser(prog="ep", description="EssayPrinter CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="AST -> 门禁 -> 渲染 -> 自检 -> 发布")
    b.add_argument("--from-ast", default=None,
                   help="agent 产出的 doc.json；workspace 模式下可省略（默认 article_dir/doc.json）")
    b.add_argument("--source-md", default=None,
                   help="可选：源 Markdown，用于判断 toc.detected")
    b.add_argument("-o", "--output", default=None,
                   help="可选；省略时不复制用户侧文件，交付物以 release/ 为准")
    b.add_argument("--theme", default="article-annotated")
    b.add_argument("--preview", action="store_true")
    b.add_argument("--keep-work", action=argparse.BooleanOptionalAction, default=True,
                   help="失败时保留 work/ 诊断包；成功时可用 --no-keep-work 清理栅格/预览")
    b.add_argument("--workspace-config", default=None,
                   help="工作区配置 JSON；不传则保持旧的 release/ 行为")
    b.add_argument("--name", default=None,
                   help="文章名；必须与 --workspace-config 同时使用")
    b.set_defaults(func=lambda a: build(
        Path(a.from_ast) if a.from_ast else None,
        Path(a.output) if a.output else None,
        a.theme, a.preview, a.keep_work,
        Path(a.source_md) if a.source_md else None,
        Path(a.workspace_config) if a.workspace_config else None,
        a.name))

    w = sub.add_parser("workspace", help="解析工作区配置并打印路径")
    w.add_argument("--workspace-config", default=None,
                   help="工作区配置 JSON；必填，未传 -> exit 5")
    w.add_argument("--name", default=None)
    w.set_defaults(func=cmd_workspace)

    n = sub.add_parser("normalize", help="确定性归一化（不调模型）")
    n.add_argument("input")
    n.add_argument("-o", "--output", required=True)
    n.set_defaults(func=cmd_normalize)

    g = sub.add_parser("gate", help="AST 门禁预检（schema/白名单/TOC/ref）")
    g.add_argument("input")
    g.add_argument("--source-md", default=None)
    g.add_argument("-o", "--output", default=None)
    g.set_defaults(func=cmd_gate)

    c = sub.add_parser("check", help="只跑自检")
    c.add_argument("input", help="构建目录")
    c.add_argument("--theme", default="article-annotated")
    c.add_argument("--preview", action="store_true")
    c.set_defaults(func=cmd_check)

    v = sub.add_parser("verify", help="复核 PDF 的 artifact_id/hash")
    v.add_argument("pdf")
    v.add_argument("--doc", default=None, help="可选：用这份 AST（会先 gate）复算 artifact_id")
    v.add_argument("--source-md", default=None, help="可选：与 build 相同的源 Markdown，用于 gate")
    v.add_argument("--theme", default="article-annotated")
    v.set_defaults(func=cmd_verify)

    t = sub.add_parser("toc", help="调试目录识别")
    t.add_argument("input")
    t.set_defaults(func=cmd_toc)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
