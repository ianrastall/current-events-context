import sys; sys.path.insert(0, ".")
import build
for d in sys.argv[1:]:
    doc = build.build(d)
    print(f"=== {d}")
    for e in doc["events"]:
        c = e["casualty_report"]
        cas = "/".join("-" if c[k] is None else str(c[k]) for k in ("killed", "injured", "missing", "arrest_count"))
        if e["provenance"]["enriched_manually"]:
            print(f" {e['id'][-3:]} MD imp={e['importance']} [{e['category'][:22]}] {e['headline'][:95]} | kia/wia/mia/arr={cas} | portal={'Y' if e['sources']['wikipedia_portal']['included'] else 'n'}")
        else:
            print(f" {e['id'][-3:]} P  imp={e['importance']} [{e['category'][:22]}] {e['summary']} | {cas}")
