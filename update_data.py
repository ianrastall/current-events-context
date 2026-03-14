import os
import sys
import calendar
import logging
import yaml
from datetime import datetime, timezone

from wiki_parser import fetch_wikitext, parse_events

# ---------------------------------------------------------------------------
# Logging — file only, no console output
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("update.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

USER_AGENT = "LLM-Context-Pipeline/1.0 (https://github.com/ianrastall/current-events-context)"

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def process_date(target_date) -> bool:
    month_name = calendar.month_name[target_date.month]
    page_title = (
        f"Portal:Current events/"
        f"{target_date.year} {month_name} {target_date.day}"
    )

    log.info("Processing: %s", page_title)

    wikitext = fetch_wikitext(page_title, USER_AGENT)
    if not wikitext:
        log.warning("No data found for %s", page_title)
        return False

    events_data = parse_events(wikitext, page_title)
    if not events_data:
        log.warning("No events parsed for %s", page_title)
        return False

    dataset = {
        "Date":                 target_date.strftime("%Y-%m-%d"),
        "Source_URI":           page_title,
        "Intelligence_Payload": events_data,
    }

    dir_path = os.path.join(str(target_date.year), f"{target_date.month:02d}")
    os.makedirs(dir_path, exist_ok=True)
    filename = os.path.join(dir_path, f"{target_date}.yaml")

    with open(filename, "w", encoding="utf-8") as f:
        yaml.dump(
            dataset,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    log.info("Saved %s", filename)
    return True


def main() -> None:
    if len(sys.argv) > 1:
        try:
            target_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        except ValueError:
            log.error("Invalid date argument %r — expected YYYY-MM-DD", sys.argv[1])
            sys.exit(1)
    else:
        target_date = datetime.now(timezone.utc).date()

    success = process_date(target_date)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
