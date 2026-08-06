"""
Diagnose the real rendered HTML structure of a legacy Wikipedia monthly
Current Events archive page, so MonthlyCurrentEventsParser can be fixed
against actual markup instead of guessed markup.

Usage:
  python diagnose_monthly_page.py "Portal:Current events/January 2002"

Output:
  - Saves the full rendered HTML to ./diagnostic_output.html for manual
    inspection if needed.
  - Prints a compact structural fingerprint: every distinct (tag, class)
    and (tag, id) pair found, plus a short snippet of text near any
    heading-like tag, so we can identify how individual days are marked
    off without you having to paste the whole page back.
"""

import re
import sys
from collections import Counter

import requests

USER_AGENT = "LLM-Context-Pipeline/1.0 (https://github.com/ianrastall/current-events-context)"


def fetch_rendered_html(page_title: str) -> str | None:
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "text",
        "format": "json",
        "formatversion": "2",
        "redirects": "true",
    }
    response = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        print(f"API error: {data['error']}")
        return None
    return data.get("parse", {}).get("text")


def fingerprint(html: str) -> None:
    tag_class_pairs = Counter(re.findall(r'<(\w+)\b[^>]*\bclass="([^"]+)"', html))
    tag_id_pairs = Counter(re.findall(r'<(\w+)\b[^>]*\bid="([^"]+)"', html))

    print("\n=== Distinct (tag, class) pairs, most common first ===")
    for (tag, cls), count in tag_class_pairs.most_common(40):
        print(f"  {count:4d}  <{tag} class=\"{cls}\">")

    print("\n=== Distinct (tag, id) pairs containing digits (likely day anchors) ===")
    for (tag, id_val), count in tag_id_pairs.most_common():
        if re.search(r"\d", id_val):
            print(f"  {count:4d}  <{tag} id=\"{id_val}\">")

    print("\n=== Headings (h2/h3/h4/dt) with surrounding text ===")
    for match in re.finditer(r"<(h[2-4]|dt)\b[^>]*>(.*?)</\1>", html, re.DOTALL):
        tag, inner = match.groups()
        text = re.sub(r"<[^>]+>", "", inner).strip()
        if text:
            print(f"  <{tag}> {text[:80]}")

    print("\n=== First 3 <li> elements (raw) ===")
    for match in list(re.finditer(r"<li\b[^>]*>.*?</li>", html, re.DOTALL))[:3]:
        print(f"  {match.group(0)[:200]}")


def main() -> None:
    page_title = sys.argv[1] if len(sys.argv) > 1 else "Portal:Current events/January 2002"
    print(f"Fetching rendered HTML for: {page_title}")
    html = fetch_rendered_html(page_title)
    if not html:
        print("No HTML returned — page may not exist under this exact title.")
        return

    with open("diagnostic_output.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved {len(html):,} chars to diagnostic_output.html")

    fingerprint(html)


if __name__ == "__main__":
    main()