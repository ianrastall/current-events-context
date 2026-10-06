"""Immutable Wikipedia payload storage; parsing never uses the network."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "reference" / "sources" / "wikipedia"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def store(payload: bytes, *, title: str, revision_id: int | None,
          timestamp: str | None, mode="wikitext", cache=CACHE) -> dict:
    if mode not in ("wikitext", "rendered_html"):
        raise ValueError("Unknown Wikipedia source mode")
    digest = sha256(payload)
    # Rendered output can change through transclusions even for one page oldid.
    key = str(revision_id) if mode == "wikitext" and revision_id else digest
    if mode == "rendered_html":
        key = f"{revision_id or 'unknown'}-{digest}"
    base = Path(cache) / mode / key
    base.parent.mkdir(parents=True, exist_ok=True)
    suffix = ".wiki" if mode == "wikitext" else ".html"
    data_path, meta_path = base.with_suffix(suffix), base.with_suffix(".json")
    meta = {"page": title, "revision_id": revision_id,
            "revision_timestamp": timestamp, "source_mode": mode,
            "source_sha256": digest, "payload": data_path.name}
    if meta_path.exists() or data_path.exists():
        if not meta_path.exists() or not data_path.exists():
            raise ValueError(f"Incomplete cache entry: {base}; reacquire through acquisition")
        old, old_payload = load(base, mode=mode)
        same_identity = all(old[k] == meta[k] for k in meta if k != "revision_timestamp")
        if old_payload != payload or not same_identity:
            raise ValueError(f"Immutable cache conflict: {base}")
        if old["revision_timestamp"] is None and timestamp is not None:
            # Add exact API metadata without rewriting the original input pair.
            with base.with_suffix(".provenance.json").open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
            return meta
        if timestamp is not None and old["revision_timestamp"] != timestamp:
            raise ValueError(f"Conflicting revision timestamp: {base}")
        return old
    # Exclusive writes prevent accidental replacement of cached inputs.
    with data_path.open("xb") as handle:
        handle.write(payload)
    with meta_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    return meta


def load(base, *, mode="wikitext") -> tuple[dict, bytes]:
    base = Path(base)
    meta = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
    extra = base.with_suffix(".provenance.json")
    if extra.exists():
        supplemented = json.loads(extra.read_text(encoding="utf-8"))
        if meta["revision_timestamp"] is not None or not supplemented["revision_timestamp"] or any(meta[k] != supplemented[k] for k in meta if k != "revision_timestamp"):
            raise ValueError(f"Invalid immutable provenance supplement: {base}")
        meta = supplemented
    if meta["source_mode"] != mode:
        raise ValueError("Source mode mismatch")
    path = base.parent / meta["payload"]
    if path.parent.resolve() != base.parent.resolve():
        raise ValueError("Cache payload escapes its entry")
    payload = path.read_bytes()
    if sha256(payload) != meta["source_sha256"]:
        raise ValueError(f"Cached payload hash mismatch: {base}")
    return meta, payload


def revision(revision_id, *, cache=CACHE):
    meta, payload = load(Path(cache) / "wikitext" / str(revision_id))
    if meta["revision_id"] != revision_id:
        raise ValueError("Cached revision identity mismatch")
    return meta, payload


def import_expansion_cache():
    """Import exact existing inputs without modifying their original bytes."""
    for path in sorted((ROOT / "reference/expansion/wikitext").glob("*.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        payload = path.with_suffix(".wiki").read_bytes()
        if sha256(payload) != meta["sha256"]:
            raise ValueError(f"Expansion source hash mismatch: {path}")
        store(payload, title=meta["title"], revision_id=meta["revid"],
              timestamp=meta.get("timestamp"))


def capture(day, meta):
    """Acquisition provenance pointer; raw cached inputs remain immutable."""
    path = CACHE / "captures" / f"{day}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def captured(day):
    meta = json.loads((CACHE / "captures" / f"{day}.json").read_text(encoding="utf-8"))
    loaded, payload = load(CACHE / meta["source_mode"] / Path(meta["payload"]).stem,
                           mode=meta["source_mode"])
    if loaded != meta:
        raise ValueError(f"Capture pointer identity mismatch: {day}")
    return loaded, payload


def capture_paths(day):
    """Files needed to publish one capture without losing its exact inputs."""
    pointer = CACHE / "captures" / f"{day}.json"
    if not pointer.exists():
        return []
    meta, _ = captured(day)
    payload = CACHE / meta["source_mode"] / meta["payload"]
    archive = ROOT / "provisional/captures" / day[:4] / day[5:7] / (day + ".yaml")
    paths = [pointer, payload, payload.with_suffix(".json"), archive, archive.with_suffix(".warnings.jsonl")]
    extra = payload.with_suffix(".provenance.json")
    if extra.exists():
        paths.append(extra)
    if not all(p.exists() for p in paths):
        raise ValueError(f"Incomplete acquisition artifacts for {day}")
    return paths
