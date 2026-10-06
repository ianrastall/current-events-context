"""Bind external-source references to the bibliography URL actually cited."""
from urllib.parse import urlsplit


def reconcile(doc, accessed):
    fixes = []
    works = doc["works_cited"]
    for event in doc["events"]:
        for source in event["sources"]["external"]:
            matches = [w["id"] for w in works if w["url"] == source["url"]]
            if any(ref in matches for ref in source["citation_refs"]):
                continue
            if not matches:
                ident = max(w["id"] for w in works) + 1
                homepage = urlsplit(source["url"]).path in ("", "/")
                title = (f"{source['outlet']} homepage; no article URL supplied" if homepage
                         else f"Source cited for {event['id']}; article title not recorded")
                works.append({"id": ident, "title": title, "outlet": source["outlet"],
                              "url": source["url"], "accessed": accessed})
                matches = [ident]
                if homepage:
                    source["supports"] = []
                    source["quoted_material"] = []
                    source["reliability_tier"] = "low"
                    event["notes"] = (event["notes"] + " " if event["notes"] else "") + f"{source['id']} supplies a homepage rather than an identifiable article; it is not treated as claim support."
            fixes.append({"event_id": event["id"], "source_id": source["id"],
                          "old_refs": source["citation_refs"], "new_refs": matches,
                          "url": source["url"]})
            source["citation_refs"] = matches
    return fixes
