"""字体来源锁定：仓库内 fonts/ 存在时只用它，否则回退系统字体。

为什么要有这个模块：
    typst 的字体路径参数（--font-path / --ignore-system-fonts）必须同时加在
    **所有** 调用 typst 的地方 —— 编译、栅格化、封面度量、字体指纹。
    只要有一处漏掉，那一处就会看到不同的字体集合：
      * 栅格化漏了 → 墨迹校验的图和实际交付的 PDF 字形不一致
      * 字体指纹漏了 → artifact_id 与实际编译不符，verify 误报 mismatch
    所以统一走 font_args()，不要再在别处手写这两个参数。
"""
from __future__ import annotations

from pathlib import Path

# 仓库根目录 = ep/ 的上一级；字体固定放在 <repo>/fonts
FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"


def font_args() -> list[str]:
    """返回要追加到 typst 子命令后的字体参数。

    fonts/ 存在
        -> 锁定仓库内字体，并屏蔽系统字体。
           缺字体时 typst 会报 unknown font family，验证层随即升级为
           ENV_FONT_MISSING（exit 3），不会静默降级成替代字体。
    fonts/ 不存在
        -> 返回空列表，沿用系统字体，保证未随仓库分发字体的旧环境仍可构建。
    """
    if not FONTS_DIR.is_dir():
        return []
    return ["--font-path", str(FONTS_DIR), "--ignore-system-fonts"]
