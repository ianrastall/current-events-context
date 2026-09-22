"""Parse a pinned Current-events portal revision (raw wikitext) into ordered events
with category, topic path, plain text and citations. Used only to build the
expanded synthesis files; not a replacement for seed.wikipedia."""
import json
import re
from pathlib import Path

import mwparserfromhell as mwp

HERE = Path(__file__).parent
WT = HERE / "wikitext"


def _plain(nodes_code):
    """Plain text for a wikicode fragment, dropping external-link citations."""
    out = []
    cites = []
    for node in nodes_code.nodes:
        if isinstance(node, mwp.nodes.ExternalLink):
            label = node.title.strip_code().strip() if node.title else ""
            label = label.strip().strip("()").strip()
            cites.append({"url": str(node.url).strip(), "outlet": label})
        elif isinstance(node, mwp.nodes.Wikilink):
            t = node.text if node.text is not None else node.title
            s = mwp.parse(str(t)).strip_code()
            if str(node.title).strip().lower().startswith(("file:", "image:", "category:")):
                continue
            out.append(s)
        elif isinstance(node, mwp.nodes.Template):
            out.append(mwp.parse(str(node)).strip_code())
        elif isinstance(node, mwp.nodes.Comment):
            continue
        elif isinstance(node, mwp.nodes.Tag):
            if str(node.tag).lower() in ("ref",):
                continue
            out.append(node.contents.strip_code() if node.contents else "")
        else:
            out.append(mwp.parse(str(node)).strip_code(keep_template_params=False))
    text = "".join(out)
    text = text.replace("''", "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*\(\s*\)\s*$", "", text)  # empty parens left by stripped cite wrappers
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text, cites


def parse(date):
    meta = json.loads((WT / f"{date}.json").read_text())
    raw = (WT / f"{date}.wiki").read_text(encoding="utf-8")
    body = raw
    m = re.search(r"<!-- All news items below this line -->(.*)<!-- All news items above this line -->", raw, re.S)
    if m:
        body = m.group(1)
    category = None
    stack = []  # topic path by depth
    events = []
    for lineno, line in enumerate(body.splitlines(), 1):
        s = line.rstrip()
        if not s.strip():
            continue
        cm = re.match(r"^\s*(?:'''(.+?)'''|;\s*(.+))\s*$", s)
        if cm:
            category = (cm.group(1) or cm.group(2)).strip()
            stack = []
            continue
        bm = re.match(r"^(\*+)\s*(.*)$", s)
        if not bm:
            continue
        depth = len(bm.group(1))
        text, cites = _plain(mwp.parse(bm.group(2)))
        stack = stack[: depth - 1]
        if cites:
            events.append({
                "category": category,
                "topics": [t for t in stack if t],
                "text": text,
                "cites": cites,
                "depth": depth,
                "line": lineno,
            })
        else:
            while len(stack) < depth - 1:
                stack.append("")
            stack.append(text)
    return meta, events


if __name__ == "__main__":
    import sys
    for d in sys.argv[1:]:
        meta, ev = parse(d)
        print(f"== {d} rev={meta['revid']} events={len(ev)}")
        for i, e in enumerate(ev):
            print(f"  [{i}] {e['category']} | {' > '.join(e['topics'])[:60]} || {e['text'][:100]} || {', '.join(c['outlet'] for c in e['cites'])}")
