# Book: researched history of the year

`book/` holds the research layer for *2025: A History*, a narrative history built
on the annual archive. It is separate from the preservation edition. The archive
(`archive/2025.sqlite`) is referenced by SHA-256 and never modified. The plan and
chapter outline are in the review doc shared on 21 October 2026.

Decisions: a separate book database, sources published on or before 31 October 2026,
6 × 9 in. trim. Title, authorship wording and licence remain open.

## Layout

| Path | Role |
| --- | --- |
| `schema.sql` | `book-1.0` database schema |
| `tool.py` | Candidate sweep, validation, database build, dossier rendering |
| `2025/book.json` | Book metadata, archive identity, chapter register |
| `2025/<chapter>/inventory.json` | Archive entries the chapter draws on, by section and role, with a note on every decision |
| `2025/<chapter>/dossier.json` | Research questions, opened sources and findings |
| `2025/<chapter>/DOSSIER.md` | Generated readable dossier; edit the JSON, not this file |
| `2025.sqlite` | Generated from the JSON records; rebuilt by `tool.py build` |

The JSON records are authoritative and reviewable as text. The database is a
convenience for querying. Both are committed.

## Rules the tool enforces

- Every inventory entry carries the archive's own locator and structured hash
  (`seed.annual_archive`); any change in the archive fails the build.
- Every inventory decision, including exclusions, carries a note.
- Sources need a tier (1 primary, 2 official data, 3 original reporting,
  4 analysis), an http(s) URL, an access date, and a publication date no later
  than the cutoff. Wikipedia is refused as a source.
- A finding must cite an opened source and an existing question.

Drafted prose will cite `claims`, each supported by `claim_evidence`. Findings
are research notes and are not cited in print.

## Commands

```powershell
python book/tool.py candidates archive/2025.sqlite "tariff|trade war"
python book/tool.py build book/2025
python book/tool.py dossier book/2025 ch02
```

## Chapters and illustrations

`2025/<chapter>/chapter.txt` is the chapter text. Notes are written
`[[S001 locator | S002 locator]]` and refer to dossier sources. `render.py` turns
the text into a footnoted 6 × 9 in. PDF using `history.typ`. It writes
`claims.json` with one record per noted sentence, ready for the independent
verification pass.

```powershell
python book/illustrate.py book/2025/ch02/portraits.json <photo-folder> book/2025/ch02/figures
python book/render.py book/2025/ch02 --font-dir <fonts> --sources-dir <folder with mts4.json> --output dist/2025-history-ch02-draft.pdf
```

`illustrate.py` renders licensed reference photographs as engraving-style line
hatching. Credits and licences are listed in `portraits.json` and printed in the
book.

Primary documents are downloaded and hashed during research. Their SHA-256 is
recorded in each source's note. The files themselves are kept in ignored
`tmp/pdfs/sources/`, not in Git, and can be fetched again from the recorded URLs.
Annex tables that exist only as images were transcribed by OCR and checked by eye.
