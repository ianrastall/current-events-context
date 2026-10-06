# Exact Wikipedia source cache

`wikitext/<revision-id>.wiki` contains the exact UTF-8 API payload for a
recorded oldid. Its adjacent JSON records page title, oldid, revision timestamp,
source mode, payload filename and SHA-256. These pairs are immutable inputs.
Raw bytes bypass Git newline conversion. Acquisition verifies existing entries
and refuses conflicts. Missing metadata can be supplemented by a separate
immutable `.provenance.json` record without rewriting an input pair.

`rendered_html/` is reserved for exact rendered monthly-page captures, keyed
by revision identity and payload hash. Rendered transclusions are a distinct
source mode. `captures/<date>.json` points to a new capture's exact input;
these acquisition pointers are generated provenance rather than raw inputs.

`python -m seed cache START END` obtains revisions already recorded in seed
files. `--skip-unpinned` explicitly records legacy or missing dates without
choosing current revisions for them. `acquisition-report.json` describes the
initial bulk acquisition. Offline reparse never queries current pages or GDELT.
Never hand-edit cache data or metadata. Reacquire erroneous inputs through the
acquisition path, keeping any prior identity intact.

Wikipedia source text is attributed to the recorded page and revision on
English Wikipedia and remains subject to its CC BY-SA licensing terms.
Original contributions belong to their Wikipedia contributors. Source URLs
can be reconstructed as `https://en.wikipedia.org/w/index.php?oldid=<revision-id>`.
