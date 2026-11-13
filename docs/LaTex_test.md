# Markdown 中的 LaTeX 公式速查与测试

本文档汇总 Markdown 环境下常用的 LaTeX 数学公式写法，覆盖四则运算、阶乘、求导、微分、不定积分、定积分、向量与矩阵。

**语法约定**

- 行内公式：用一对美元符号包裹，例如 `$a+b=c$`，渲染为 $a+b=c$，与文字混排。
- 独立公式（块级）：用两个 `$$` 包裹并单独成行，公式居中另起一行。
- 常用环境：`aligned`（多行对齐）、`cases`（分段）、`pmatrix`/`bmatrix`/`vmatrix`（矩阵）。

---

## 一、四则运算

### 1.1 行内四则运算

加减乘除与括号：$1+2=3$，$7-4=3$，$3\times4=12$，$8\div2=4$，$(2+3)\times4=20$。

除号也可以用分数形式表达：$\dfrac{1}{2}+\dfrac{1}{3}=\dfrac{5}{6}$。

> Markdown 表格里的竖线 `|` 会被当成单元格分隔符，所以表格内公式应避免 `|`（如 `\left| x \right|`），可改用 `\lvert x \rvert`。

### 1.2 独立四则运算

$$
(a+b)^2 = a^2 + 2ab + b^2
$$

$$
\frac{a}{b} \times \frac{c}{d} = \frac{ac}{bd}, \qquad \frac{a}{b} \div \frac{c}{d} = \frac{a}{b}\cdot\frac{d}{c} = \frac{ad}{bc}
$$

带根号与幂次的混合运算：

$$
\sqrt{x^2+y^2} = \left(x^2+y^2\right)^{\frac{1}{2}}, \qquad \sqrt[3]{8}=2
$$

多行对齐的连续推导（`aligned` 环境）：

$$
\begin{aligned}
(1+2)^2 - 3 \times 4 &= 9 - 12 \\
&= -3
\end{aligned}
$$

---

## 二、阶乘

阶乘定义：$n! = 1\times2\times3\times\cdots\times n$，并规定 $0!=1$。

$$
5! = 5\times4\times3\times2\times1 = 120
$$

双阶乘：

$$
7!! = 7\times5\times3\times1 = 105, \qquad 6!! = 6\times4\times2 = 48
$$

排列数与组合数（含阶乘的常用写法）：

$$
A_n^k = \frac{n!}{(n-k)!}, \qquad C_n^k = \binom{n}{k} = \frac{n!}{k!\,(n-k)!}
$$

阶乘的增长与斯特林近似：

$$
n! \approx \sqrt{2\pi n}\left(\frac{n}{e}\right)^{n}
$$

---

## 三、求导

### 3.1 一阶导数

函数 $y=f(x)$ 对 $x$ 的导数：

$$
f'(x) = \frac{dy}{dx} = \lim_{\Delta x \to 0}\frac{f(x+\Delta x)-f(x)}{\Delta x}
$$

常见求导公式：

$$
\left(x^n\right)' = nx^{n-1}, \qquad \left(e^x\right)' = e^x, \qquad \left(\ln x\right)' = \frac{1}{x}
$$

$$
\left(\sin x\right)' = \cos x, \qquad \left(\cos x\right)' = -\sin x, \qquad \left(\tan x\right)' = \frac{1}{\cos^2 x}
$$

### 3.2 二阶与高阶导数

$$
f''(x) = \frac{d^2y}{dx^2}, \qquad f^{(n)}(x) = \frac{d^ny}{dx^n}
$$

### 3.3 求导法则

乘积法则与商法则：

$$
(uv)' = u'v + uv', \qquad \left(\frac{u}{v}\right)' = \frac{u'v - uv'}{v^2}
$$

复合函数（链式法则）：

$$
\frac{dy}{dx} = \frac{dy}{du}\cdot\frac{du}{dx}, \qquad \left[f(g(x))\right]' = f'(g(x))\cdot g'(x)
$$

### 3.4 偏导数与多元函数

偏导数用 `\partial`：

$$
\frac{\partial z}{\partial x}, \qquad \frac{\partial^2 z}{\partial x\,\partial y}, \qquad \nabla f = \left(\frac{\partial f}{\partial x},\ \frac{\partial f}{\partial y},\ \frac{\partial f}{\partial z}\right)
$$

---

## 四、微分

微分的定义（自变量增量与函数增量的线性主部）：

$$
dy = f'(x)\,dx
$$

常见微分形式：

$$
d\left(x^n\right) = nx^{n-1}dx, \qquad d\left(\sin x\right) = \cos x\,dx, \qquad d\left(e^x\right) = e^x dx
$$

$$
d\left(\ln x\right) = \frac{dx}{x}, \qquad d\left(\arctan x\right) = \frac{dx}{1+x^2}
$$

全微分（二元函数）：

$$
dz = \frac{\partial z}{\partial x}dx + \frac{\partial z}{\partial y}dy
$$

一阶微分形式不变性：

$$
dy = f'(u)\,du, \quad \text{其中 } u = g(x)
$$

---

## 五、不定积分

基本积分公式：

$$
\int x^n\,dx = \frac{x^{n+1}}{n+1} + C \quad (n \neq -1), \qquad \int \frac{dx}{x} = \ln\lvert x \rvert + C
$$

$$
\int e^x\,dx = e^x + C, \qquad \int \sin x\,dx = -\cos x + C, \qquad \int \cos x\,dx = \sin x + C
$$

$$
\int \frac{dx}{1+x^2} = \arctan x + C, \qquad \int \frac{dx}{\sqrt{1-x^2}} = \arcsin x + C
$$

换元积分与分部积分（`\mathrm{d}` 让微分符号正体显示，排版更规范）：

$$
\int f(g(x))\,g'(x)\,\mathrm{d}x = \int f(u)\,\mathrm{d}u, \qquad u = g(x)
$$

$$
\int u\,\mathrm{d}v = uv - \int v\,\mathrm{d}u
$$

---

## 六、定积分

定积分的定义（黎曼和的极限）：

$$
\int_a^b f(x)\,\mathrm{d}x = \lim_{n\to\infty}\sum_{i=1}^{n} f(\xi_i)\,\Delta x_i
$$

牛顿—莱布尼茨公式：

$$
\int_a^b f(x)\,\mathrm{d}x = F(b) - F(a) = \Big[F(x)\Big]_a^b
$$

计算示例：

$$
\int_0^1 x^2\,\mathrm{d}x = \left[\frac{x^3}{3}\right]_0^1 = \frac{1}{3}
$$

$$
\int_{0}^{\pi} \sin x\,\mathrm{d}x = \Big[-\cos x\Big]_0^{\pi} = 2
$$

多重积分：

$$
\iint_D f(x,y)\,\mathrm{d}x\,\mathrm{d}y, \qquad \iiint_{\Omega} f(x,y,z)\,\mathrm{d}x\,\mathrm{d}y\,\mathrm{d}z
$$

曲线积分与曲面积分：

$$
\oint_L \vec{F}\cdot \mathrm{d}\vec{l}, \qquad \iint_{\Sigma} \vec{F}\cdot \mathrm{d}\vec{S}
$$

---

## 七、向量

列向量与行向量：

$$
\vec{a} = \begin{pmatrix} a_1 \\ a_2 \\ a_3 \end{pmatrix}, \qquad \vec{b}^{\mathsf{T}} = \begin{pmatrix} b_1 & b_2 & b_3 \end{pmatrix}
$$

粗体（数学惯例中的向量记法）：

$$
\mathbf{u} = (u_1, u_2, u_3), \qquad \|\mathbf{u}\| = \sqrt{u_1^2 + u_2^2 + u_3^2}
$$

单位向量与方向余弦：

$$
\hat{\mathbf{e}} = \frac{\mathbf{u}}{\|\mathbf{u}\|}, \qquad \cos\alpha = \frac{u_x}{\|\mathbf{u}\|}
$$

点积与叉积：

$$
\vec{a}\cdot\vec{b} = a_1b_1 + a_2b_2 + a_3b_3 = \lvert \vec{a} \rvert\,\lvert \vec{b} \rvert\cos\theta
$$

$$
\vec{a}\times\vec{b} =
\begin{vmatrix}
\mathbf{i} & \mathbf{j} & \mathbf{k} \\
a_1 & a_2 & a_3 \\
b_1 & b_2 & b_3
\end{vmatrix}
$$

向量加法与数乘：

$$
\vec{a} + \vec{b} = (a_1+b_1,\ a_2+b_2,\ a_3+b_3), \qquad \lambda\vec{a} = (\lambda a_1,\ \lambda a_2,\ \lambda a_3)
$$

---

## 八、矩阵

### 8.1 矩阵的书写

圆括号矩阵（`pmatrix`）：

$$
A = \begin{pmatrix}
a_{11} & a_{12} & a_{13} \\
a_{21} & a_{22} & a_{23} \\
a_{31} & a_{32} & a_{33}
\end{pmatrix}
$$

方括号矩阵（`bmatrix`）与行列式（`vmatrix`）：

$$
B = \begin{bmatrix}
1 & 2 \\
3 & 4
\end{bmatrix},
\qquad
\det A = \begin{vmatrix}
a_{11} & a_{12} \\
a_{21} & a_{22}
\end{vmatrix} = a_{11}a_{22} - a_{12}a_{21}
$$

大括号矩阵（`Bmatrix`）与无括号矩阵：

$$
C = \begin{Bmatrix} 1 & 0 \\ 0 & 1 \end{Bmatrix},
\qquad
\begin{matrix} 1 & 2 \\ 3 & 4 \end{matrix}
$$

### 8.2 矩阵运算

矩阵乘法：

$$
\begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}
\begin{pmatrix} 5 & 6 \\ 7 & 8 \end{pmatrix}
=
\begin{pmatrix}
1\times5+2\times7 & 1\times6+2\times8 \\
3\times5+4\times7 & 3\times6+4\times8
\end{pmatrix}
=
\begin{pmatrix} 19 & 22 \\ 43 & 50 \end{pmatrix}
$$

转置与逆矩阵：

$$
A^{\mathsf{T}}, \qquad A^{-1} = \frac{1}{\det A}\begin{pmatrix} d & -b \\ -c & a \end{pmatrix}, \quad A = \begin{pmatrix} a & b \\ c & d \end{pmatrix}
$$

单位矩阵：

$$
I_n = \begin{pmatrix}
1 & 0 & \cdots & 0 \\
0 & 1 & \cdots & 0 \\
\vdots & \vdots & \ddots & \vdots \\
0 & 0 & \cdots & 1
\end{pmatrix}
$$

### 8.3 分段函数与线性方程组

分段函数用 `cases`：

$$
f(x) = \begin{cases}
x^2, & x \geq 0 \\
-x, & x < 0
\end{cases}
$$

线性方程组的矩阵形式 $A\mathbf{x} = \mathbf{b}$：

$$
\begin{cases}
a_{11}x_1 + a_{12}x_2 = b_1 \\
a_{21}x_1 + a_{22}x_2 = b_2
\end{cases}
\iff
\begin{pmatrix} a_{11} & a_{12} \\ a_{21} & a_{22} \end{pmatrix}
\begin{pmatrix} x_1 \\ x_2 \end{pmatrix}
=
\begin{pmatrix} b_1 \\ b_2 \end{pmatrix}
$$

---

## 九、常用语法速查表

| 需求 | LaTeX 写法 | 效果 |
| --- | --- | --- |
| 分数 | `\frac{a}{b}` | $\frac{a}{b}$ |
| 大型分数 | `\dfrac{a}{b}` | $\dfrac{a}{b}$ |
| 上下标 | `x_i^2` | $x_i^2$ |
| 根号 | `\sqrt[3]{x}` | $\sqrt[3]{x}$ |
| 求和 | `\sum_{i=1}^{n}` | $\sum_{i=1}^{n}$ |
| 连乘 | `\prod_{i=1}^{n}` | $\prod_{i=1}^{n}$ |
| 极限 | `\lim_{x\to0}` | $\lim_{x\to0}$ |
| 阶乘 | `n!` | $n!$ |
| 导数 | `f'(x)` | $f'(x)$ |
| 偏导 | `\frac{\partial f}{\partial x}` | $\partial f / \partial x$ |
| 微分符号 | `\mathrm{d}x` | $\mathrm{d}x$ |
| 积分 | `\int_a^b f(x)\,dx` | $\int_a^b f(x)\,dx$ |
| 二重积分 | `\iint_D` | $\iint_D$ |
| 向量 | `\vec{a}` | $\vec{a}$ |
| 粗体向量 | `\mathbf{u}` | $\mathbf{u}$ |
| 范数 | `\lVert x \rVert` | $\lVert x \rVert$ |
| 矩阵 | `\begin{pmatrix}…\end{pmatrix}` | 圆括号矩阵 |
| 行列式 | `\begin{vmatrix}…\end{vmatrix}` | 竖线行列式 |
| 希腊字母 | `\alpha \beta \gamma` | $\alpha \beta \gamma$ |
| 无穷 | `\infty` | $\infty$ |
| 空格 | `\,` `\quad` `\qquad` | 由小到大 |

---

## 十、书写注意事项

1. 行内公式的 `$` 必须成对出现，`$` 与公式内容之间不要插入其他无关字符。
2. 块级公式 `$$` 必须成对出现，且建议前后各留一个空行，避免被合并进上一段落。
3. 上标/下标内容多于一个字符时用花括号：`x^{10}` 而不是 `x^10`。
4. 函数名（sin、cos、ln、lim 等）要用反斜杠命令，写成 `\sin x` 才会以正体显示。
5. 表格内避免使用 `|`，用 `\lvert`、`\rvert`、`\lVert`、`\rVert` 代替绝对值与范数符号。
6. 需要下标文字用 `\text{}`，例如 `\Delta_{\text{总}}`。
7. 不同 Markdown 编辑器（Typora、Obsidian、VS Code、GitHub）对公式的支持程度不同，导出前建议在本机预览确认。

