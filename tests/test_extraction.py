import copy
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator
from seed.extract import canonical, extract, fingerprint
from seed.replay import dump
from seed import source

ROOT = Path(__file__).resolve().parents[1]


def identity(raw, mode="wikitext"):
    return {"page": "Fixture", "revision_id": 123, "revision_timestamp": None,
            "source_mode": mode, "source_sha256": fingerprint(raw)}


class GoldenTests(unittest.TestCase):
    def setUp(self):
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_golden_fixtures(self):
        schema = json.loads((ROOT / "reference/schema/extraction.schema.json").read_text(encoding="utf-8"))
        for expected_path in sorted((ROOT / "tests/fixtures").glob("*.json")):
            with self.subTest(fixture=expected_path.stem):
                expected = json.loads(expected_path.read_text(encoding="utf-8"))
                raw = expected_path.with_suffix(".html" if expected["mode"] == "rendered_html" else ".wiki").read_text(encoding="utf-8")
                doc = extract(raw, date=expected["date"], source=identity(raw, expected["mode"]))
                got = [[c["name"], e["role"], e["depth"], e["source_path"], e["parent_path"], e["text"]]
                       for c in doc["categories"] for e in c["entries"]]
                self.assertEqual(expected["entries"], got)
                self.assertEqual(expected["warnings"], [w["code"] for w in doc["warnings"]])
                Draft202012Validator(schema).validate(doc)
                again = extract(raw, date=expected["date"], source=identity(raw, expected["mode"]))
                self.assertEqual(dump(doc), dump(again))
                self.assertEqual(canonical(doc), canonical(yaml.safe_load(dump(doc))))
                self.assertTrue(dump(doc).endswith("\n"))
                self.assertNotIn("\r", dump(doc))

    def test_links_citations_and_source_errors(self):
        raw = (ROOT / "tests/fixtures/modern.wiki").read_text(encoding="utf-8")
        event = extract(raw, date="2002-01-01", source=identity(raw))["categories"][0]["entries"][1]
        self.assertEqual({"surface": "The country", "target": "Country", "red_link": None,
                          "raw": "[[Country|The country]]"}, event["links"][0])
        self.assertEqual([("AFP", "Wire", None), ("BBC", None, "French")],
                         [(c["publisher"], c["via"], c["language"]) for c in event["citations"]])
        self.assertEqual(["https://a.test", "https://b.test"], [c["url"] for c in event["citations"]])
        raw = ";News\n*A misspelt consituency is reported.\n"
        doc = extract(raw, date="2002-01-01", source=identity(raw))
        self.assertIn("consituency", doc["categories"][0]["entries"][0]["text"])

    def test_guarded_override_and_drift(self):
        raw = ";Politics\n*[[Topic]]\n"
        guard = {"date": "2002-01-01", "source_sha256": fingerprint(raw), "category": "Politics",
                 "source_path": [1], "raw_sha256": fingerprint("*[[Topic]]"), "role": "event"}
        doc = extract(raw, date=guard["date"], source=identity(raw), overrides=[guard])
        self.assertEqual("event", doc["categories"][0]["entries"][0]["role"])
        self.assertEqual("guarded_override", doc["warnings"][0]["resolution"])
        for field, value in [("raw_sha256", "bad"), ("source_sha256", "bad"), ("source_path", [2])]:
            bad = copy.deepcopy(guard); bad[field] = value
            with self.assertRaises(ValueError):
                extract(raw, date=guard["date"], source=identity(raw), overrides=[bad])

    def test_citation_templates_preserve_order_and_explicit_annotations(self):
        raw = (ROOT / "tests/fixtures/cite_templates.wiki").read_text(encoding="utf-8")
        doc = extract(raw, date="2002-01-01", source=identity(raw))
        cites = doc["categories"][0]["entries"][0]["citations"]
        self.assertEqual(["https://first.test", "https://second.test", "https://third.test"], [c["url"] for c in cites])
        self.assertEqual(("Agency", "Wire", "French"), (cites[1]["publisher"], cites[1]["via"], cites[1]["language"]))
        from seed.extract import fragment
        combined = fragment("[https://a.test (AFP via Wire) (in French)]")[2][0]
        self.assertEqual(("AFP", "Wire", "French"), (combined["publisher"], combined["via"], combined["language"]))

    def test_immutable_hash_verified_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            source.store(b"exact\r\nbytes", title="Fixture", revision_id=123, timestamp=None, cache=directory)
            _, payload = source.revision(123, cache=directory)
            self.assertEqual(b"exact\r\nbytes", payload)
            original = (Path(directory) / "wikitext/123.json").read_bytes()
            source.store(payload, title="Fixture", revision_id=123, timestamp="2002-01-01T00:00:00Z", cache=directory)
            meta, _ = source.revision(123, cache=directory)
            self.assertEqual("2002-01-01T00:00:00Z", meta["revision_timestamp"])
            self.assertEqual(original, (Path(directory) / "wikitext/123.json").read_bytes())
            with self.assertRaises(ValueError):
                source.store(b"changed", title="Fixture", revision_id=123, timestamp=None, cache=directory)
            path = Path(directory) / "wikitext/123.wiki"
            path.write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                source.revision(123, cache=directory)

    def test_all_checked_in_wikitext_offline(self):
        for path in sorted((ROOT / "reference/expansion/wikitext").glob("*.wiki")):
            with self.subTest(date=path.stem):
                before = path.read_bytes()
                meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
                raw = before.decode("utf-8")
                src = {"page": meta["title"], "revision_id": meta["revid"],
                       "revision_timestamp": meta["timestamp"], "source_mode": "wikitext", "source_sha256": meta["sha256"]}
                doc = extract(raw, date=path.stem, source=src)
                self.assertEqual(before, path.read_bytes())
                self.assertEqual(dump(doc), dump(extract(raw, date=path.stem, source=src)))
                self.assertTrue(any(c["name"] is not None for c in doc["categories"]))


if __name__ == "__main__":
    unittest.main()
