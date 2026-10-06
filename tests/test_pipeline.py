import contextlib
import copy
import importlib.util
import io
import json
import socket
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch, Mock

import yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference/expansion"))
import build
import inputs
import generate_prompts
import corrections
from seed import replay, source, wikipedia
from seed.cli import build_parser, fetch_and_save_day

spec = importlib.util.spec_from_file_location("validator", ROOT / "reference/schema/validate.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class PipelineTests(unittest.TestCase):
    def test_current_capture_requires_explicit_policy_and_preserves_legacy(self):
        doc = {"Date": "2026-08-07", "Source_URI": "Exact", "Intelligence_Payload": {"Uncategorized": ["Original"]}}
        original = copy.deepcopy(doc)
        meta = {"page": "Exact", "revision_id": 123}
        with tempfile.TemporaryDirectory() as directory:
            args = build_parser().parse_args(["cache", "2026-08-07", "2026-08-07"])
            with patch.object(source, "import_expansion_cache"), patch.object(replay, "seed_path", return_value=ROOT / "README.md"), patch.object(replay, "seed_doc", return_value=doc):
                with self.assertRaisesRegex(ValueError, "choose an acquisition policy"):
                    replay.run_cache(args)
                args.capture_unpinned = True
                with patch.object(source, "CACHE", Path(directory)), patch.object(replay, "cached_input", side_effect=FileNotFoundError), patch.object(wikipedia, "fetch_wikitext", return_value=Mock(source_meta=meta)) as fetch, patch.object(source, "capture") as capture, patch("time.sleep"):
                    self.assertEqual(0, replay.run_cache(args))
                    self.assertEqual("Exact", fetch.call_args.args[0])
                    capture.assert_called_once_with("2026-08-07", meta)
                    report = json.loads((Path(directory) / "current-captures-report.json").read_text())
                    self.assertEqual("current_revision_as_new_input", report["new_source_captures"][0]["policy"])
                    self.assertIsNone(report["new_source_captures"][0]["original_capture_revision"])
                self.assertEqual(original, doc)
        with patch.object(source, "captured", return_value=(meta, b"raw")):
            self.assertEqual((meta, b"raw"), replay.cached_input("2026-08-07", doc))
            with self.assertRaisesRegex(ValueError, "matching pinned source"):
                replay.cached_input("2026-08-07", dict(doc, Source_URI="Different"))

    def test_selected_replacement_reports_and_exact_snapshot_replay(self):
        for n in range(1, 16):
            day = f"2026-01-{n:02}"
            selected = inputs.selection(day)
            if 10 <= n <= 12:
                self.assertEqual(day + "b.md", build.md_path_for(day).name)
            doc = yaml.safe_load(inputs.resolve(selected["snapshot"]).read_bytes())
            path = corrections.path(day)
            records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            self.assertEqual(build.build(day), corrections.apply(doc, selected, records))

    def test_input_drift_rejected(self):
        with patch.object(inputs, "digest", return_value="wrong"):
            with self.assertRaisesRegex(ValueError, "Research input drift"):
                build.build("2026-01-10")

    def test_authored_correction_is_guarded_by_identity_and_resets_review(self):
        day = "2026-01-02"
        selected = inputs.selection(day)
        doc = build.build(day)
        event = doc["events"][0]
        record = corrections.locator(day, event["id"])
        record.update(reason="Test interpretation", patch={"notes": "Test correction"})
        updated = corrections.apply(doc, selected, [record])
        self.assertEqual("Test correction", updated["events"][0]["notes"])
        self.assertEqual("draft", updated["dataset"]["compiler"]["status"])
        self.assertEqual([], validator.schema_errors(updated) + validator.cross_ref_errors(updated))
        self.assertNotEqual(doc, updated)
        record["event_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "event drift"):
            corrections.apply(doc, selected, [record])

    def test_capture_pointer_and_publication_paths_are_complete(self):
        check = replay.extraction_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "reference/sources/wikipedia"
            meta = source.store(b"* An event.", title="Exact", revision_id=123, timestamp="pinned", cache=cache)
            with patch.object(source, "ROOT", root), patch.object(source, "CACHE", cache), patch.object(replay, "REPO_ROOT", root), patch.object(replay, "extraction_validator", return_value=check):
                source.capture("2026-01-01", meta)
                identity = {k: meta[k] for k in ("page", "revision_id", "revision_timestamp", "source_mode", "source_sha256")}
                from seed.extract import extract
                replay.save_capture("2026-01-01", extract("* An event.", date="2026-01-01", source=identity))
                self.assertEqual(5, len(source.capture_paths("2026-01-01")))
                pointer = cache / "captures/2026-01-01.json"
                modified = dict(meta, source_sha256="wrong")
                pointer.write_text(json.dumps(modified), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "identity mismatch"):
                    source.captured("2026-01-01")

    def test_generated_prompt_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            written = generate_prompts.generate(["2026-01-02", "2026-01-10"], directory)
            self.assertEqual(1, len(written))
            text = written[0].read_text(encoding="utf-8")
            self.assertIn("2026-01-10b.md", text)
            self.assertIn('"const": "2.2"', text)
            self.assertIn("expanded/2026/01/2026-01-10.yaml", text)
            self.assertNotIn(str(ROOT), text)
            self.assertIn("GUARDED SYNTHESIS CORRECTIONS", text)
            self.assertIn("Executive Order", text)
            self.assertNotIn('schema_version: "2.1"', text)
            self.assertNotIn("D:\\GitHub", text)

    def test_validator_requires_schema_dependency_and_checks_all_files(self):
        with patch.dict(sys.modules, {"jsonschema": None}):
            self.assertTrue(validator.schema_errors({}))
        with patch.object(validator, "validate", side_effect=[False, True]) as check:
            with self.assertRaises(SystemExit) as exc:
                validator.main(["bad.yaml", "good.yaml"])
            self.assertEqual(1, exc.exception.code)
            self.assertEqual(2, check.call_count)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.yaml"; path.write_text("* invalid alias")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(validator.validate(path))

    def test_related_events_resolve_and_missing_links_fail(self):
        doc = build.build("2026-01-15")
        self.assertEqual([], validator.related_errors(doc, ROOT / "expanded"))
        doc["events"][0]["related_events"].append("evt-2099-01-01-001")
        self.assertTrue(validator.related_errors(doc, ROOT / "expanded"))

    def test_citation_pointer_identifies_the_cited_article(self):
        doc = build.build("2026-01-12")
        source_record = doc["events"][9]["sources"]["external"][0]
        works = {w["id"]: w["url"] for w in doc["works_cited"]}
        self.assertEqual(source_record["url"], works[source_record["citation_refs"][0]])
        source_record["citation_refs"] = [36]  # The unrelated ISRO article.
        self.assertTrue(any("cited URL" in error for error in validator.cross_ref_errors(doc)))

    def test_offline_replay_preserves_gdelt_and_cache(self):
        base = yaml.safe_load((ROOT / "2026/01/2026-01-06.yaml").read_text(encoding="utf-8"))
        base["gdelt"] = {"queried_at": "pinned", "articles": [{"title": "Exact", "url": "https://a.test"}], "article_count": 1}
        rev = base["source_page"]["wikipedia_revision_id"]
        path = source.CACHE / "wikitext" / f"{rev}.wiki"
        before = path.read_bytes()
        with patch.object(replay, "seed_doc", return_value=copy.deepcopy(base)), patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
            first = replay.candidate("2026-01-06")
            second = replay.candidate("2026-01-06")
        self.assertEqual(base["gdelt"], first["gdelt"])
        self.assertEqual(replay.dump(first), replay.dump(second))
        self.assertEqual(before, path.read_bytes())

    def test_full_reparse_has_no_network_and_rejects_missing_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            args = build_parser().parse_args(["reparse", "2026-01-06", "2026-01-12", "--verify", "--output-root", directory])
            with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, replay.run_reparse(args))
            report = json.loads((Path(directory) / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(7, report["generated"])
            self.assertTrue(report["complete"])
            self.assertTrue(report["verified_idempotence_and_round_trip"])
            self.assertTrue(all(r["source_bullets"] == r["represented_bullets"] for r in report["reconciliation"]))
            with patch.object(replay, "candidate", side_effect=FileNotFoundError):
                with self.assertRaisesRegex(ValueError, "Incomplete offline inputs"):
                    replay.run_reparse(args)
        args = build_parser().parse_args(["reparse", "2026-01-06", "2026-01-06", "--output-root", str(ROOT / "2026/01")])
        with self.assertRaises(ValueError):
            replay.run_reparse(args)

    def test_explicit_oldid_batch_and_no_current_revision_fallback(self):
        response = Mock(); response.status_code = 200
        response.json.return_value = {"query": {"pages": [{"title": "Exact", "revisions": [{"revid": 123, "timestamp": "pinned", "slots": {"main": {"content": "raw"}}}]}]}}
        with patch.object(wikipedia._session, "get", return_value=response) as get, patch.object(source, "store", return_value={"revision_id": 123}):
            self.assertEqual({123}, set(wikipedia.acquire_revision_batch([123], "test")))
            params = get.call_args.kwargs["params"]
            self.assertEqual("123", params["revids"])
            self.assertNotIn("titles", params)
        with self.assertRaises(ValueError):
            wikipedia.acquire_revision_batch(list(range(51)), "test")

    def test_march_repair_is_regenerable_and_valid(self):
        for day in ["2026-03-10", "2026-03-11", "2026-03-18"]:
            doc = build.build(day)
            self.assertEqual([], validator.schema_errors(doc) + validator.cross_ref_errors(doc))
            self.assertEqual("draft", doc["dataset"]["compiler"]["status"])
            self.assertEqual([], validator.related_errors(doc, ROOT / "expanded"))
        doc = build.build("2026-03-18")
        event = next(e for e in doc["events"] if e["id"] == "evt-2026-03-18-007")
        works = {w["id"]: w for w in doc["works_cited"]}
        for source_record in event["sources"]["external"]:
            work = works[source_record["citation_refs"][0]]
            self.assertEqual("2026-10-05", work["accessed"])
            self.assertEqual(source_record["url"], work["url"])
            self.assertNotIn("title not recorded", work["title"])


if __name__ == "__main__":
    unittest.main()
