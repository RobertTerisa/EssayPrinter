"""[报告] 统一 Issue / Report / 退出码 / LLM 回灌文本。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_WARN = 2
EXIT_ENV = 3
EXIT_USAGE = 5

ENV_PREFIX = "ENV_"


@dataclass
class Issue:
    code: str
    severity: str                 # error | warn | info
    message: str
    hint: str = ""
    where: str = ""
    category: str = "content"     # content | env | publish | info

    def as_dict(self) -> dict:
        return asdict(self)

    def __getitem__(self, key: str) -> Any:      # 兼容旧代码 issue["code"]
        return getattr(self, key)


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)
    pages: int = 0
    stats: dict[str, Any] = field(default_factory=dict)
    artifact_id: str | None = None
    published_path: str | None = None
    build_dir: str | None = None

    def add(self, issue: Issue) -> None:
        self.issues.append(issue)

    def extend(self, issues) -> None:
        self.issues.extend(issues)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warns(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warn"]

    def ok(self) -> bool:
        return not self.errors

    def has_warn(self) -> bool:
        return bool(self.warns)

    def exit_code(self, published: bool = False) -> int:
        # env 只有 error 才升级为 exit 3；env warn 不阻断交付。
        if any(i.severity == "error"
               and (i.category == "env" or i.code.startswith(ENV_PREFIX))
               for i in self.issues):
            return EXIT_ENV
        if self.errors:
            return EXIT_ERROR
        if not published:
            return EXIT_ERROR
        return EXIT_WARN if self.warns else EXIT_OK

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for i in self.issues if i.severity == s)
                for s in ("error", "warn", "info")}

    def to_dict(self) -> dict:
        # 预检（gate/check）没有 published_path，但 ok=true 时应是 exit 0，
        # 不能因为“未发布”就写成 1。
        if self.published_path is not None:
            exit_code = self.exit_code(published=True)
        elif self.ok():
            exit_code = EXIT_OK
        else:
            exit_code = self.exit_code(published=False)
        return {
            "schema": "essayprinter/report@1",
            "ok": self.ok(),
            "exit_code": exit_code,
            "pages": self.pages,
            "stats": self.stats,
            "artifact_id": self.artifact_id,
            "published_path": self.published_path,
            "build_dir": self.build_dir,
            "counts": self.counts(),
            "issues": [i.as_dict() for i in self.issues],
        }

    def to_llm_text(self, max_errors: int = 20, max_warns: int = 5) -> str:
        lines: list[str] = []
        errors = self.errors[:max_errors]
        warns = self.warns[:max_warns]
        if errors:
            lines.append("请只修复以下 error，不要重写无关内容：")
            for i in errors:
                hint = f"（建议：{i.hint}）" if i.hint else ""
                lines.append(f"- [{i.code}] {i.message}{hint}")
        if warns:
            lines.append("本轮 warn（可交付，但需要向用户说明）：")
            for i in warns:
                lines.append(f"- [{i.code}] {i.message}")
        return "\n".join(lines) or "没有 error/warn。"

    def write(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                     encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path) -> "Report":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        r = cls(pages=int(data.get("pages", 0)), stats=data.get("stats", {}),
                artifact_id=data.get("artifact_id"),
                published_path=data.get("published_path"),
                build_dir=data.get("build_dir"))
        r.issues = [Issue(**i) for i in data.get("issues", [])]
        return r
