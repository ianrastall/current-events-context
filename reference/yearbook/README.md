# Printed annual reference

For the designed reading edition (*2025: A Chronicle of the Year*), see
[typeset/README.md](typeset/README.md).

The PDF is the readable physical preservation layer, derived from a named
annual SQLite edition. It complements the exact-source database and plain-text
Markdown. It is not a new authoritative source or a claim to complete,
independently verified history. The database and Markdown are not modified.

## Design and content

- US Letter, portrait; mirrored binding margins, continuous printed folios,
  embedded Unicode font subsets, selectable text and internal bookmarks.
- A restrained navy/teal textbook layout, monochrome-readable labels and bars,
  a source-coverage overview and twelve calendar/chart chapter openers. Charts
  describe archived assertion counts, not unique incidents or world importance.
- Every source event, in original date/category/order, with topic context,
  stable event IDs, original source citations and separately labeled editorial
  corrections. Original factual errors remain visible.
- Printed research limitations and all prior scoped findings; exact Wikipedia
  revision URLs, IDs and payload hashes for every date; full publisher URLs;
  a page-numbered index of event and topic-ancestor wikilink targets, without inferred entity
  classifications or redirect resolution. No online lookup is necessary to
  read the narrative or use the printed navigation.
- Production provenance and the exact database SHA-256 inside the PDF.
  URLs identify evidence; full publisher articles and the raw binary inputs
  are not reproduced. Photos are not required or newly acquired.

This is a reference chronicle, not a set of newly researched monthly essays.
No synthetic illustrations are presented as historical evidence. The PDF is
not claimed to be PDF/A, digitally signed or a substitute for the exact-source
digital layer.

## Rebuild

Optional PDF dependencies are separate from the collection dependencies:

```powershell
python -m pip install -r reference/yearbook/requirements.txt
python reference/yearbook/build.py 2025/2025.sqlite --edition-date 2026-10-21 --output dist/2025.pdf
python reference/yearbook/verify.py 2025/2025.sqlite dist/2025.pdf
```

The builder is offline. It reads SQLite directly and never acquires sources,
calls a model or changes the database. It renders into a temporary sibling
and installs the PDF atomically. It checks that chronology pagination and the
table of contents converge before installation. The PDF records the generator
hash, ReportLab version and typeface-file hashes; render the same inputs to
obtain the same edition. Creation metadata uses ReportLab's invariant timestamp;
the actual edition date is printed in the book and supplied explicitly above.

`--font-dir` must contain DejaVu Serif regular/bold and DejaVu Sans regular/bold.
Default directories cover standard Windows and Linux installations.
`--fallback-font` may be repeated for additional TTF/TTC coverage. This edition
uses installed Arial for two currency glyphs and SimSun for Chinese link-target
text. Font subsets are embedded; original font files are not redistributed.
Supply suitable, embeddable, licensed equivalents when rebuilding elsewhere.
Missing glyphs cause an error rather than silent squares. Typeface changes
can alter pagination and require a new visually checked PDF edition.

Index alphabetization folds accents while retaining target spelling in print.

Source HTML/Markdown is escaped, not interpreted as typesetting instructions.
Dash/minus variants are normalized to ASCII hyphens for print; other source
text is retained. The named SQLite edition retains original source characters.
Printed publisher URLs in the 2025 edition have no affected dash variants.

`--sample --output tmp/pdfs/design-proof.pdf` produces an explicitly labeled
layout proof using selected dates, including dense pages and editorial notes.
It is not the final complete book. Keep proofs, contact sheets and QA renders
under ignored `tmp/pdfs/`; keep final PDFs in ignored `dist/` for release distribution.
Include a verified PDF in a bundle with `python tools/build_tiers.py build
2025/2025.sqlite --pdf dist/2025.pdf`. Generated PDFs and raster pages do not
become additional canonical repository files.

## Verification and printing

`verify.py` independently extracts the PDF and checks every source assertion,
event label, publisher URL, Wikipedia revision/hash and subject text against
SQLite. It checks dimensions, embedded used fonts, chapter bookmarks and the
edition identity. This is preservation verification, not factual checking or
visual QA. Render and inspect representative and boundary pages with Poppler
after every meaningful layout update. Inspect long URLs, corrected entries,
non-Latin index text, headings, folios and final pages at readable resolution.

Print at 100% scale, duplex, flipping on the long edge. The continuously
numbered book may be bound in sections using its contents page and folios;
avoid shrinking multiple pages onto a sheet. When a separately bound section
begins on an even folio, add a blank recto so its mirrored gutter remains
on the binding side. Color is optional for understanding the content.
