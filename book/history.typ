// 2025: A History. Chapter template, 6 x 9 in. All text arrives as Typst
// strings from render.py; data for figures, notes and credits from data.json.

#let data = json("data.json")
#let meta = data.meta

#let ink = rgb("#1c1f24")
#let muted = rgb("#5f5b55")
#let faint = rgb("#9c968c")
#let hair = rgb("#d4cec4")
#let accent = rgb("#7d2a2c")
#let serif = ("Source Serif 4 SmText", "SimSun")
#let caption-face = ("Source Serif 4 Caption",)
#let head-face = ("Source Serif 4 Subhead",)
#let display = ("Source Serif 4 Display",)
#let sans = ("Source Sans 3",)

#let label-text(body, size: 7pt, fill: muted) = text(font: sans, size: size, weight: "semibold", tracking: 1.1pt, fill: fill, upper(body))

#set document(title: meta.book + ": " + meta.title, author: "current-events-context")
#set page(
  width: 6in, height: 9in,
  margin: (inside: 0.8in, outside: 0.65in, top: 0.8in, bottom: 0.8in),
  binding: left,
  header: context {
    let p = here().page()
    if p > 2 and query(<opener>).all(o => o.location().page() != p) {
      set text(font: sans, size: 7.4pt, fill: muted)
      if calc.even(p) { grid(columns: (auto, 1fr), column-gutter: 10pt, text(weight: "bold", fill: ink, str(p)), label-text(meta.book, size: 6.6pt)) }
      else { grid(columns: (1fr, auto), column-gutter: 10pt, align(right, label-text(meta.title, size: 6.6pt)), text(weight: "bold", fill: ink, str(p))) }
    }
  },
  footer: context {
    let p = here().page()
    if query(<opener>).any(o => o.location().page() == p) { align(center, text(font: sans, size: 7.4pt, fill: muted, str(p))) }
  },
)
#set text(font: serif, size: 10.2pt, fill: ink, lang: "en", region: "GB", hyphenate: true,
  costs: (hyphenation: 90%, runt: 150%, widow: 300%, orphan: 300%))
#set par(justify: true, leading: 0.68em, first-line-indent: 1.2em, spacing: 0.68em, linebreaks: "optimized")
#set footnote(numbering: "1")
#set footnote.entry(separator: line(length: 22%, stroke: 0.4pt + hair), gap: 0.45em, clearance: 1em, indent: 0pt)
#show footnote.entry: set text(font: caption-face, size: 7.4pt, fill: rgb("#33302b"))
#show footnote.entry: set par(justify: false, first-line-indent: 0pt, leading: 0.5em, hanging-indent: 0pt)
#show link: it => it

// ------------------------------------------------------------ components
#let section(title) = block(above: 1.8em, below: 0.9em, sticky: true)[
  #set par(first-line-indent: 0pt)
  #text(font: head-face, size: 12.5pt, style: "italic", title)
]

#let epigraph(quote, source) = block(width: 78%, above: 0pt, below: 2.2em)[
  #set par(first-line-indent: 0pt, justify: false)
  #text(font: head-face, size: 11pt, style: "italic", [\u{201C}#quote\u{201D}])
  #v(2pt)
  #align(right, text(font: sans, size: 7.4pt, fill: muted, [— #source]))
]

#let portrait(id, name) = {
  let p = data.portraits.find(x => x.id == id)
  place(top + right, float: true, clearance: 12pt, block(width: 1.55in)[
    #set par(first-line-indent: 0pt, justify: false, leading: 0.45em)
    #image("figures/" + id + ".svg", width: 100%)
    #v(3pt)
    #align(center, text(font: head-face, size: 8.6pt, style: "italic", name))
  ])
}

#let fig-frame(title, note, body) = figure(kind: "chart", supplement: "Figure", placement: auto, block(width: 100%, breakable: false, inset: (top: 6pt))[
  #set par(first-line-indent: 0pt, justify: false)
  #align(left, text(font: sans, size: 8.4pt, weight: "semibold", title))
  #v(6pt)
  #body
  #v(4pt)
  #align(left, text(font: sans, size: 6.6pt, fill: muted, note))
])
#show figure.where(kind: "chart"): it => block(above: 1.4em, below: 1.4em, it.body)

#let days(iso) = {
  let (y, m, d) = iso.split("-").map(int)
  let cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
  cum.at(m - 1) + d - 1
}

#let step-path(points, w, h, mx) = {
  let segs = ()
  for (i, pt) in points.enumerate() {
    let x = w * days(pt.at(0)) / 365
    let y = h - h * pt.at(1) / mx
    if i > 0 { let prev = points.at(i - 1); segs.push((x, h - h * prev.at(1) / mx)) }
    segs.push((x, y))
  }
  segs
}

#let china-chart = {
  let w = 3.9in
  let h = 1.55in
  let mx = 150
  let us = step-path(data.figures.us_on_china, w, h, mx)
  let cn = step-path(data.figures.china_on_us, w, h, mx)
  let months = ("J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D")
  box(width: w + 0.45in, height: h + 0.3in)[
    #for v in (0, 50, 100, 150) {
      place(dx: 0.4in, dy: h - h * v / mx, line(length: w, stroke: 0.3pt + hair))
      place(dx: 0in, dy: h - h * v / mx - 4pt, box(width: 0.32in, align(right, text(font: sans, size: 6.2pt, fill: muted, str(v) + "%"))))
    }
    #place(dx: 0.4in, dy: 0pt, curve(stroke: 1pt + faint, curve.move(cn.first()), ..cn.slice(1).map(p => curve.line(p))))
    #place(dx: 0.4in, dy: 0pt, curve(stroke: 1.6pt + accent, curve.move(us.first()), ..us.slice(1).map(p => curve.line(p))))
    #for (i, m) in months.enumerate() { place(dx: 0.4in + w * (i + 0.35) / 12, dy: h + 5pt, text(font: sans, size: 6pt, fill: muted, m)) }
    #place(dx: 0.4in + w * 136 / 365, dy: h - h * 145 / mx - 3pt, text(font: sans, size: 6.4pt, fill: accent, weight: "semibold")[145%])
    #place(dx: 0.4in + w * 136 / 365, dy: h - h * 125 / mx - 3pt, text(font: sans, size: 6.4pt, fill: muted)[125%])
    #place(dx: 0.4in + w * 220 / 365, dy: h - h * 30 / mx - 11pt, text(font: sans, size: 6.4pt, fill: accent)[30%])
    #place(dx: 0.4in + w * 318 / 365, dy: h - h * 20 / mx - 11pt, text(font: sans, size: 6.4pt, fill: accent)[20%])
    #place(dx: 0.4in + w * 0.62, dy: 2pt, stack(spacing: 4pt,
      [#box(width: 12pt, height: 1.6pt, fill: accent) #std.h(3pt) #text(font: sans, size: 6.4pt)[United States on China]],
      [#box(width: 12pt, height: 1pt, fill: faint) #std.h(3pt) #text(font: sans, size: 6.4pt)[China on the United States]]))
  ]
}

#let deficit-chart = {
  let rows = data.figures.deficit_change
  let mx = 100
  let half = 1.5in
  grid(columns: (1.35in, 2 * half), row-gutter: 5pt, align: (right + horizon, left + horizon),
    ..rows.map(r => (
      text(font: sans, size: 7.4pt, r.partner),
      box(width: 2 * half, height: 9pt, {
        place(dx: half, dy: -2pt, line(angle: 90deg, length: 13pt, stroke: 0.4pt + muted))
        let len = half * calc.abs(r.change) / mx
        if r.change >= 0 {
          place(dx: half, rect(width: len, height: 9pt, fill: if r.partner == "China" { faint } else { accent.lighten(25%) }, stroke: none))
          place(dx: half + len + 3pt, dy: 1pt, text(font: sans, size: 6.8pt, weight: "semibold", r.label))
        } else {
          place(dx: half - len, rect(width: len, height: 9pt, fill: faint, stroke: none))
          place(dx: half + 3pt, dy: 1pt, text(font: sans, size: 6.8pt, weight: "semibold", r.label))
        }
      }),
    )).flatten())
}

#let customs-chart = {
  let rows = data.figures.customs
  let mx = 35
  let h = 1.3in
  let bw = 0.135in
  grid(columns: rows.len() * (bw,), column-gutter: 1.6pt, align: bottom,
    ..rows.map(r => box(width: bw, height: h, align(bottom, rect(width: 100%, height: h * calc.max(r.billions, 0) / mx,
      fill: if r.month.starts-with("2025") { accent.lighten(15%) } else { faint }, stroke: none)))),
    ..rows.map(r => align(center, text(font: sans, size: 5.4pt, fill: muted, if r.month.ends-with("-01") { r.month.slice(0, 4) } else { "" }))))
}

#let figure-block(id) = {
  if id == "china-rates" {
    fig-frame([Additional tariffs on each other's goods, 2025], [Additional duty on most Chinese goods charged by the United States (fentanyl and reciprocal orders combined) and China's across-the-board duty on American goods, by effective date; the March increase is placed at the order's date, 3 March. Excludes sector tariffs and China's selective February and March duties. Sources: Executive Orders 14195, 14228, 14259, 14266, 14357; Geneva joint statement; Customs Tariff Commission announcements.], china-chart)
  } else if id == "deficit-shift" {
    fig-frame([Change in the US goods deficit, 2025 over 2024 (\$ billion)], [First annual estimate, balance-of-payments basis. Source: Census Bureau and BEA, December and Annual 2025 release.], deficit-chart)
  } else if id == "customs" {
    fig-frame([Net customs receipts by month, 2024–2025 (\$ billion)], [Monthly net customs duties; 2024 in grey, 2025 in red. Source: Monthly Treasury Statement, Table 4, via the Treasury Fiscal Data API.], customs-chart)
  }
}

// ================================================================ FRONT
#page(header: none, footer: none)[
  #v(1.6in)
  #align(center)[
    #label-text([Sample chapter · draft for editorial review], size: 7pt, fill: accent)
    #v(18pt)
    #text(font: display, size: 38pt, weight: "light", meta.book)
    #v(14pt)
    #line(length: 0.8in, stroke: 0.7pt + accent)
    #v(14pt)
    #text(font: head-face, size: 15pt, style: "italic")[Chapter #meta.number: #meta.title]
  ]
  #place(bottom + center, text(font: sans, size: 7.4pt, fill: muted)[current-events-context · #meta.date])
]

#page(header: none, footer: none)[
  #set text(size: 8.6pt)
  #set par(first-line-indent: 0pt, spacing: 0.9em)
  #v(1fr)
  #label-text[About this draft]
  #v(6pt)
  This chapter was drafted with Claude, an AI system, from a research dossier of opened primary documents, official statistics and analyses, and is presented to its editor for review. Every footnoted sentence rests on recorded findings; nothing is cited to Wikipedia, which served only as a finding aid. Sources are limited to those published by #meta.cutoff.

  Status: every footnoted sentence has been checked against the full text of the sources it cites, in a separate verification pass on 21 October 2026; fourteen corrections followed, and all 97 noted sentences are now supported as worded. That pass was made by the same AI system, not by a person. The editor's review and sign-off have not yet taken place, and the text should be treated as a draft.

  Portraits are engraving-style renderings made by line hatching from the photographs credited at the end, not photographs and not evidence. Figures are drawn from the official data named beneath them.

  #v(6pt)
  #text(fill: muted)[#meta.words words · #meta.notes notes · #meta.sources sources · chapter text SHA-256 #raw(meta.chapter_sha256.slice(0, 16))… · dossier #raw(meta.dossier_sha256.slice(0, 16))…]
]

// ============================================================== CHAPTER
#pagebreak(to: "odd", weak: true)
#metadata(none)<opener>
#block(below: 24pt)[
  #set par(first-line-indent: 0pt)
  #v(0.9in)
  #label-text(meta.part, fill: accent)
  #v(10pt)
  #text(font: display, size: 54pt, weight: "light", fill: hair.darken(10%), meta.number)
  #v(-8pt)
  #text(font: display, size: 30pt, meta.title)
]
#eval(read("body.typ"), mode: "markup", scope: (epigraph: epigraph, section: section, portrait: portrait, figure-block: figure-block))

// ============================================================= SOURCES
#pagebreak(weak: true)
#{
  set par(first-line-indent: 0pt, justify: false, hanging-indent: 1.2em, spacing: 0.5em, leading: 0.5em)
  set text(size: 7.8pt)
  block(below: 1em, text(font: head-face, size: 13pt, style: "italic")[Sources])
  let groups = ((1, "Primary documents"), (2, "Official statistics and data"), (4, "Analysis"))
  for (tier, name) in groups {
    let items = data.bibliography.filter(b => b.tier == tier)
    if items.len() > 0 {
      block(above: 1.1em, below: 0.6em, label-text(name, size: 6.6pt))
      for b in items { par[#b.text #link(b.url)[#text(fill: muted, size: 6.8pt, b.url)]] }
    }
  }
  block(above: 1.4em, below: 0.6em, label-text([Illustrations], size: 6.6pt))
  for p in data.portraits.filter(p => p.id in ("trump", "xi", "sheinbaum")) {
    par[#p.name. #p.credit. #p.licence. Rendered as line engraving. #link(p.source)[#text(fill: muted, size: 6.8pt, p.source)]]
  }
}
