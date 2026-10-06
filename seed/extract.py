"""Deterministic archival extraction from one exact Wikipedia payload."""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import date as Date

import mwparserfromhell as mw


def fingerprint(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fragment(raw):
    code = mw.parse(raw)
    links = [{"surface": (n.text if n.text is not None else n.title).strip_code(),
              "target": str(n.title), "red_link": None, "raw": str(n)}
             for n in code.filter_wikilinks(recursive=True)]
    citations = []
    templated_links = set()
    template_cursor = 0
    for template in code.filter_templates(recursive=True):
        name = str(template.name).strip().lower()
        if (name == "citation" or name.startswith("cite ")) and template.has("url"):
            position = raw.find(str(template), template_cursor)
            template_cursor = position + len(str(template))
            def field(key):
                return template.get(key).value.strip_code().strip() if template.has(key) else None
            publisher = field("publisher") or field("work")
            citations.append((position, {"url": str(template.get("url").value).strip(),
                              "display": publisher or field("title") or "", "publisher": publisher,
                              "via": field("via"), "language": field("language"), "raw": str(template)}))
            templated_links.update(id(n) for n in template.get("url").value.filter_external_links(recursive=True))
    external_cursor = 0
    for n in code.filter_external_links(recursive=True):
        position = raw.find(str(n), external_cursor)
        external_cursor = position + len(str(n))
        if id(n) in templated_links:
            continue
        display = n.title.strip_code() if n.title else ""
        label = display.strip()
        def unwrap(value):
            if not value.startswith("("):
                return value
            depth = 0
            for index, char in enumerate(value):
                depth += (char == "(") - (char == ")")
                if depth == 0:
                    return value[1:-1].strip() if index == len(value) - 1 else value
            return value
        label = unwrap(label)
        language = None
        match = re.fullmatch(r"(.+?)\s+\(in\s+(.+?)\)", label)
        if match:
            label, language = match.groups()
            label = unwrap(label)
        publisher, via = label or None, None
        match = re.fullmatch(r"(.+?)\s+via\s+(.+)", label)
        if match:
            publisher, via = match.groups()
        citations.append((position, {"url": str(n.url), "display": display,
                          "publisher": publisher, "via": via,
                          "language": language, "raw": str(n)}))
    citations = [record for _, record in sorted(citations, key=lambda item: item[0])]
    unknown = []

    def render(nodes):
        parts = []
        for n in nodes:
            if isinstance(n, (mw.nodes.ExternalLink, mw.nodes.Comment)):
                continue
            if isinstance(n, mw.nodes.Text):
                parts.append(str(n))
                if "[[" in str(n) or "]]" in str(n) or "[http" in str(n):
                    unknown.append(("MALFORMED_MARKUP", str(n)))
            elif isinstance(n, mw.nodes.Wikilink):
                parts.append((n.text if n.text is not None else n.title).strip_code())
            elif isinstance(n, mw.nodes.Template):
                if str(n.name).strip().lower() in ("nowrap", "small", "lang") and n.params:
                    value = n.params[-1].value
                    parts.append(render(value.nodes))
                else:
                    unknown.append(("INLINE_TEMPLATE", str(n)))
                    # Retain unknown markup verbatim rather than erase its content.
                    parts.append(str(n))
            elif isinstance(n, mw.nodes.Tag):
                if str(n.tag).lower() == "ref":
                    if n.contents and not n.contents.filter_external_links(recursive=True):
                        unknown.append(("UNSUPPORTED_CITATION", str(n)))
                    continue
                parts.append(n.contents.strip_code() if n.contents else "")
            else:
                parts.append(str(n.strip_code()) if hasattr(n, "strip_code") else mw.parse(str(n)).strip_code())
        return "".join(parts)

    text = re.sub(r"\s+", " ", render(code.nodes)).strip()
    # Empty citation wrappers are markup artifacts; raw remains unmodified.
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text).strip()
    return text, links, citations, unknown


def body(raw, date):
    code = mw.parse(raw)
    templates = [t for t in code.filter_templates()
                 if re.fullmatch(r"\s*current\s+events\s*", str(t.name), re.I)
                 and t.has("content")]
    selected = templates
    if len(templates) > 1:
        target = Date.fromisoformat(date)
        selected = [t for t in templates if t.has("day") and str(t.get("day").value).strip() == str(target.day)
                    and t.has("year") and str(t.get("year").value).strip() == str(target.year)
                    and t.has("month") and str(t.get("month").value).strip().lstrip("0") == str(target.month)]
    if len(selected) == 1:
        value = str(selected[0].get("content").value)
        template_raw = str(selected[0])
        offset = raw.find(template_raw) + template_raw.find(value)
        return value, raw[:offset].count("\n"), None
    if templates:
        return raw, 0, "Multiple event templates cannot be assigned to the requested day"
    return raw, 0, None


def extract(raw, *, date, source, overrides=None):
    if fingerprint(raw) != source["source_sha256"]:
        raise ValueError("Extraction payload does not match pinned source hash")
    doc = {"schema_version": "extraction-1.0", "date": date,
           "source_page": copy.deepcopy(source), "categories": [], "warnings": []}

    def warn(code, message, *, category=None, entry=None, raw="", line=None):
        doc["warnings"].append({"code": code, "date": date, "source_page": source["page"],
                                "revision_id": source["revision_id"], "source_sha256": source["source_sha256"],
                                "category": category, "source_path": entry["source_path"] if entry else None,
                                "line": entry["line"] if entry else line, "raw": entry["raw"] if entry else raw,
                                "interpretation": entry["role"] if entry else None,
                                "message": message, "resolution": None})

    if source["source_mode"] == "rendered_html":
        from seed.rendered import parse_day
        groups = parse_day(raw, date)
        warn("RENDERED_SOURCE", "Rendered HTML preserves this acquisition; it is not raw-wikitext extraction")
        for group in groups:
            category = {"name": None, "entries": group}
            doc["categories"].append(category)
            for entry in group:
                if entry.pop("_malformed", False):
                    entry["role"] = "unknown"
                    warn("MALFORMED_HTML", "Unclosed list element retained", entry=entry)
        if not groups:
            warn("RENDERED_NO_ITEMS", "No day-specific list recognized; exact HTML retained in warning", raw=raw)
        return finish(doc, overrides, warn)
    if source["source_mode"] != "wikitext":
        raise ValueError("Unsupported source mode")
    content, offset, problem = body(raw, date)
    if problem:
        warn("AMBIGUOUS_DAY", problem, raw=raw)
        return doc
    current = None
    tokens = []
    for lineno, line in enumerate(content.splitlines(), offset + 1):
        stripped = line.strip()
        if not stripped or re.fullmatch(r"<!--.*?-->", stripped):
            continue
        cat = re.fullmatch(r"(?:;\s*(.+)|'''(.+?)'''|==+\s*(.+?)\s*==+)", stripped)
        if cat:
            name = next(g for g in cat.groups() if g is not None)
            current = {"name": fragment(name)[0].rstrip(":"), "entries": [], "line": lineno, "raw": line}
            tokens.append(("category", current))
            continue
        bullet = re.match(r"^\s*([*:]+)\s*(.*)$", line)
        if bullet:
            text, links, cites, unknown = fragment(bullet.group(2))
            entry = {"role": "unknown", "depth": len(bullet.group(1)), "list_marker": bullet.group(1), "source_path": [],
                     "parent_path": None, "line": lineno, "raw": line,
                     "text": text, "links": links, "citations": cites}
            tokens.append(("bullet", (entry, unknown)))
        elif line[:1].isspace() and tokens and tokens[-1][0] == "bullet":
            entry, unknown = tokens[-1][1]
            entry["raw"] += "\n" + line
            entry["text"], entry["links"], entry["citations"], new = fragment(re.sub(r"^\s*[*:]+\s*", "", entry["raw"]))
            unknown[:] = new
        else:
            warn("UNSUPPORTED_CONTENT", "Unrecognized structural content retained in warning", category=current["name"] if current else None,
                 raw=line, line=lineno)
    current = None
    stack = []
    counters = {}
    for index, (kind, value) in enumerate(tokens):
        if kind == "category":
            current = value
            doc["categories"].append(current)
            stack, counters = [], {}
            continue
        entry, unknown = value
        next_entry = tokens[index + 1][1][0] if index + 1 < len(tokens) and tokens[index + 1][0] == "bullet" else None
        children = next_entry is not None and next_entry["depth"] > entry["depth"]
        # The historical '*Category:' format only establishes a category before
        # an explicit section. Elsewhere colon lines remain topic headers.
        bullet_category_mode = current is None or current.get("raw", "").lstrip().startswith(("*", ":"))
        if bullet_category_mode and entry["depth"] == 1 and entry["text"].endswith(":") and children:
            current = {"name": entry["text"][:-1], "entries": [], "line": entry["line"], "raw": entry["raw"]}
            doc["categories"].append(current)
            stack, counters = [], {}
            continue
        if current is None:
            current = {"name": None, "entries": []}
            doc["categories"].append(current)
        while stack and stack[-1]["depth"] >= entry["depth"]:
            stack.pop()
        parent = stack[-1] if stack else None
        prefix = tuple(parent["source_path"]) if parent else ()
        counters[prefix] = counters.get(prefix, 0) + 1
        entry["source_path"] = list(prefix) + [counters[prefix]]
        entry["parent_path"] = list(prefix) if parent else None
        category_depth = len(re.match(r"^\s*([*:]*)", current.get("raw", "")).group(1))
        if entry["depth"] > (parent["depth"] + 1 if parent else category_depth + 1):
            warn("DEPTH_JUMP", "Missing intermediate list depth; actual depth retained", category=current["name"], entry=entry)
        pure_links = bool(entry["links"]) and not entry["citations"] and not re.sub(r"\[\[.*?\]\]|[\s,:;'\-–]", "", re.sub(r"^\s*[*:]+", "", entry["raw"]))
        if children and not entry["citations"]:
            entry["role"] = "topic"
        elif entry["text"].endswith(":") and not entry["citations"]:
            entry["role"] = "topic"
        elif pure_links:
            warn("AMBIGUOUS_ROLE", "Childless link-only bullet may be a topic or an event; requires an override", category=current["name"], entry=entry)
        else:
            entry["role"] = "event"
        current["entries"].append(entry)
        stack.append(entry)
        for code, markup in unknown:
            warn(code, "Unknown or malformed markup retained verbatim", category=current["name"], entry=entry)
    return finish(doc, overrides, warn)


def finish(doc, overrides, warn):
    for override in overrides or []:
        if override["date"] != doc["date"] or override["source_sha256"] != doc["source_page"]["source_sha256"]:
            raise ValueError("Override source identity drift")
        found = [e for c in doc["categories"] if c["name"] == override["category"]
                 for e in c["entries"] if e["source_path"] == override["source_path"]
                 and fingerprint(e["raw"]) == override["raw_sha256"]]
        if len(found) != 1 or fingerprint(found[0]["raw"]) != override["raw_sha256"]:
            raise ValueError("Override locator drift")
        if override["role"] not in ("topic", "event", "unknown"):
            raise ValueError("Invalid override role")
        found[0]["role"] = override["role"]
        for warning in doc["warnings"]:
            if warning["category"] == override["category"] and warning["source_path"] == override["source_path"] and warning["line"] == found[0]["line"]:
                warning["resolution"] = "guarded_override"
                warning["interpretation"] = override["role"]
    for category in doc["categories"]:
        entries = category["entries"]
        if not entries and category["name"] is not None:
            warn("ORPHAN_CATEGORY", "Category has no child; preserved", category=category["name"], raw=category.get("raw", ""), line=category.get("line"))
        paths = {tuple(e["source_path"]): e for e in entries}
        for entry in entries:
            if entry["parent_path"] is not None and tuple(entry["parent_path"]) not in paths:
                raise ValueError("Invalid parent path")
            if entry["role"] == "topic" and not any(e["parent_path"] == entry["source_path"] for e in entries):
                warn("ORPHAN_TOPIC", "Topic has no child; preserved", category=category["name"], entry=entry)
            for warning in doc["warnings"]:
                if warning["category"] == category["name"] and warning["source_path"] == entry["source_path"] and warning["line"] == entry["line"]:
                    warning["interpretation"] = entry["role"]
    return doc


def legacy_view(doc):
    """Explicit compatibility projection; the archive retains all structure."""
    result = {}
    for category in doc["categories"]:
        result.setdefault(category["name"] or "Uncategorized", [])
        for entry in category["entries"]:
            if entry["role"] == "event":
                result[category["name"] or "Uncategorized"].append(entry["text"])
    return result


def canonical(doc):
    return [{"category": c["name"], "raw": c.get("raw"), "entries": [
        dict({k: e[k] for k in ("role", "depth", "source_path", "parent_path", "raw", "links", "citations")}, list_marker=e.get("list_marker"))
        for e in c["entries"]]} for c in doc["categories"]]
