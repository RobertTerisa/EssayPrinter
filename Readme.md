## EssayPrinter 说明

### **0. 项目简介**

本项目是一款可以帮助用户将自己的电子版文章轻松转变成易于打印、易于阅读、易于批注的纸质文档的 agent。

使用时请在 DeepSeek Harness 中打开该项目文件夹作为工作区，将含有文章的 `.html` / `.md` / `.pdf` / `.docx` 引用并要求 LLM 进行排版即可；agent 的具体工作流程由工作区内的 `AGENTS.md` 约束。

>当前对中文排版支持最好，其他语言可用但不保证效果。

> P1.18（packaging / console entry point）暂缓，因此所有命令统一写作 `python -m ep.cli <subcommand>`，不使用裸 `ep`。

> **<font color="red">本项目仅限于个人用户学习交流使用，请勿用于商业出版、盗版等行为。任何由用户引起的版权纠纷由用户自行承担，本人概不负责！</font>**

---

### **1. 项目架构**

```
用户需求：把这篇文章排成看得清、能打印、能上手批注的纸质文档
  │
  │  python -m ep.cli build --from-ast doc.json -o out.pdf --theme article-annotated
  ▼
[1] 归一化 normalize —— 确定性 · 静态工具（基于 all2md）
    html / md / pdf / docx  ->  规范 Markdown
    只做格式转换，不做任何排版判断；PDF 仅支持纯文本型
  ▼
[2] 语义化 semanticize —— LLM · 全流程唯一需要模型的环节
    规范 Markdown  ->  语义 AST (doc.json)
    只决定「这段内容是什么」，不决定字号/颜色/边距/版式
    不输出 toc 节点：目录由 gate 从 heading 自动生成，页码由 Typst 计算
  ▼
[3] 渲染 render —— 确定性 · Typst
    doc.json + theme.tokens.json  ->  doc.typ  ->  typst compile  ->  out.pdf
    页码、图号、章号、交叉引用、运行页眉、PDF 书签 全部由 Typst 计算
  ▼
[4] 自检 validate —— 确定性 · 5 项硬指标
    AST schema ／ 页边溢出 ／ 字体嵌入 ／ 图片有效 DPI ／ 目录一致性
    失败 -> 结构化报告交给 agent 修复后重跑（≤3 次）；仍失败则终止，不发布任何交付物
  ▼
[5] 发布 publish —— 全有或全无
    通过才由 publish() 原子写入 release/<slug>-<artifact-id>.pdf
    交付物内嵌 artifact_id，可用 python -m ep.cli verify 独立复核；
    不通过时 release/ 里不会多出任何文件（诊断包留在 work/，不算交付物）
```

#### 1.1 五条架构决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | **最终输出引擎** | **Typst** | 纸面文档的刚需——目录真实页码、交叉引用、运行页眉、脚注、PDF 书签、分节页码重置、字体嵌入——Typst 全部原生支持且确定性可复现；Chrome 不支持 CSS `@page` margin box 与 `target-counter`，做不出目录页码；WeasyPrint 能做但专有 DSL 更重、CJK 标点处理更弱。Chrome 仅保留作 HTML 预览，不参与交付。 |
| 2 | **中间表示** | **语义 AST（JSON）** | 比让 LLM 直接写 HTML/Typst 更可控：可 schema 校验、可限制自由度、可回归测试；且**后端无关**——同一份 AST 将来可换渲染后端而不动上游。 |
| 3 | **目录（TOC）** | **AST 只存结构，页码由 Typst 生成** | 原文档自带的目录页码（如 docx 的 `PAGEREF`、导出的 HTML 快照）一经修改即全部失效。因此 AST 中的 `toc` 节点**禁止出现任何页码字段**，只保留条目文字与层级，渲染时统一由 `outline()` 重算。 |
| 4 | **LLM 职责边界** | **只决定"内容是什么"，不决定"长什么样"** | 样式全部收敛在 `themes/*` 里。若让 LLM 每次现写渲染代码，同一输入两次运行结果不同、无法复现、无法做视觉回归。 |
| 5 | **交付方式** | **全有或全无（发布门禁）** | 校验不通过就不产生交付物：交付物只能由 `publish()` 原子写入 `release/`，且文件名带 `artifact_id`。模型无法靠"自称完成"或复用旧 PDF 绕过，也不依赖 harness 提供插件能力。 |

#### 1.2 目录处理规则

| 情形 | 识别方式 | 处理 |
|------|----------|------|
| A. 原文**有**目录 | 存在标题为 `目录` / `目次` / `CONTENTS` / `Table of Contents` 的段落，其后跟随 ≥3 条带页码或带锚点的条目 | 源目录只用于判定 `detected=original`；条目与页码全部丢弃，gate 从 heading 重建 |
| B. 原文**无**目录 | 上述特征不成立 | gate 从 heading 生成 `{"type":"toc","detected":"extracted",...}` |
| C. 原文有目录但与标题层级不一致 | 源目录条目/页码与 headings 对不上 | 以**标题层级为准**重建，并把 `detected` 降级为 `extracted`（`TOC_SOURCE_MISMATCH` warn） |
| D. 无任何标题层级 | 全文无 `#` 标题 | 不生成 `toc` 节点，交付时提示"本文无层级，未生成目录"（`TOC_NOT_GENERATED` warn） |

补充约束：

- 目录**只能有一个**，且必须位于封面之后、第一个 `h1` 之前。
- 条目的 `anchor` 必须与某个 `h` 节点的 `id` 对应；匹配失败计入自检 `TOC_MISMATCH`。
- 目录页码、条目缩进、引导点（dot leader）均属样式，由 theme 决定，**不进 AST**。

---

### **2. 支持范围**

| 输入 | 支持程度 | 说明 |
|------|----------|------|
| `.md` | 一等公民 | 直接进入 [2] |
| `.html` | 支持 | all2md 归一化后进入 [2] |
| `.docx` | 支持 | all2md 归一化后进入 [2] |
| `.pdf`（**纯文本型**） | 兜底 | 仅支持文字层完整、单栏、无扫描件、无复杂公式的 PDF；双栏 / 扫描件 / 图片内文字不在支持范围 |
