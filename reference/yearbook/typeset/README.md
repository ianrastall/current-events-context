# Typeset yearbook

A designed reading edition of an annual archive: *2025: A Chronicle of the
Year*. It is built from the same SQLite edition as the
[print chronicle](../README.md), but it is set as a book for reading. The
print chronicle remains the preservation-oriented printout, with full URL and
source registers. Neither one replaces the database.

## Design

- US Letter, mirrored margins, two-column chronicle. Running heads give the
  range of dates on each page, as a dictionary does. Chapter openers carry a
  drop folio.
- Source Serif 4 (small-text, caption, subhead and display optical sizes) with
  Source Sans 3 for labels and figures. Text is justified and hyphenated, and
  the paragraph breaker is tuned against widows and orphans.
- Front matter: cover, title and edition pages, contents, *About This Volume*,
  an annotated *Reading an Entry* specimen, and a *Year at a Glance* spread.
  The spread has a 365-day heat strip, monthly category columns, running
  stories with monthly ribbons, and the most-cited sources.
- Twelve month chapters open on a recto, each with a calendar heat map,
  category mix and running stories. Days are grouped by portal category, then
  by story heading (italic kicker), with one colour square per category.
  Citations appear as small publisher names linked to the cited URL.
- Editorial reviews and scoped checks are printed as shaded notes directly
  after their entries, and again in a table with page references.
- Back matter: method notes, notes table, publications cited with counts,
  register of source revisions, a page-referenced index of linked articles,
  and a colophon with the database, generator and template SHA-256.
- PDF bookmarks for every section and every day; tagged PDF output.

Presentation-only changes: straight quotes become curly quotes, and invisible
direction and zero-width marks are dropped. Unlike the print chronicle, dashes
are left as captured. Index headings use MediaWiki's case-insensitive first
letter, and underscores become spaces.

## Build

```powershell
python -m pip install -r reference/yearbook/typeset/requirements.txt
python reference/yearbook/typeset/book.py archive/2025.sqlite --edition-date 2026-10-21 `
    --font-dir path/to/source-fonts --keep-json tmp/pdfs/2025-yearbook.json `
    --output dist/2025-yearbook.pdf
python reference/yearbook/typeset/verify.py tmp/pdfs/2025-yearbook.json dist/2025-yearbook.pdf
```

`--font-dir` must contain the static OTF files of
[Source Serif 4](https://github.com/adobe-fonts/source-serif/releases) (4.005)
and [Source Sans 3](https://github.com/adobe-fonts/source-sans/releases)
(3.052). Both are SIL Open Font License. Font files are not committed. System
fonts provide fallback glyphs: Microsoft YaHei/SimSun for the few CJK index
headings and Cambria for the lari sign. `--sample` typesets a labeled proof
of selected dates.

The builder is offline and read-only. `book.py` selects and arranges data into
JSON. `book.typ` holds all of the design and inserts source strings as text,
never as markup. A full compile takes about ten seconds. The PDF timestamp is
the edition date, so identical inputs and versions reproduce the same output.
The output is compacted with object streams.

`verify.py` checks that every entry's text, every cited URL (as a link) and
every index heading appear in the PDF, and that the database SHA-256 is in the
PDF metadata. It does not check facts, and it is no substitute for looking at
the rendered pages.
