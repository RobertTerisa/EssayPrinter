// =====================================================================
// EssayPrinter theme: article-annotated
// A4 · 大字批注版（几何从 Super-agent设计探索_批注版.docx 反解）
//   水平: 左 22 + 正文列 126 + 间距 4 + 批注栏 46 + 外白边 12 = 210mm
//   垂直: 上 20 + 正文 258 + 下 19                    = 297mm
//   正文 12pt / 行距 1.8(=21.6pt)  ->  约 22 字/行 x 33 行 ≈ 720 字/页
// 依赖: article-annotated.tokens.json（与本文件同目录）
// =====================================================================

#let T = json("article-annotated.tokens.json")

#let MI = if T.mode == "print" { 1 } else { 0 }
#let ink(name) = rgb(T.ink.at(name).at(MI))
#let mm_(v) = v * 1mm
#let ts(name) = T.type.at(name)
#let sz(name) = ts(name).size * 1pt
#let lead(name) = (ts(name).leading - 1) * 1em
#let font-of(key) = (T.font.at(key).latin, T.font.at(key).cjk)

// 批注栏底色（print 态为 none）
#let callout-fill() = if T.ink.calloutBg.at(MI) == none { none } else { rgb(T.ink.calloutBg.at(MI)) }

// 批注栏/竖线几何：每页固定右侧，不随奇偶页镜像。
// （even 参数保留以兼容调用点；T.page.mirror=false 时页边距也用 left/right。）
#let note-left(even) = T.page.width - T.page.note.outer - T.page.note.width
#let rule-x(even) = T.page.width - T.page.note.outer - T.page.note.width
#let note-dx(even) = T.page.bodyColumn + T.page.note.gap

// 标题编号只给 1 / 1.1 / 1.1.1；标点与空格由 show 规则加。
#let heading-number(level) = {
  let pat = if level == 1 { "1" } else { "1" + ".1" * (level - 1) }
  counter(heading).display(pat)
}

// ---------------------------------------------------------------------
// 正文分节：20/19/22/62，正文列 126，批注栏 46+4+12
// ---------------------------------------------------------------------
#let article(meta: (:), body) = {
  set document(title: meta.at("title", default: ""),
               author: meta.at("author", default: ""))

  set page(
    paper: T.page.size,
    margin: if T.page.mirror {
      (top: mm_(T.page.margin.t), bottom: mm_(T.page.margin.b),
       inside: mm_(T.page.margin.l), outside: mm_(T.page.margin.r))
    } else {
      (top: mm_(T.page.margin.t), bottom: mm_(T.page.margin.b),
       left: mm_(T.page.margin.l), right: mm_(T.page.margin.r))
    },
    header-ascent: mm_(T.page.headerDistance),
    footer-descent: mm_(T.page.footerDistance),
    numbering: "1",
    background: context {
      let even = calc.even(counter(page).get().first())
      // 竖线只画在正文区高度内（top=20mm → bottom=278mm），不能贯穿纸边；
      // 否则底部 5mm 边带会命中 MARGIN_OVERFLOW。
      place(top + left,
        dx: mm_(rule-x(even)),
        dy: mm_(T.page.margin.t),
        line(length: mm_(T.page.height - T.page.margin.t - T.page.margin.b),
             angle: 90deg,
             stroke: T.page.note.rule.w * 1pt + ink("noteRule")))
    },
    header: context {
      let even = calc.even(counter(page).get().first())
      set text(size: sz("header"), fill: ink("muted"))
      // 关键：header 里如果只有 place，内容高度会塌成 0，Typst 会把页眉贴到纸张顶边。
      // 必须给一个固定高度的外层 block，再用 place(left+horizon, …) 做水平定位 + 垂直居中。
      block(height: 4mm, width: 100%, {
        place(left + horizon, meta.at("title", default: ""))
        place(left + horizon, dx: mm_(note-dx(even)) + 2mm,
          block(width: mm_(T.page.note.width) - 4mm, align(right)[批注区]))
      })
    },
    footer: context {
      set text(size: sz("footer"), fill: ink("muted"))
      // page numbering 用 "1"，让 outline() 的目录页码保持纯数字；
      // 页脚格式在这里手工拼，避免目录页码继承 "— 3 —"。
      align(center, [— #counter(page).display() —])
    },
  )

  set text(font: font-of("body"), size: sz("body"), fill: ink("body"),
           lang: "zh", region: "cn")
  set par(leading: lead("body"), justify: true, spacing: 0pt,
          first-line-indent: (amount: T.para.indent * 1em, all: true))
  set heading(numbering: (..nums) => {
    let n = nums.pos()
    let pat = if n.len() == 1 { "1" } else { "1" + ".1" * (n.len() - 1) }
    numbering(pat, ..nums)
  }, outlined: true)
  // P3-3：带 id 的 math 块可被 ref 引用；公式编号由 Typst 计算。
  set math.equation(numbering: "(1)")

  // 目录条目：numbering 只给 1/1.1，一级的点号在这里补；页码用纯数字。
  show outline.entry: it => {
    let nums = counter(heading).at(it.element.location())
    let num = if it.level == 1 {
      numbering("1", ..nums) + [. ]
    } else {
      numbering("1.1", ..nums) + [ ]
    }
    link(it.element.location(), pad(left: (it.level - 1) * 1.2em, grid(
      columns: (auto, auto, 1fr, auto),
      column-gutter: 0.4em,
      num,
      it.element.body,
      box(width: 1fr, it.fill),
      numbering("1", ..counter(page).at(it.element.location())),
    )))
  }

  // ---- 标题：AST 不写编号，编号由 Typst 生成 --------------------------
  show heading.where(level: 1): it => block(
    above: ts("h1").spaceBefore * 1pt, below: ts("h1").spaceAfter * 1pt, {
      set text(font: font-of("sans"), size: sz("h1"), weight: "semibold", fill: ink("strong"))
      set par(leading: lead("h1"), first-line-indent: (amount: 0pt, all: false))
      if it.numbering != none {
        heading-number(it.level)
        if it.level == 1 { [.] }
        [ ]
      }
      it.body
    })
  show heading.where(level: 2): it => block(
    above: ts("h2").spaceBefore * 1pt, below: ts("h2").spaceAfter * 1pt, {
      set text(font: font-of("sans"), size: sz("h2"), weight: "semibold", fill: ink("accent"))
      set par(leading: lead("h2"), first-line-indent: (amount: 0pt, all: false))
      if it.numbering != none {
        heading-number(it.level)
        [ ]
      }
      it.body
    })
  show heading.where(level: 3): it => block(
    above: ts("h3").spaceBefore * 1pt, below: ts("h3").spaceAfter * 1pt, {
      set text(font: font-of("sans"), size: sz("h3"), weight: "semibold", fill: ink("strong"))
      set par(leading: lead("h3"), first-line-indent: (amount: 0pt, all: false))
      if it.numbering != none {
        heading-number(it.level)
        [ ]
      }
      it.body
    })
  show heading.where(level: 4): it => block(
    above: ts("h4").spaceBefore * 1pt, below: ts("h4").spaceAfter * 1pt, {
      set text(font: font-of("sans"), size: sz("h4"), weight: "semibold", fill: ink("strong"))
      set par(leading: lead("h4"), first-line-indent: (amount: 0pt, all: false))
      if it.numbering != none {
        heading-number(it.level)
        [ ]
      }
      it.body
    })
  show heading.where(level: 5): it => block(
    above: ts("h5").spaceBefore * 1pt, below: ts("h5").spaceAfter * 1pt, {
      set text(font: font-of("sans"), size: sz("h5"), weight: "semibold", fill: ink("strong"))
      set par(leading: lead("h5"), first-line-indent: (amount: 0pt, all: false))
      if it.numbering != none {
        heading-number(it.level)
        [ ]
      }
      it.body
    })
  show heading.where(level: 6): it => block(
    above: ts("h6").spaceBefore * 1pt, below: ts("h6").spaceAfter * 1pt, {
      set text(font: font-of("sans"), size: sz("h6"), weight: "semibold", fill: ink("strong"))
      set par(leading: lead("h6"), first-line-indent: (amount: 0pt, all: false))
      if it.numbering != none {
        heading-number(it.level)
        [ ]
      }
      it.body
    })

  // ---- 图 / 表 / 代码 ------------------------------------------------
  // v0.3.1 修复：图/表整体必须有显式的外部上下间距。
  // 本主题 par.spacing=0pt、para 的 above=0em；Typst 0.15.1 在 figure 之后会把
  // figure 尾部的 below 间距与图注最后一行的行距一起塌陷掉，紧跟其后的段落就会
  // 压在图注/表注上。把间距加在 figure 外层 block 上则不参与塌陷，可稳定隔开。
  // 注意：写在 show figure.caption 里的 block(above/below) 无效——caption 属于
  // figure 内部，它的外边距不计入 figure 自身高度。
  show figure: set block(above: 0.7em, below: 0.8em)

  // 注意：自定义 show 规则必须自己渲染 supplement + 编号 + 分隔符，
  // 只写 it.body 会把“图 1 / 表 1”整段丢掉。0.15.1 没有 it.prefix。
  show figure.caption: it => block(above: 0.5em, below: 1em, {
    set text(size: sz("caption"), fill: ink("caption"), style: "normal")
    set par(leading: lead("caption"), first-line-indent: (amount: 0pt, all: false), justify: false)
    align(center, [
      #it.supplement
      #context it.counter.display(it.numbering)
      #it.separator
      #it.body
    ])
  })

  body
}

// ---------------------------------------------------------------------
// 封面：24/22/25/25；无页码/页眉/页脚/批注栏竖线；不计入页码重置
// ---------------------------------------------------------------------
#let cover(meta: (:)) = {
  pagebreak(weak: true)
  set page(
    margin: (top: mm_(T.page.coverMargin.t), bottom: mm_(T.page.coverMargin.b),
             left: mm_(T.page.coverMargin.l), right: mm_(T.page.coverMargin.r)),
    numbering: none, header: none, footer: none, background: none,
  )
  set par(first-line-indent: (amount: 0pt, all: false), justify: false)

  v(38mm)
  align(center, {
    set text(font: font-of("sans"), size: sz("coverKicker"), fill: ink("muted"),
             tracking: ts("coverKicker").tracking * 1pt)
    upper(meta.at("kicker", default: "ESSAY PRINTER"))
  })
  v(6mm)
  align(center, line(length: 22%, stroke: 1.2pt + ink("accent")))
  v(10mm)

  align(center, {
    set text(font: font-of("sans"), size: sz("coverTitle"), weight: "semibold", fill: ink("strong"))
    set par(leading: lead("coverTitle"), justify: false)
    meta.at("title", default: "")
  })
  if meta.at("subtitle", default: "") != "" {
    v(4mm)
    align(center, {
      set text(font: font-of("sans"), size: sz("coverSub"), weight: "semibold", fill: ink("strong"))
      set par(leading: lead("coverSub"), justify: false)
      meta.at("subtitle")
    })
  }
  if meta.at("subtitle_latin", default: "") != "" {
    v(6mm)
    align(center, {
      set text(font: font-of("quote"), size: sz("coverLatin"), style: "italic", fill: ink("muted"))
      meta.at("subtitle_latin")
    })
  }

  v(1fr)
  align(center, {
    set text(size: sz("coverMeta"), fill: ink("meta"))
    set par(leading: lead("coverMeta"), justify: false)
    for k in ("author", "date", "source") {
      if meta.at(k, default: "") != "" { meta.at(k); linebreak() }
    }
    if meta.at("url", default: "") != "" { link(meta.at("url")) }
  })
  v(20mm)

  pagebreak()
}

// ---------------------------------------------------------------------
// 目录：16.9/14.8/25/25；无页码/页眉/页脚/竖线；目录独占页
// ---------------------------------------------------------------------
#let tocblock(title: "目录", depth: 2) = {
  pagebreak(weak: true)
  set page(
    margin: (top: mm_(T.page.tocMargin.t), bottom: mm_(T.page.tocMargin.b),
             left: mm_(T.page.tocMargin.l), right: mm_(T.page.tocMargin.r)),
    numbering: none, header: none, footer: none, background: none,
  )
  block(above: 0pt, below: 1.2em, {
    set text(font: font-of("sans"), size: sz("tocTitle"), weight: "semibold", fill: ink("strong"))
    set par(first-line-indent: (amount: 0pt, all: false), justify: false)
    title
  })
  block(below: 1em, line(length: 100%, stroke: 1pt + ink("accent")))
  set par(first-line-indent: (amount: 0pt, all: false), justify: false)
  outline(title: none, depth: depth, indent: auto)
  pagebreak(weak: true)
}

// ---------------------------------------------------------------------
// 内容块原语（由 render_typst.py 生成调用）
// ---------------------------------------------------------------------
#let h1(body) = heading(level: 1, outlined: true, body)
#let h2(body) = heading(level: 2, outlined: true, body)
#let h3(body) = heading(level: 3, outlined: true, body)
#let h4(body) = heading(level: 4, outlined: true, body)
#let h5(body) = heading(level: 5, outlined: true, body)
#let h6(body) = heading(level: 6, outlined: true, body)

#let para(body) = block(above: 0em, below: 0.5em, body)
#let hrule() = block(above: 1em, below: 1em, line(length: 100%, stroke: 0.5pt + ink("rule")))

// 列表项：必须用 list.item / enum.item，否则不会生成项目符号/编号
#let bitem(body) = list.item(body)
#let nitem(body) = enum.item(body)

#let bulletlist(body) = block(above: 0.4em, below: 0.6em, {
  set par(first-line-indent: (amount: 0pt, all: false), spacing: 0.35em)
  set list(marker: text(fill: ink("list"))[•], indent: T.list.indent * 1em)
  body
})

#let numlist(body) = block(above: 0.4em, below: 0.6em, {
  set par(first-line-indent: (amount: 0pt, all: false), spacing: 0.35em)
  set enum(indent: T.list.indent * 1em)
  body
})

#let quote(body) = block(
  inset: (left: 1em, right: 0.5em),
  stroke: (left: 1.5pt + ink("noteRule")),
  above: 0.6em, below: 0.8em, body,
)

#let callout(tone: "note", body) = block(
  width: 100%,
  inset: (left: 0.8em, right: 0.5em, top: 0.6em, bottom: 0.6em),
  stroke: (left: 1.5pt + ink("noteRule")),
  fill: callout-fill(),
  above: 0.8em, below: 1em,
  body,
)

// 插图：图号自动，caption 由 AST 提供
#let fig(src, width: 100%, caption: none) = figure(
  image(src, width: width),
  caption: caption,
  gap: 0.7em,
  kind: image,
  supplement: [图],
)

// 表格：表格号自动
#let tbl(columns: 2, caption: none, ..cells) = figure(
  block(width: 100%, {
    set par(justify: false, first-line-indent: (amount: 0pt, all: false))
    table(columns: columns, stroke: 0.4pt + ink("rule"),
          inset: 0.5em, align: left, ..cells)
  }),
  caption: caption,
  gap: 0.6em,
  kind: table,
  supplement: [表],
)

#let codeblock(lang: "", content: "") = block(
  width: 100%,
  inset: 0.6em,
  fill: if T.ink.calloutBg.at(MI) == none { none } else { rgb(T.ink.calloutBg.at(MI)) },
  stroke: (left: 2pt + ink("rule")),
  above: 0.8em, below: 1em, {
    // raw 元素自带字体 show 规则；只 set text 会被覆盖，必须显式 show raw。
    show raw: set text(font: font-of("mono"))
    set text(font: font-of("mono"), size: 0.85em)
    set par(first-line-indent: (amount: 0pt, all: false), justify: false, leading: 0.45em)
    raw(content, lang: if lang == "" { none } else { lang }, block: true)
  },
)

// 数学块：renderer 传入 $ ... $（Typst 数学语法）
#let matheq(body) = block(above: 0.8em, below: 0.8em, body)

// 批注栏旁注：跟随当前段落位置；批注栏固定在右侧
#let mnote(body) = context {
  let p = here().position()
  let even = calc.even(counter(page).get().first())
  place(
    top + left,
    dx: mm_(note-dx(even)),
    dy: p.y - mm_(T.page.margin.t),
    block(width: mm_(T.page.note.width), inset: (left: 2mm), {
      set text(size: sz("note"), fill: ink("note"), style: "normal")
      set par(leading: lead("note"), justify: false,
              first-line-indent: (amount: 0pt, all: false))
      body
    }),
  )
}

// 交叉引用：kind = sec / fig / tbl / eq
#let xref(kind, label) = context {
  if kind == "sec" {
    [#ref(label, supplement: none) 节]
  } else if kind == "eq" {
    [#ref(label)]                 // 默认 supplement 为「式」（由 text.lang 决定）
  } else {
    ref(label)
  }
}

// 未知块类型的兜底显示（不应出现在正常产物中）
#let unknown(kind) = block(
  fill: rgb("#FFE8E8"), inset: 0.4em,
  text(fill: rgb("#B00020"))[未识别的块类型：#kind],
)
