// Annual yearbook design. All content arrives as data from book.json;
// source strings are inserted as text and never evaluated as markup.

#let data = json("book.json")
#let meta = data.meta
#let year = meta.year

// ---------------------------------------------------------------- tokens
#let ink = rgb("#1c1f24")
#let muted = rgb("#67635c")
#let faint = rgb("#a39e95")
#let hair = rgb("#d6d0c6")
#let tint = rgb("#f4f0e8")
#let accent = rgb("#7d2a2c")
#let night = rgb("#161c24")
#let heat-lo = rgb("#efe7da")
#let heat-hi = rgb("#7d2a2c")

#let catcolor = (
  conflict: rgb("#9a3b33"), law: rgb("#4a5c7c"), disaster: rgb("#b0742b"),
  politics: rgb("#2f5d86"), relations: rgb("#2e7264"), business: rgb("#6a7832"),
  sports: rgb("#7a4c86"), arts: rgb("#a14f69"), science: rgb("#2a7a93"),
  health: rgb("#4e8746"), other: rgb("#7a7670"),
)

#let text-face = ("Source Serif 4 SmText", "SimSun", "Segoe UI Symbol")
#let caption-face = ("Source Serif 4 Caption", "SimSun")
#let head-face = ("Source Serif 4 Subhead", "SimSun")
#let display-face = ("Source Serif 4 Display", "SimSun")
#let sans = ("Source Sans 3", "Microsoft YaHei", "Segoe UI Symbol")
#let mono = ("Source Code Pro", "DejaVu Sans Mono")

// --------------------------------------------------------------- helpers
#let num(n) = {
  let s = str(n)
  let parts = ()
  while s.len() > 3 {
    parts.insert(0, s.slice(s.len() - 3))
    s = s.slice(0, s.len() - 3)
  }
  parts.insert(0, s)
  parts.join(",")
}

#let plural(n, one, many) = if n == 1 [#num(n) #one] else [#num(n) #many]

#let ranges(pages) = {
  let ps = pages.sorted().dedup()
  let out = ()
  let start = none
  let prev = none
  for p in ps {
    if start == none { start = p; prev = p }
    else if p == prev + 1 { prev = p }
    else {
      out.push(if start == prev { str(start) } else { str(start) + "–" + str(prev) })
      start = p; prev = p
    }
  }
  if start != none { out.push(if start == prev { str(start) } else { str(start) + "–" + str(prev) }) }
  out.join(", ")
}

#let heat(t) = color.mix((heat-hi, t * 100%), (heat-lo, (1 - t) * 100%))
#let smallcaps-label(body, fill: muted, size: 6.6pt) = text(font: sans, size: size, weight: "semibold", tracking: 1pt, fill: fill, upper(body))
#let kicker(body, fill: accent) = smallcaps-label(body, fill: fill, size: 7pt)

#let month-names = ("January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December")
#let pretty-date(iso) = {
  let parts = iso.split("-")
  str(int(parts.at(2))) + " " + month-names.at(int(parts.at(1)) - 1)
}

// Recto starts and section ends, used to suppress furniture on blank versos.
#let recto-start() = [#metadata(none)<recto>]
#let section-end() = [#metadata(none)<end>]
#let section-mark(name) = [#metadata(name)<sectmark>]

#let is-blank(p) = {
  let next = query(<recto>).any(x => x.location().page() == p + 1)
  if not next { return false }
  let ends = query(<end>).map(x => x.location().page()).filter(q => q <= p)
  ends.len() > 0 and ends.last() < p
}

// -------------------------------------------------------- page furniture
#let date-range(p) = {
  let marks = query(<daymark>)
  let on = marks.filter(m => m.location().page() == p)
  let before = marks.filter(m => m.location().page() < p)
  let starts-clean = on.len() > 0 and {
    let pos = on.first().location().position()
    pos.y < 1.35in and pos.x < 4.25in
  }
  let first = if starts-clean { on.first() } else if before.len() > 0 { before.last() } else if on.len() > 0 { on.first() } else { none }
  if first == none { return none }
  let last = if on.len() > 0 { on.last() } else { first }
  let a = first.value
  let b = last.value
  if a.date == b.date { [#a.day #a.month] }
  else if a.month == b.month { [#a.day–#b.day #a.month] }
  else { [#a.day #a.month – #b.day #b.month] }
}

// Section-opening pages carry a drop folio instead of a running head.
#let opens-section(p) = query(<sectmark>).any(m => m.location().page() == p)

#let running-head = context if not is-blank(here().page()) and not opens-section(here().page()) {
  let p = here().page()
  let sects = query(<sectmark>).filter(m => m.location().page() <= p)
  let sect = if sects.len() > 0 { sects.last().value } else { "" }
  let folio = text(font: sans, size: 7.6pt, weight: "bold", fill: ink, str(p))
  let range = if sect in month-names { date-range(p) } else { none }
  let outer = if range != none { text(font: head-face, size: 8.8pt, style: "italic", fill: ink, range) } else { smallcaps-label(size: 6.6pt, sect) }
  let inner = smallcaps-label(size: 6.2pt, if range != none { if calc.even(p) [#year · A Chronicle of the Year] else { sect } } else [#year · A Chronicle of the Year])
  if calc.even(p) {
    grid(columns: (auto, auto, 1fr), column-gutter: 10pt, align: (left + horizon, left + horizon, right + horizon),
      folio, outer, inner)
  } else {
    grid(columns: (1fr, auto, auto), column-gutter: 10pt, align: (left + horizon, right + horizon, right + horizon),
      inner, outer, folio)
  }
  v(-4pt)
  line(length: 100%, stroke: 0.4pt + hair)
}

#let drop-folio = context if opens-section(here().page()) {
  align(center, text(font: sans, size: 7.6pt, fill: muted, str(here().page())))
}

// ------------------------------------------------------------- document
#set document(
  title: [#year: A Chronicle of the Year],
  author: "current-events-context",
  keywords: ("chronicle", "current events", str(year), "Wikipedia Current Events portal"),
  description: "Day-by-day chronicle of " + str(year) + ". Database SHA-256 " + meta.database_sha256,
)
#set page(
  paper: "us-letter",
  margin: (inside: 0.9in, outside: 0.72in, top: 0.95in, bottom: 0.8in),
  binding: left,
  header: running-head,
  header-ascent: 34%,
  footer: drop-folio,
  footer-descent: 40%,
  fill: white,
)
#set text(font: text-face, size: 9pt, lang: "en", region: "US", fill: ink, hyphenate: true,
  costs: (hyphenation: 80%, runt: 120%, widow: 200%, orphan: 200%))
#set par(justify: true, leading: 0.58em, spacing: 0.9em, linebreaks: "optimized",
  justification-limits: (spacing: (min: 85%, max: 125%), tracking: (min: -0.012em, max: 0.012em)))
#set columns(gutter: 0.28in)

#show heading: it => place(hide(it.body))
#show raw: set text(font: mono, size: 0.92em)
#set heading(numbering: none)

// ----------------------------------------------------------- components
#let title-block(title, eyebrow: none, dek: none) = {
  if eyebrow != none { kicker(eyebrow); v(6pt) }
  text(font: display-face, size: 30pt, weight: "regular", tracking: -0.3pt, title)
  if dek != none { v(4pt); block(width: 85%, text(font: head-face, size: 11pt, style: "italic", fill: muted, dek)) }
  v(14pt)
}

#let badge(n) = box(circle(radius: 5.2pt, fill: accent, stroke: none,
  align(center + horizon, text(font: sans, size: 6.4pt, weight: "bold", fill: white, str(n)))))
#let callout(n, dy: -1pt) = if n != none { place(top + right, dx: 17pt, dy: dy, badge(n)) }

#let cite-line(cites) = if cites.len() > 0 {
  h(3pt)
  box(text(font: sans, size: 6.5pt, fill: muted, tracking: 0.1pt,
    cites.map(c => link(c.url, c.name)).join(text(fill: faint, " · "))))
}

#let note-box(n, page-ref: none) = block(
  width: 100%, fill: tint, inset: (left: 7pt, right: 6pt, y: 5.5pt),
  stroke: (left: 1.6pt + accent), above: 5pt, below: 7pt, breakable: true,
)[
  #set par(justify: false, leading: 0.5em)
  #text(font: sans, size: 6.2pt, weight: "bold", tracking: 0.9pt, fill: accent)[#upper(n.label) · #upper(n.state)]
  #v(1.5pt)
  #text(size: 8.2pt, n.statement)
  #v(1pt)
  #text(font: sans, size: 6.8pt, fill: muted)[#n.note #if n.evidence.len() > 0 [Evidence: #n.evidence.map(e => link(e.url, e.name)).join("; ").]]
]

#let event-block(e, color, mark: none) = block(above: 3.4pt, below: 3.4pt, inset: (left: 7.5pt), width: 100%, sticky: e.notes.len() > 0)[
  #metadata(e.id)<ev>
  #place(top + left, dx: -7.5pt, dy: 2.9pt, square(size: 2.9pt, fill: color, stroke: none))
  #callout(mark, dy: 4pt)
  #e.text#cite-line(e.cites)
]

#let group-block(g, color, mark: none) = {
  if g.path.len() > 0 {
    block(above: 6pt, below: 2.6pt, sticky: true, width: 100%)[
      #set par(justify: false, leading: 0.45em)
      #callout(mark)
      #text(font: caption-face, size: 7.9pt, style: "italic", fill: muted,
        g.path.join(text(style: "normal", fill: faint, " › ")))
    ]
  }
}

#let category-block(s, mark: none) = block(above: 8.5pt, below: 3.5pt, sticky: true, width: 100%)[
  #callout(mark)
  #box(baseline: 0.5pt, square(size: 5pt, fill: catcolor.at(s.key), stroke: none))
  #h(3pt)
  #text(font: sans, size: 6.6pt, weight: "bold", tracking: 1pt, fill: catcolor.at(s.key), upper(s.name))
]

#let day-header(d, m, mark: none) = block(above: 13pt, below: 4pt, sticky: true, breakable: false, width: 100%)[
  #heading(level: 2, outlined: false, bookmarked: true, str(d.day) + " " + m.name + ", " + d.weekday)
  #metadata((date: d.date, day: d.day, month: m.name))<daymark>
  #line(length: 100%, stroke: 0.7pt + ink)
  #v(0.5pt)
  #callout(mark)
  #grid(columns: (auto, 1fr, auto), column-gutter: 6pt, align: (left + bottom, left + bottom, right + bottom),
    text(font: display-face, size: 23pt, weight: "semibold", top-edge: "cap-height", bottom-edge: "baseline", str(d.day)),
    pad(bottom: 0.6pt, stack(spacing: 2.6pt,
      text(font: sans, size: 6.8pt, weight: "bold", tracking: 1pt, upper(d.weekday)),
      text(font: sans, size: 6.8pt, fill: muted, [#m.name #year]))),
    pad(bottom: 0.6pt, text(font: sans, size: 6.4pt, fill: faint, plural(d.count, "entry", "entries"))),
  )
]

#let render-day(d, m) = {
  day-header(d, m)
  for s in d.sections {
    category-block(s)
    let color = catcolor.at(s.key)
    for g in s.groups {
      group-block(g, color)
      for e in g.events {
        event-block(e, color)
        for n in e.notes { note-box(n) }
      }
    }
  }
}

// --------------------------------------------------------------- charts
#let year-strip(cell: 7.9pt, gap: 1.25pt, lo: heat-lo, hi: heat-hi, label-fill: muted) = {
  let counts = data.year_counts
  let mx = calc.max(..counts)
  let mn = calc.min(..counts)
  let offset = data.first_weekday
  let weeks = calc.ceil((counts.len() + offset) / 7)
  // Month labels on the week in which each month begins.
  let starts = ()
  let acc = 0
  for m in data.months.map(x => x.length) { starts.push(calc.floor((acc + offset) / 7)); acc += m }
  let labels = range(weeks).map(w => {
    let i = starts.position(s => s == w)
    if i != none { text(font: sans, size: 5.8pt, weight: "semibold", tracking: 0.6pt, fill: label-fill, upper(month-names.at(i).slice(0, 3))) } else { [] }
  })
  let cells = ()
  for wd in range(7) {
    for w in range(weeks) {
      let i = w * 7 + wd - offset
      if i >= 0 and i < counts.len() {
        let t = 0.1 + 0.9 * (counts.at(i) - mn) / calc.max(1, mx - mn)
        cells.push(box(width: cell, height: cell, fill: color.mix((hi, t * 100%), (lo, (1 - t) * 100%))))
      } else { cells.push(box(width: cell, height: cell)) }
    }
  }
  grid(columns: weeks * (cell,), column-gutter: gap, row-gutter: gap, align: left + bottom,
    ..labels.map(l => box(width: cell, height: 9pt, place(bottom + left, l))), ..cells)
}

#let legend-ramp(lo: heat-lo, hi: heat-hi, fill: muted) = {
  let counts = data.year_counts
  set text(font: sans, size: 6.2pt, fill: fill)
  [Fewer entries]
  h(4pt)
  for t in (0.1, 0.32, 0.55, 0.78, 1.0) { box(width: 7pt, height: 7pt, fill: color.mix((hi, t * 100%), (lo, (1 - t) * 100%))); h(1.2pt) }
  h(3pt)
  [More · range #calc.min(..counts)–#calc.max(..counts) per day]
}

#let hbar(value, maximum, width, color, height: 6pt) = box(width: width, height: height,
  box(width: width * value / maximum, height: height, fill: color))

#let month-columns(height: 150pt) = {
  let totals = data.month_categories.map(r => r.sum())
  let mx = calc.max(..totals)
  let keys = data.category_order
  let bars = data.month_categories.enumerate().map(((i, row)) => {
    let segs = ()
    for (j, v) in row.enumerate() {
      if v > 0 { segs.push(rect(width: 100%, height: height * v / mx, fill: catcolor.at(keys.at(j)), stroke: (top: 0.35pt + white))) }
    }
    align(bottom + center, stack(dir: ttb,
      text(font: sans, size: 6.4pt, weight: "semibold", num(totals.at(i))), v(2.5pt),
      box(width: 72%, stack(dir: btt, ..segs))))
  })
  grid(columns: 12 * (1fr,), column-gutter: 4pt, row-gutter: 5pt, align: center + bottom,
    ..bars, ..month-names.map(n => text(font: sans, size: 6.4pt, fill: muted, tracking: 0.6pt, upper(n.slice(0, 3)))))
}

#let category-legend(cats, total, width: 1fr, bar: 90pt) = {
  set text(hyphenate: false)
  set par(justify: false)
  let mx = calc.max(..cats.map(c => c.count))
  grid(columns: (8pt, 1fr, auto, bar), column-gutter: 6pt, row-gutter: 5.2pt, align: (left + horizon, left + horizon, right + horizon, left + horizon),
    ..cats.map(c => (
      box(width: 6pt, height: 6pt, fill: catcolor.at(c.key)),
      text(font: sans, size: 7.6pt, c.name),
      text(font: sans, size: 7.6pt, weight: "semibold", num(c.count)),
      hbar(c.count, mx, bar, catcolor.at(c.key).lighten(25%), height: 5pt),
    )).flatten())
}

#let month-calendar(m, cell-h: 0.52in) = {
  let counts = m.counts
  let all = data.year_counts
  let mx = calc.max(..all)
  let mn = calc.min(..all)
  let cells = range(m.first_weekday).map(_ => [])
  for (i, c) in counts.enumerate() {
    let t = 0.1 + 0.9 * (c - mn) / calc.max(1, mx - mn)
    let dark = t > 0.55
    cells.push(box(width: 100%, height: cell-h, fill: heat(t), inset: 4pt)[
      #text(font: sans, size: 8pt, weight: "bold", fill: if dark { white } else { ink }, str(i + 1))
      #place(bottom + right, text(font: sans, size: 6.6pt, fill: if dark { white.transparentize(15%) } else { muted }, str(c)))
    ])
  }
  grid(columns: 7 * (1fr,), column-gutter: 2pt, row-gutter: 2pt,
    ..("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun").map(d => pad(bottom: 2pt, smallcaps-label(d, size: 6pt))),
    ..cells)
}

#let story-ribbon(s, total-max) = {
  let mx = calc.max(1, ..s.months)
  box(grid(columns: 12 * (7.4pt,), column-gutter: 1.1pt,
    ..s.months.map(v => box(width: 7.4pt, height: 7.4pt,
      fill: if v == 0 { rgb("#f3f0ea") } else { heat(0.15 + 0.85 * v / mx) }))))
}

// ================================================================ COVER
#page(margin: 0pt, header: none, fill: night)[
  #place(top + left, dx: 0.85in, dy: 0.9in, smallcaps-label(fill: rgb("#c9b9a3"), size: 7.5pt)[Current Events Context #h(6pt) · #h(6pt) Annual chronicle])
  #place(top + left, dx: 0.78in, dy: 1.55in, text(font: display-face, size: 168pt, weight: "light", fill: rgb("#f3ede3"), tracking: -4pt, str(year)))
  #place(top + left, dx: 0.85in, dy: 4.35in, text(font: display-face, size: 32pt, style: "italic", fill: rgb("#f3ede3"))[A Chronicle of the Year])
  #place(top + left, dx: 0.85in, dy: 4.98in, block(width: 5in, text(font: head-face, size: 12.5pt, fill: rgb("#c9b9a3"))[World events day by day, as recorded on the Current Events portal of the English-language Wikipedia]))
  #place(top + left, dx: 0.85in, dy: 6.35in, year-strip(cell: 7.6pt, gap: 1.35pt, lo: rgb("#27303b"), hi: rgb("#e0a26a"), label-fill: rgb("#8f8578")))
  #place(top + left, dx: 0.85in, dy: 7.62in, block(width: 6.6in, text(font: sans, size: 7pt, fill: rgb("#8f8578"))[Each square is one day of #year; its tone shows how many entries were recorded that day.]))
  #place(bottom + left, dx: 0.85in, dy: -0.85in, block(width: 6.8in)[
    #line(length: 100%, stroke: 0.5pt + rgb("#3a4552"))
    #v(6pt)
    #grid(columns: (1fr, auto),
      text(font: sans, size: 8pt, fill: rgb("#c9b9a3"))[#num(meta.entries) entries · #meta.days days · #num(meta.citations) cited reports],
      text(font: sans, size: 8pt, fill: rgb("#8f8578"))[#if meta.sample [Design proof · ] Edition of #pretty-date(meta.edition_date) #meta.edition_date.slice(0, 4)])
  ])
]

#page(header: none)[]

// =========================================================== TITLE PAGE
#page(header: none)[
  #v(1.4in)
  #align(center)[
    #smallcaps-label(size: 7.5pt)[Current Events Context]
    #v(22pt)
    #text(font: display-face, size: 84pt, weight: "light", tracking: -1.5pt, str(year))
    #v(-18pt)
    #text(font: display-face, size: 26pt, style: "italic")[A Chronicle of the Year]
    #v(18pt)
    #line(length: 0.9in, stroke: 0.8pt + accent)
    #v(16pt)
    #block(width: 4.2in, text(font: head-face, size: 11.5pt, fill: muted)[World events day by day, as recorded on the Current Events portal of the English-language Wikipedia, with the sources its editors cited])
  ]
  #place(bottom + center, dy: -0.2in, align(center)[
    #text(font: sans, size: 7.6pt, fill: muted)[Reading edition · #pretty-date(meta.edition_date) #meta.edition_date.slice(0, 4)]
    #if meta.sample { v(4pt); text(font: sans, size: 7.6pt, weight: "bold", fill: accent)[DESIGN PROOF — SELECTED DATES ONLY] }
  ])
]

// ======================================================== EDITION PAGE
#page(header: none)[
  #set text(font: sans, size: 7.6pt, fill: muted)
  #set par(justify: false, leading: 0.55em, spacing: 0.95em)
  #align(bottom)[
    #block(width: 4.6in)[
      #text(font: head-face, size: 10pt, style: "italic", fill: ink)[#year: A Chronicle of the Year]

      Reading edition of #pretty-date(meta.edition_date) #meta.edition_date.slice(0, 4), typeset from the #year annual preservation database of the current-events-context archive (publication contract #raw(meta.contract)).

      The entries reprinted here are the work of the volunteer editors of the Current Events portal of the English-language Wikipedia. They are reused under the Creative Commons Attribution-ShareAlike 4.0 International license (#link("https://creativecommons.org/licenses/by-sa/4.0/")[creativecommons.org/licenses/by-sa/4.0]); this edition is offered under the same terms. The page and revision history behind every day is identified in the Register of Source Revisions. Names of news organizations identify citations; their articles are not reproduced.

      This book is a source chronicle, not an independently verified history. Entries keep their original wording, including errors and reports later superseded. Editorial notes are marked as such and are limited to their stated scope.

      #text(weight: "semibold", fill: ink)[How to cite.] _#year: A Chronicle of the Year_, reading edition of #meta.edition_date, current-events-context, compiled from the Wikipedia Current Events portal (pinned revisions), database SHA-256 #raw(meta.database_sha256.slice(0, 16))….

      Set in Source Serif 4 and Source Sans 3. Typeset with Typst. Full production details appear in the colophon.
    ]
  ]
]

// ============================================================= CONTENTS
#let front-titles = ("About This Volume", "Reading an Entry", "The Year at a Glance")
#let back-titles = ("Notes on Sources and Method", "Editorial Notes and Checks", "Publications Cited", "Register of Source Revisions", "Index", "Colophon")

#page(header: none)[
  #recto-start()
  #title-block([Contents])
  #context {
    let heads = query(heading.where(level: 1))
    let find(t) = heads.find(h => h.body.has("text") and h.body.text == t)
    let entry(t, detail: none) = {
      let hd = find(t)
      if hd == none { return }
      let p = hd.location().page()
      block(above: 0pt, below: 0pt, link(hd.location(), grid(columns: (1fr, auto), column-gutter: 8pt, align: (left + bottom, right + bottom),
        [#text(font: head-face, size: 11pt, t)#if detail != none { h(6pt); text(font: sans, size: 7pt, fill: faint, detail) } #box(width: 1fr, repeat(text(fill: hair, size: 8pt, ".") + h(3pt)))],
        text(font: sans, size: 8.6pt, weight: "semibold", str(p)))))
      v(6.4pt)
    }
    let group(label, items) = {
      v(12pt)
      kicker(label)
      v(8pt)
      items
    }
    group([Introduction], front-titles.map(t => entry(t)).join())
    group([The Chronicle], data.months.map(m => entry(m.name, detail: plural(m.entries, "entry", "entries"))).join())
    group([Reference], back-titles.map(t => entry(t)).join())
  }
]

// ================================================================ ABOUT
#let prose(body) = {
  set text(size: 10pt)
  set par(leading: 0.66em, spacing: 1.05em, first-line-indent: (amount: 1.2em, all: false))
  align(center, block(width: 5.05in, align(left, body)))
}
#let runin(t) = text(font: sans, size: 7.4pt, weight: "bold", tracking: 0.9pt, fill: accent, upper(t)) + h(5pt)

#let notes-by-kind(kind) = data.months.map(m => m.days.map(d => d.sections.map(s => s.groups.map(g => g.events.map(e => e.notes.filter(n => n.label == kind).len()))))).flatten().sum(default: 0)

#section-mark("About This Volume")
#heading(level: 1, "About This Volume")
#prose[
  #v(0.25in)
  #title-block([About This Volume], eyebrow: [Introduction])

  This book is a day-by-day chronicle of #year. It reprints, in calendar order, every one of the #num(meta.entries) event entries recorded for the year on the Current Events portal of the English-language Wikipedia, together with the story headings under which the portal's editors filed them and the news reports they cited.

  #runin[The source]The Current Events portal is a collaboratively edited digest of the news. Each day's page lists short, present-tense summaries under subject headings — armed conflicts and attacks, politics and elections, disasters and accidents, and so on — usually with a link to one or more published reports. Entries are written close to the events they describe and are revised afterward. They reflect the judgment of volunteer editors about what was notable, and the coverage of the largely English-language press on which they draw. They are neither a complete record of the year nor a neutral sample of it.

  #runin[The text]Each day's page was captured at a specific revision, identified in the Register of Source Revisions, and its entries were extracted mechanically, keeping their order, hierarchy and wording. The original wording is retained throughout, including errors of fact, spelling or grammar, and reports that later proved incomplete. Only typographic conventions have changed: straight quotation marks are printed as curly ones, and invisible formatting characters are omitted.

  #runin[Arrangement]The chronicle is divided into twelve monthly chapters. Each opens with a summary page: a calendar showing how many entries were recorded on each day, the balance of subject categories, and the stories that recurred most often. Within each day, entries appear under the portal's own categories and in the portal's order. Where the portal filed an entry under a continuing story, that heading is printed in italics above it.

  #runin[Sources]The news organizations cited for each entry are named in small type at its end; in the digital edition each name links to the cited report. A citation shows what the portal's editors relied on. It does not mean that the report has been consulted for this edition, or that it supports every detail of the entry. #plural(meta.uncited, "entry was", "entries were") left uncited by the portal.

  #runin[Editorial notes]A small number of entries have been checked against primary or publisher sources. Where that research supports, narrows, corrects or re-dates an entry, a shaded note follows it; the original entry is never altered. This edition carries #plural(notes-by-kind("Editorial note"), "editorial note", "editorial notes") and #plural(notes-by-kind("Scoped check"), "scoped check", "scoped checks"), each limited to its stated scope and all listed under Editorial Notes and Checks. Every other entry stands as the portal recorded it and has not been independently verified.

  #runin[Counts]All counts and charts measure entries in the archive. They describe the attention of the portal, not the scale, severity or importance of events. A single continuing story may produce entries on many days, and a single entry may report several developments.

  #runin[Index]The index lists the Wikipedia articles linked from each entry and from the story headings above it, as the portal's editors wrote them, with the pages on which they appear. Titles have not been merged or reclassified, except that, as on Wikipedia, the case of the first letter is disregarded.

  #runin[Preservation]This volume is a reading edition. Its authoritative counterpart is the annual preservation database, which retains the exact source pages, link markup and full citation addresses. The fingerprint of the database used for this edition is printed in the colophon.
]

// ======================================================== READING AN ENTRY
#pagebreak(weak: true)
#section-mark("Reading an Entry")
#heading(level: 1, "Reading an Entry")
#{
  let m = data.months.first()
  let d = m.days.first()
  let s = d.sections.first()
  let g = s.groups.find(g => g.path.len() > 0)
  let color = catcolor.at(s.key)
  v(0.25in)
  title-block([Reading an Entry], eyebrow: [Introduction], dek: [Every day of the year follows the same pattern. The opening of #pretty-date(d.date) is reproduced here with its parts identified.])
  grid(columns: (3.3in, 1fr), column-gutter: 0.55in,
    block(width: 100%, inset: (y: 4pt))[
      #day-header(d, m, mark: 1)
      #category-block(s, mark: 2)
      #group-block(g, color, mark: 3)
      #event-block(g.events.first(), color, mark: 4)
      #if g.events.len() > 1 { event-block(g.events.at(1), color) }
    ],
    {
      set par(justify: false, leading: 0.55em, spacing: 0.7em)
      let item(n, t, body) = grid(columns: (14pt, 1fr), column-gutter: 6pt, badge(n),
        [#text(font: sans, size: 7.6pt, weight: "bold", t) \ #text(size: 8.6pt, fill: muted, body)])
      v(10pt)
      item(1, [The day], [Date and weekday as given by the portal, with the number of entries recorded that day. Days follow in calendar order; the running heads give the range of dates on each page.])
      v(10pt)
      item(2, [Category], [The portal's subject heading, printed as archived. The colored square is repeated beside each entry and in the charts.])
      v(10pt)
      item(3, [Story heading], [The continuing story under which the entry was filed. Nested stories are separated by ›. Entries filed without a story heading appear directly under the category.])
      v(10pt)
      item(4, [Entry and sources], [The text of the entry, unaltered, followed by the news organizations it cites. Several entries may share one story heading.])
      v(10pt)
      grid(columns: (14pt, 1fr), column-gutter: 6pt, box(width: 10pt, height: 10pt, fill: tint, stroke: (left: 1.6pt + accent)),
        [#text(font: sans, size: 7.6pt, weight: "bold")[Editorial note] \ #text(size: 8.6pt, fill: muted)[Where an entry has been researched for this edition, a shaded note follows it, stating what was checked and what the evidence shows.]])
    })
  v(1fr)
  block(width: 100%, inset: (top: 10pt), stroke: (top: 0.4pt + hair))[
    #set par(justify: false)
    #grid(columns: (1fr, 1fr), column-gutter: 0.35in,
      [#kicker([Category colors]) #v(6pt) #category-legend(data.categories, meta.entries, bar: 60pt)],
      [#kicker([On the page]) #v(6pt)
        #text(size: 8.6pt, fill: muted)[Pages are numbered continuously from the cover. Months begin on a right-hand page with a summary of the month. The index refers to pages; in the digital edition, the contents and bookmarks link to every month and day.]])
  ]
}

// ===================================================== YEAR AT A GLANCE
#section-end()
#pagebreak(to: "even", weak: true)
#recto-start()
#section-mark("The Year at a Glance")
#heading(level: 1, "The Year at a Glance")
#{
  title-block([The Year at a Glance], eyebrow: [Introduction], dek: [The shape of the year as the portal recorded it. Counts measure entries in the archive, not the significance of events.])
  let stat(n, label) = stack(spacing: 4pt,
    text(font: display-face, size: 30pt, weight: "regular", n),
    text(font: sans, size: 7pt, weight: "semibold", tracking: 0.8pt, fill: muted, upper(label)))
  grid(columns: 5 * (1fr,), column-gutter: 10pt,
    stat(str(meta.days), [days]),
    stat(num(meta.entries), [entries]),
    stat(num(meta.citations), [citations]),
    stat(num(meta.publishers), [publications]),
    stat(num(meta.subjects), [indexed articles]))
  v(20pt)
  line(length: 100%, stroke: 0.4pt + hair)
  v(10pt)
  kicker([Every day of the year])
  v(8pt)
  year-strip()
  v(5pt)
  legend-ramp()
  v(20pt)
  line(length: 100%, stroke: 0.4pt + hair)
  v(10pt)
  grid(columns: (1fr, 2.35in), column-gutter: 0.35in,
    [#kicker([Entries by month and category]) #v(10pt) #month-columns(height: 165pt)],
    [#kicker([The year by category]) #v(10pt) #category-legend(data.categories, meta.entries, bar: 52pt)
     #v(10pt)
     #text(font: sans, size: 6.8pt, fill: muted)[Category labels are grouped here for counting; a few days use variant spellings, which are printed as archived in the chronicle.]])
}
#pagebreak()
#{
  v(0.1in)
  grid(columns: (1fr, 2.3in), column-gutter: 0.4in,
    {
      kicker([Running stories])
      set text(hyphenate: false)
      set par(justify: false)
      v(4pt)
      text(font: head-face, size: 9.5pt, style: "italic", fill: muted)[The story headings that appeared on the most days, with their monthly pattern.]
      v(10pt)
      let mxd = data.stories.first().days
      grid(columns: (1fr, auto, auto), column-gutter: 8pt, row-gutter: 6.2pt, align: (left + horizon, right + horizon, left + horizon),
        [], text(font: sans, size: 5.8pt, fill: faint, tracking: 0.6pt, upper[days]),
        box(grid(columns: 12 * (7.4pt,), column-gutter: 1.1pt, ..month-names.map(n => align(center, text(font: sans, size: 5.4pt, fill: faint, n.first()))))),
        ..data.stories.map(s => (
          text(font: caption-face, size: 8.2pt, s.name),
          text(font: sans, size: 7.4pt, weight: "semibold", str(s.days)),
          story-ribbon(s, mxd),
        )).flatten())
    },
    {
      kicker([Most-cited sources])
      v(4pt)
      text(font: head-face, size: 9.5pt, style: "italic", fill: muted)[News organizations by number of citations.]
      v(10pt)
      let mx = data.top_publishers.first().count
      grid(columns: (1fr, auto), column-gutter: 6pt, row-gutter: 4pt, align: (left + horizon, right + horizon),
        ..data.top_publishers.map(p => (
          stack(spacing: 2.2pt, text(font: sans, size: 7.6pt, p.name), hbar(p.count, mx, 1.6in, accent.lighten(35%), height: 3.2pt)),
          text(font: sans, size: 7.4pt, weight: "semibold", num(p.count)),
        )).flatten())
      v(12pt)
      text(font: sans, size: 6.8pt, fill: muted)[Names as given in the portal's citations. Variant names for one organization (for example "AP" and "AP News") are counted separately. The full list appears under Publications Cited.]
    })
}

// ============================================================ CHRONICLE
#let numeral(n) = if n < 10 { "0" + str(n) } else { str(n) }

#for m in data.months {
  section-end()
  pagebreak(to: "odd", weak: true)
  page(header: none, columns: 1)[
    #recto-start()
    #section-mark(m.name)
    #heading(level: 1, m.name)
    #place(top + right, dx: 0.05in, dy: -0.25in, text(font: display-face, size: 150pt, weight: "light", fill: tint.darken(4%), numeral(m.num)))
    #v(0.35in)
    #kicker([Chapter #numeral(m.num) · The Chronicle])
    #v(4pt)
    #text(font: display-face, size: 56pt, weight: "regular", tracking: -0.8pt, m.name)
    #v(-6pt)
    #text(font: head-face, size: 12pt, style: "italic", fill: muted)[#m.length days · #plural(m.entries, "entry", "entries") · #plural(m.citations, "citation", "citations")]
    #v(22pt)
    #month-calendar(m)
    #v(5pt)
    #legend-ramp()
    #v(22pt)
    #grid(columns: (1fr, 1fr), column-gutter: 0.4in,
      {
        kicker([Categories this month])
        v(8pt)
        category-legend(m.categories, m.entries, bar: 58pt)
      },
      {
        kicker([Running stories])
        v(8pt)
        grid(columns: (1fr, auto), column-gutter: 8pt, row-gutter: 5.4pt, align: (left + horizon, right + horizon),
          ..m.stories.map(s => (
            text(font: caption-face, size: 8.2pt, s.name),
            text(font: sans, size: 7pt, fill: muted)[#s.days #if s.days == 1 [day] else [days]],
          )).flatten())
      })
    #v(1fr)
    #text(font: sans, size: 6.6pt, fill: faint)[Calendar figures are entries recorded for each day. Running stories are counted by the number of days on which a story heading appears.]
  ]
  set page(columns: 2)
  for d in m.days { render-day(d, m) }
}

// ========================================================== BACK MATTER
#set page(columns: 1)
#section-end()
#pagebreak(to: "odd", weak: true)
#recto-start()
#section-mark("Notes on Sources and Method")
#heading(level: 1, "Notes on Sources and Method")
#{
  title-block([Notes on Sources and Method], eyebrow: [Reference])
  set par(first-line-indent: 0pt)
  columns(2)[
    #set text(size: 8.8pt)
    #runin[Capture]Each daily page of the portal was captured once, at the revision identified in the Register of Source Revisions, and stored byte for byte with a cryptographic fingerprint. A captured revision may include corrections made after the day itself; the chronicle therefore reflects the record as later revised, not necessarily what was known on the day.

    #runin[Extraction]Entries were extracted from the captured wiki source by a deterministic program, without manual rewriting or model-generated text. Category headings, story headings and entries keep their source order and nesting. Links and citations were captured before markup was removed. No content was silently discarded: structures the program could not classify were recorded for review.

    #runin[Retained notices]The extraction program recorded the following notices about source structure. Most were resolved by general rules; none implies a judgment about the accuracy of an entry.
    #v(4pt)
    #block(width: 100%, inset: (left: 8pt))[
      #set par(justify: false)
      #grid(columns: (1fr, auto), row-gutter: 4pt, column-gutter: 8pt,
        ..data.notices.map(n => (text(font: mono, size: 6.6pt, n.code.replace("_", "_\u{200B}")), text(font: sans, size: 7.4pt, weight: "semibold", str(n.count)))).flatten())
    ]

    #runin[Unclassified passage]One pasted passage on #pretty-date(data.fragments.first().date) contains malformed structure. Its #data.fragments.len() fragments are not counted as entries or assigned a category, and are reproduced here as source evidence:
    #for f in data.fragments [
      #block(width: 100%, inset: (left: 8pt, y: 2pt), stroke: (left: 0.6pt + hair))[#text(font: sans, size: 6.4pt, fill: muted)[Source line #f.line] \ #text(font: mono, size: 6.4pt, f.raw)]
    ]

    #runin[Empty marker]A literal empty bullet on 5 July is kept in the database as an empty marker of unknown role. It is not an entry and is omitted from the chronicle and index.

    #runin[Typography]Straight quotation marks are printed as curly quotation marks, using their position in the text; an apostrophe-like mark in a name may therefore appear as ’. Invisible direction and spacing marks are omitted. All other characters, including original dashes, accents and non-Latin script, are printed as captured.

    #runin[Not included]This edition does not reproduce publisher articles, images or full citation addresses, which remain in the preservation database. No new reporting, illustration or model-written summary has been added.
  ]
}

#section-end()
#pagebreak(weak: true)
#section-mark("Editorial Notes and Checks")
#heading(level: 1, "Editorial Notes and Checks")
#{
  title-block([Editorial Notes and Checks], eyebrow: [Reference], dek: [Entries researched for this edition. Each finding concerns only its stated scope; access failures do not establish that a claim is false.])
  context {
    let pages = (:)
    for m in query(<ev>) { pages.insert(str(m.value), m.location().page()) }
    set par(justify: false, leading: 0.5em)
    table(columns: (0.75in, 0.4in, 1.05in, 1fr), stroke: none, inset: (x: 0pt, y: 5pt), column-gutter: 10pt,
      table.hline(stroke: 0.6pt + ink),
      table.header(..([Date], [Page], [Finding], [Scope]).map(h => smallcaps-label(h, size: 6.2pt))),
      table.hline(stroke: 0.4pt + hair),
      ..data.notes.map(n => (
        text(font: sans, size: 7.6pt, pretty-date(n.date)),
        text(font: sans, size: 7.6pt, weight: "semibold", str(pages.at(str(n.id), default: "—"))),
        text(font: sans, size: 7.2pt, fill: accent)[#n.label \ #text(fill: muted, n.state)],
        text(size: 8pt, n.statement),
      )).flatten(),
      table.hline(stroke: 0.6pt + ink))
  }
}

#section-end()
#pagebreak(to: "odd", weak: true)
#recto-start()
#section-mark("Publications Cited")
#heading(level: 1, "Publications Cited")
#{
  title-block([Publications Cited], eyebrow: [Reference], dek: [Every news organization named in a citation, with the number of times it is cited. Names are given as the portal wrote them.])
  columns(4, gutter: 14pt)[
    #set par(justify: false, leading: 0.4em, spacing: 0.4em, hanging-indent: 6pt)
    #set text(font: sans, size: 6.9pt)
    #for p in data.publishers {
      [#p.name #box(width: 1fr, repeat(text(fill: hair, ".") + h(1.5pt))) #text(weight: "semibold", str(p.count))]
      parbreak()
    }
  ]
}

#section-end()
#pagebreak(to: "odd", weak: true)
#recto-start()
#section-mark("Register of Source Revisions")
#heading(level: 1, "Register of Source Revisions")
#{
  title-block([Register of Source Revisions], eyebrow: [Reference], dek: [The exact revision of each daily portal page from which this edition was made, with its revision timestamp and the SHA-256 fingerprint of the captured source.])
  set par(justify: false)
  table(columns: (0.72in, 0.78in, 1.18in, 1fr), stroke: none, inset: (x: 0pt, y: 2.15pt), column-gutter: 8pt,
    table.header(..([Portal date], [Revision], [Revision time (UTC)], [SHA-256 of captured page]).map(h => smallcaps-label(h, size: 6pt)), table.hline(stroke: 0.5pt + ink)),
    ..data.register.enumerate().map(((i, r)) => (
      text(font: sans, size: 7pt, r.date),
      text(font: sans, size: 7pt, link(r.url, str(r.revision))),
      text(font: sans, size: 7pt, fill: muted, r.timestamp.replace("T", " ").replace("Z", "")),
      text(font: mono, size: 6.1pt, fill: muted, r.sha),
    )).flatten())
  v(8pt)
  text(font: sans, size: 6.8pt, fill: muted)[A revision can be viewed at en.wikipedia.org/w/index.php?oldid= followed by the revision number. Page histories record the contributors to each day.]
}

#section-end()
#pagebreak(to: "odd", weak: true)
#page(columns: 3)[
  #recto-start()
  #section-mark("Index")
  #heading(level: 1, "Index")
  #place(top, scope: "parent", float: true, clearance: 14pt)[
    #title-block([Index], eyebrow: [Reference], dek: [Wikipedia articles linked from entries and their story headings, as written by the portal's editors, with page references.])
  ]
  #set par(justify: false, leading: 0.36em, spacing: 0.36em, hanging-indent: 8pt)
  #set text(font: sans, size: 6.8pt)
  #context {
    let pages = (:)
    for m in query(<ev>) { pages.insert(str(m.value), m.location().page()) }
    let current = none
    for item in data.index {
      if item.letter != current {
        current = item.letter
        block(above: 9pt, below: 4pt, sticky: true, text(font: display-face, size: 15pt, fill: accent, item.letter))
      }
      [#item.term#h(4pt)#text(fill: muted, ranges(item.ids.map(i => pages.at(str(i)))))]
      parbreak()
    }
  }
]

// ============================================================= COLOPHON
#section-end()
#pagebreak(weak: true)
#page(header: none, columns: 1)[
  #section-mark("Colophon")
  #heading(level: 1, "Colophon")
  #align(bottom, block(width: 4.6in)[
    #set text(font: sans, size: 7.4pt, fill: muted)
    #set par(justify: false, leading: 0.55em, spacing: 0.9em)
    #kicker([Colophon])
    #v(6pt)
    #text(font: head-face, size: 10pt, fill: ink, style: "italic")[Set in Source Serif 4, in its small-text, caption, subhead and display optical sizes, with Source Sans 3 for labels and figures. Both typefaces were designed for Adobe by Frank Grießhammer and Paul D. Hunt and are released under the SIL Open Font License.]

    Typeset with Typst #meta.typst from data selected by #raw("reference/yearbook/typeset/book.py"). Every chart and figure is computed from the same database as the text.

    #grid(columns: (auto, 1fr), column-gutter: 10pt, row-gutter: 5pt,
      [Edition], [#meta.edition_date · #meta.version#if meta.sample [ · design proof]],
      [Contents], [#num(meta.entries) entries on #meta.days days · #num(meta.structural) structural records · #num(meta.citations) citations · #num(meta.subjects) index headings],
      [Database], text(font: mono, size: 6.3pt, meta.database_sha256),
      [Generator], text(font: mono, size: 6.3pt, meta.generator_sha256),
      [Template], text(font: mono, size: 6.3pt, meta.template_sha256),
    )

    Wikipedia content is used under CC BY-SA 4.0; attribution is to the contributors of the Current Events portal pages identified in the Register of Source Revisions.
  ])
]
