"""Preserve nested list structure in exact legacy rendered HTML inputs."""
from html.parser import HTMLParser
import re


def parse_day(raw, date):
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.entries = []
            self.stack = []
            self.counters = {}
            self.div_depth = 0
            self.region = None
            self.has_regions = "current-events-main" in raw
            self.active = not self.has_regions
            self.anchor = None
            self.offsets = [0]
            for line in raw.splitlines(keepends=True):
                self.offsets.append(self.offsets[-1] + len(line))

        def raw_offset(self):
            line, column = self.getpos()
            return self.offsets[line - 1] + column

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "div":
                self.div_depth += 1
                if "current-events-main" in attrs.get("class", "").split():
                    self.region = self.div_depth
                    match = re.search(r"(\d{1,2})$", attrs.get("aria-label", ""))
                    self.active = bool(match and int(match.group(1)) == int(date[-2:]))
            if tag == "li" and self.active:
                parent = self.stack[-1] if self.stack else None
                prefix = tuple(parent["source_path"]) if parent else ()
                self.counters[prefix] = self.counters.get(prefix, 0) + 1
                entry = {"role": "unknown", "depth": len(self.stack) + 1,
                         "source_path": list(prefix) + [self.counters[prefix]],
                         "parent_path": list(prefix) if parent else None,
                         "line": self.getpos()[0], "raw": "", "text": "",
                         "links": [], "citations": [], "_start": self.raw_offset()}
                self.entries.append(entry)
                self.stack.append(entry)
            if tag == "a" and self.stack:
                self.anchor = {"href": attrs.get("href", ""), "surface": "", "raw": self.get_starttag_text()}

        def handle_data(self, data):
            if self.stack:
                self.stack[-1]["text"] += data
                if self.anchor:
                    self.anchor["surface"] += data

        def handle_endtag(self, tag):
            if tag == "a" and self.anchor and self.stack:
                a = self.anchor
                if a["href"].startswith(("/wiki/", "./")):
                    self.stack[-1]["links"].append({"surface": a["surface"], "target": a["href"],
                                                   "red_link": None, "raw": a["raw"]})
                elif a["href"].startswith(("https://", "http://")):
                    self.stack[-1]["citations"].append({"url": a["href"], "display": a["surface"],
                        "publisher": a["surface"] or None, "via": None, "language": None, "raw": a["raw"]})
                self.anchor = None
            if tag == "li" and self.stack:
                entry = self.stack.pop()
                entry["raw"] = raw[entry.pop("_start"):self.raw_offset() + len("</li>")]
                entry["text"] = re.sub(r"\s+", " ", entry["text"]).strip()
            if tag == "div":
                if self.region == self.div_depth:
                    self.active = False
                    self.region = None
                self.div_depth -= 1

    parser = Parser()
    parser.feed(raw)
    for entry in parser.entries:
        if "_start" in entry:
            entry["raw"] = raw[entry.pop("_start"):]
            entry["_malformed"] = True
        children = any(e["parent_path"] == entry["source_path"] for e in parser.entries)
        entry["role"] = "topic" if children and not entry["citations"] else "event"
    return [parser.entries] if parser.entries else []
