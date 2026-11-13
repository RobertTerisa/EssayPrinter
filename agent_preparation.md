## 你现在是 EssayPrinter 环境配置人员

### 允许
- python -m pip install -r requirements.txt
- winget install --id Typst.Typst -e --accept-package-agreements --accept-source-agreements
- 只读运行 typst --version / typst fonts

### 禁止
- 安装/卸载 Python（版本不够就报告用户，不要自己换）
- 安装系统字体（字体已随仓库分发在 fonts/，无需安装）
- 修改 ep/ themes/ schema/ tokens.json
- 为绕过环境错误去改 AST

### 步骤
1. Python：`python -V` → 需 >= 3.12。低于则报告用户并停止。
2. pip 依赖：先 `python -m pip install -r requirements.txt --dry-run`
   无 error 且不会降级已有包 → 跳过；否则执行
   `python -m pip install -r requirements.txt`（会降级则先问用户）。
3. Typst：`typst --version` → 需 >= 0.15.1。缺失则执行上面的 winget 命令，
   装完**重开终端**再验证。
4. 字体（不需要安装，只需验证）：
   `typst fonts --ignore-system-fonts --font-path fonts`
   必须出现：Source Serif 4、Source Han Serif SC、Noto Sans、Noto Sans SC、JetBrains Mono
5. 最终确认：`python -m ep.cli build --from-ast examples/sample.ast.json --source-md examples/sample.md`
   退出码 0 或 2 = 环境就绪；3 = 环境缺失（按上面步骤补）；1 = AST/内容问题（不属环境）。

### 失败处理
无 winget / 无网络 / 需要管理员权限 → 报告用户，停止，不要重试。
同一失败最多重试 1 次。
缺少python ， winget请给出提示并告知用户去哪里下载。