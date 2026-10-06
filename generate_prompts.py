"""Generate schema-2.2 conversion prompts from explicit synthesis inputs."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reference" / "expansion"))
import inputs
import corrections


def generate(dates, output_dir, *, include_reviewed=False):
    template = (ROOT / "llm_agent_prompt.txt").read_text(encoding="utf-8")
    schema = (ROOT / "reference/schema/daily-events.schema.json").read_text(encoding="utf-8")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for day in dates:
        selected = inputs.selection(day)
        overlay = corrections.path(day)
        records = json.loads(overlay.read_text(encoding="utf-8")) if overlay.exists() else []
        if selected["mode"] == "legacy_build":
            print(f"Skipped {day}: legacy synthesis is not a report-conversion input")
            continue
        target = ROOT / "expanded" / day[:4] / day[5:7] / (day + ".yaml")
        if selected["mode"] == "authored_snapshot":
            import yaml
            doc = yaml.safe_load(inputs.resolve(selected["snapshot"]).read_bytes())
            doc = corrections.apply(doc, selected, records)
            if doc["dataset"]["compiler"]["reviewed"] and not include_reviewed:
                continue
        report = inputs.resolve(selected["report"]).read_text(encoding="utf-8")
        text = template.replace("DATE_ISO = [insert date]", f"DATE_ISO = {day}")
        text = text.replace("[Insert Markdown Report Here]", report)
        text += f"\nTARGET OUTPUT FILE (repository-relative): {target.relative_to(ROOT).as_posix()}\nSELECTED INPUT: {selected['report']}\n"
        if records:
            text += "\nGUARDED SYNTHESIS CORRECTIONS:\nThese durable corrections supersede the corresponding original report claims. Preserve them during conversion; use the recorded evidence and keep the result draft pending review.\n"
            text += json.dumps(records, ensure_ascii=False, indent=2) + "\n"
        text += "\nCANONICAL SCHEMA 2.2:\n" + schema + "\n"
        path = output_dir / f"agent_prompt_{day}.txt"
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dates", nargs="*")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "copilot_prompts")
    parser.add_argument("--include-reviewed", action="store_true")
    args = parser.parse_args(argv)
    days = args.dates or sorted(json.loads(inputs.MANIFEST.read_text(encoding="utf-8")))
    for path in generate(days, args.output_dir, include_reviewed=args.include_reviewed):
        print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


if __name__ == "__main__":
    main()
