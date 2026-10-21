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
                doc = extract(raw, date=expected["date"], source=identity(raw, expected["mode"]), source_templates=expected.get("source_templates", False))
                got = [[c["name"], e["role"], e["depth"], e["source_path"], e["parent_path"], e["text"]]
                       for c in doc["categories"] for e in c["entries"]]
                self.assertEqual(expected["entries"], got)
                self.assertEqual(expected["warnings"], [w["code"] for w in doc["warnings"]])
                Draft202012Validator(schema).validate(doc)
                again = extract(raw, date=expected["date"], source=identity(raw, expected["mode"]), source_templates=expected.get("source_templates", False))
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

    def test_category_markup_is_structured_and_unsupported_content_warned(self):
        for raw in [";[[Politics|Political news]] [https://a.test (Agency)]\n*An event.\n",
                    "*[[Politics|Political news]] [https://a.test (Agency)]:\n**An event.\n"]:
            doc = extract(raw, date="2002-01-01", source=identity(raw))
            category = doc["categories"][0]
            self.assertEqual("Politics", category["links"][0]["target"])
            self.assertEqual("Political news", category["links"][0]["surface"])
            self.assertEqual("https://a.test", category["citations"][0]["url"])
            self.assertEqual(canonical(doc), canonical(yaml.safe_load(dump(doc))))
        raw = ";News {{unknown|Exact}}\n*An event.\n"
        doc = extract(raw, date="2002-01-01", source=identity(raw))
        self.assertEqual("INLINE_TEMPLATE", doc["warnings"][0]["code"])
        self.assertEqual("{{unknown|Exact}}", doc["warnings"][0]["raw"])

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

    def test_explicit_template_arguments_without_live_conversions(self):
        from seed.extract import fragment
        original_fragment = fragment
        fragment = lambda raw: original_fragment(raw, source_templates=True)
        cases = {
            '{{M|w|7.1}}': '7.1 Mw', '{{M|s|6.8}}': '6.8 Ms',
            '{{cvt|30|cm|in|adj=on}}': '30 cm', '{{conv|42|C|F}}': '42 C',
            '{{cvt|770,000|ha|km2|abbr=on}}': '770,000 ha',
            '{{Euro}}34 million': '€34 million', '{{USD}}2': 'US$2',
            '{{GBP}}4': '£4', '{{Renminbi|link=yes}}2.9 million': 'CN¥2.9 million',
            '{{mpl|2024 YR|4}}': '2024 YR4', '{{sub|w}}': 'w',
            '{{Ship|ARM|Cuauhtémoc}}': 'ARM Cuauhtémoc', '{{USS|Harry Truman||}}': 'USS Harry Truman',
            '{{MV|Eternity C||2}}': 'MV Eternity C', "{{'}}": "'",
            '{{FXConvert|BRA|{{#expr:1000000}}|cursign=[[Brazilian real|R$]]}}': 'R$1000000',
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(expected, fragment(raw)[0])
                self.assertEqual('SOURCE_TEMPLATE', fragment(raw)[3][0][0])
        raw = '{{ill|Exact target|fr|Cible|lt=Surface}}'
        self.assertEqual({'surface': 'Surface', 'target': 'Exact target', 'red_link': None, 'raw': raw}, fragment(raw)[1][0])
        self.assertIn('INLINE_TEMPLATE', [c for c, _ in fragment('{{FXConvert|BRA|{{#expr:1+2}}|cursign=R$}}')[3]])

    def test_citation_continuation_and_warning_guards_do_not_hide_other_problems(self):
        raw = ';News\n*[[Heading]]\n**An event [https://a.test (First)]\n[https://b.test (Second)]\nPasted prose\n'
        doc = extract(raw, date='2002-01-01', source=identity(raw), source_templates=True)
        event = doc['categories'][0]['entries'][1]
        self.assertEqual(['https://a.test', 'https://b.test'], [c['url'] for c in event['citations']])
        warning = next(w for w in doc['warnings'] if w['code'] == 'UNSUPPORTED_CONTENT')
        override = {'date': doc['date'], 'source_sha256': fingerprint(raw), 'action': 'preserve_unclassified',
                    'warning_code': warning['code'], 'line': warning['line'], 'raw_sha256': fingerprint(warning['raw']),
                    'reason': 'Retain unclassified pasted source, never infer an event.'}
        result = extract(raw, date=doc['date'], source=identity(raw), overrides=[override], source_templates=True)
        self.assertEqual('guarded_unclassified_retention', next(w for w in result['warnings'] if w['code'] == 'UNSUPPORTED_CONTENT')['resolution'])
        override['raw_sha256'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'locator drift'):
            extract(raw, date=doc['date'], source=identity(raw), overrides=[override], source_templates=True)

    def test_extra_portal_parameters_and_source_reliability_are_preserved(self):
        raw = '{{Current events|year=2002|month=1|day=1|content=\n;News\n*Reported claim.{{unreliable inline}}\nPasted video | Extra label |tail=Exact URL and bytes\n}}'
        doc = extract(raw, date='2002-01-01', source=identity(raw), source_templates=True)
        extra = [w['raw'] for w in doc['warnings'] if w['code'] == 'UNASSIGNED_TEMPLATE_PARAMETER']
        self.assertEqual([' Extra label ', 'tail=Exact URL and bytes\n'], extra)
        reliability = next(w for w in doc['warnings'] if w['code'] == 'SOURCE_RELIABILITY_TAG')
        self.assertEqual('annotation_preserved_for_factual_review', reliability['resolution'])

    def test_empty_source_marker_is_retained_without_a_factual_assertion(self):
        raw = ';News\n*\n*A cited event [https://a.test (Source)]\n'
        result = extract(raw, date='2002-01-01', source=identity(raw), source_templates=True)
        marker = result['categories'][0]['entries'][0]
        self.assertEqual(('unknown', '', '*'), (marker['role'], marker['text'], marker['raw']))
        warning = next(w for w in result['warnings'] if w['code'] == 'SOURCE_EMPTY_MARKER')
        self.assertEqual('deterministic_source_rule', warning['resolution'])
        self.assertEqual('event', extract(raw, date='2002-01-01', source=identity(raw))['categories'][0]['entries'][0]['role'])

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
