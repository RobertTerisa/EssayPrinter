# 字体来源与授权记录

本仓库 `fonts/` 目录随附 EssayPrinter 渲染所需的全部字体文件。
所有文件均为**上游发行版原件，未做任何修改**（未子集化、未改名、未重新打包）。

## 为什么需要这个文件

- **SIL Open Font License 1.1（OFL-1.1）** 要求再分发时保留字体版权声明与许可证全文；
- **Apache License 2.0** 第 4 条要求保留版权声明与许可声明；
- 记录版本与校验值，便于确认「字体变更导致 `artifact_id` 变化」是否预期
  （`ep/publish.py` 的 `font_fingerprint()` 依赖实际可用的字体集合）。

## 一、主题实际用到的字体族

权威来源：`themes/article-annotated.tokens.json` 的 `font` 段。
`themes/article-annotated.typ` 通过 `font-of(key)` 只从该文件读取字体名。

| tokens 键 | latin 槽位 | cjk 槽位 | 使用位置 |
|---|---|---|---|
| `body` | Source Serif 4 | Source Han Serif SC | 正文 |
| `sans` | Noto Sans | Noto Sans SC | 全部标题 h1–h6、目录标题、封面 |
| `quote` | Source Serif 4 | Source Han Serif SC | 引文（斜体） |
| `mono` | JetBrains Mono | Noto Sans SC | 代码块 |

## 二、文件清单

| 文件 | 字族（Typst 中的名称） | 字重/样式 | 版本 | 大小 | 许可证 |
|---|---|---|---|---|---|
| `SourceSerif4-Regular.otf` | Source Serif 4 | Regular | 4.005 | 0.23 MB | OFL-1.1 |
| `SourceSerif4-It.otf` | Source Serif 4 | Italic | 4.005 | 0.16 MB | OFL-1.1 |
| `SourceSerif4-Semibold.otf` | Source Serif 4 | Semibold | 4.005 | 0.24 MB | OFL-1.1 |
| `SourceHanSerifSC-VF.otf` | Source Han Serif SC | 可变字体（全字重） | 2.003 | 52.81 MB | OFL-1.1 |
| `NotoSans-Regular-2.ttf` | Noto Sans | Regular | 1.04 | 0.38 MB | Apache-2.0 |
| `NotoSans-Bold-5.ttf` | Noto Sans | Bold | 1.04 | 0.38 MB | Apache-2.0 |
| `NotoSansSC-VF.ttf` | Noto Sans SC | 可变字体（全字重） | 2.04 | 16.95 MB | OFL-1.1 |
| `JetBrainsMono-Regular.ttf` | JetBrains Mono | Regular | 2.304 | 0.26 MB | OFL-1.1 |

合计 8 个文件，约 72 MB。

字体来源只有一处：`ep/fontenv.py` 在构建时自动注入
`--font-path <repo>/fonts --ignore-system-fonts`，因此构建**不依赖系统字体**。

## 三、逐个字体的版权声明与上游

### Source Serif 4

- 文件：`SourceSerif4-Regular.otf`、`SourceSerif4-It.otf`、`SourceSerif4-Semibold.otf`
- 版权：© 2014-2023 Adobe (http://www.adobe.com/), with Reserved Font Name 'Source'.
- 商标：Source is a trademark of Adobe in the United States and/or other countries.
- 许可证：SIL Open Font License 1.1 → `licenses/license ofl1.1.txt`
- 上游：https://github.com/adobe-fonts/source-serif（发行包 `source-serif-4.005_Desktop`）

### Source Han Serif SC（思源宋体）

- 文件：`SourceHanSerifSC-VF.otf`
- 版权：© 2017-2024 Adobe (http://www.adobe.com/), with Reserved Font Name 'Source'.
- 商标：Source is a trademark of Adobe in the United States and/or other countries.
- 许可证：SIL Open Font License 1.1 → `licenses/license ofl1.1.txt`
- 上游：https://github.com/adobe-fonts/source-han-serif
- 备注：文件内部 family 名为 `Source Han Serif SC VF`，Typst 会自动去掉 `VF` 后缀，
  因此 `tokens.json` 中写作 `Source Han Serif SC`。这是正常现象，不要手改 tokens。

### Noto Sans

- 文件：`NotoSans-Regular-2.ttf`、`NotoSans-Bold-5.ttf`
- 版权：Copyright 2012 Google Inc. All Rights Reserved.
- 许可证：Apache License 2.0 → `licenses/license Notosans.txt`
- 上游：Google Fonts / https://github.com/notofonts
- 备注：**与 `Noto Sans SC` 不是同一字体，许可证也不同**（本项 Apache-2.0，
  `Noto Sans SC` 为 OFL-1.1），请勿混淆。

### Noto Sans SC

- 文件：`NotoSansSC-VF.ttf`
- 版权：© 2014-2021 Adobe (http://www.adobe.com/), with Reserved Font Name 'Source'.
- 商标：Source is a trademark of Adobe in the United States and/or other countries.
- 许可证：SIL Open Font License 1.1 → `licenses/license ofl1.1.txt`
- 上游：https://github.com/notofonts/noto-cjk
- 备注：版权方为 Adobe（Noto Sans SC 衍生于 Source Han Sans），非 Google。

### JetBrains Mono

- 文件：`JetBrainsMono-Regular.ttf`
- 版权：Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono)
- 商标：JetBrains Mono is a trademark of JetBrains s.r.o.
- 许可证：SIL Open Font License 1.1 → `licenses/license ofl1.1.txt`
- 上游：https://github.com/JetBrains/JetBrainsMono

## 四、许可证全文对照

| 许可证 | 覆盖字体 | 全文位置 |
|---|---|---|
| SIL Open Font License 1.1 | Source Serif 4、Source Han Serif SC、Noto Sans SC、JetBrains Mono | `licenses/license ofl1.1.txt` |
| Apache License 2.0 | Noto Sans | `licenses/license Notosans.txt` |

## 五、Reserved Font Name（重要）

以下字体含 Reserved Font Name `'Source'`：

- Source Serif 4
- Source Han Serif SC
- Noto Sans SC

OFL-1.1 的规定是：**只要不修改字体文件，原样分发不受 RFN 限制，无需改名。**

> ⚠️ 如果将来为缩小体积而做子集化、裁剪或可变字体实例化，即构成「修改版本」，
> 届时**必须移除或替换字族名中的 `Source`**，并同步修改
> `themes/article-annotated.tokens.json` 的 `font` 段，否则违反 OFL。

## 六、完整性校验

    # Git Bash / Linux
    sha256sum fonts/*

    # PowerShell
    Get-ChildItem fonts | Get-FileHash -Algorithm SHA256 | Format-Table Hash, Path

各文件期望值：

| 文件 | SHA-256 |
|---|---|
| `SourceSerif4-Regular.otf` | `edf160d0d584deee8a3bb2c3371b2a7624ca63580fbe02c57c1f4c91e84d8787` |
| `SourceSerif4-It.otf` | `f8062257f4693e438a8e317c9fe2b4393f0d4eed84d897edcbfd733c30a1c1a1` |
| `SourceSerif4-Semibold.otf` | `25e034392847d9965c92f98971b3646436b7ab919ece9118b0c0e5ec94c02efc` |
| `SourceHanSerifSC-VF.otf` | `24980e3fdbdf7cbef800133c9bc8937cb65533ca50f0bd0565115db496f57220` |
| `NotoSans-Regular-2.ttf` | `f95fc61d04cc4c373fa58adb0e1ccd94f3607336d5e50f16363c6d823c84bba0` |
| `NotoSans-Bold-5.ttf` | `330a79dc27f6192dd7ed0efe0178716dcbc628e6cfe87b3bf35cc7479dbcfd73` |
| `NotoSansSC-VF.ttf` | `763146584cf0710223441356b4395e279021b0806c196614377a7a0174ae074a` |
| `JetBrainsMono-Regular.ttf` | `a0bf60ef0f83c5ed4d7a75d45838548b1f6873372dfac88f71804491898d138f` |

## 七、替换字体的注意事项

修改 `fonts/` 内容会改变 `artifact_id`（字体指纹参与计算），属预期行为。
替换后请重新跑一次构建，并更新本文件的版本号、SHA-256 与版权行。