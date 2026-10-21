"""Conservative text projections of explicit template arguments, without expansion.

No conversion, exchange rate, page-existence lookup or factual correction occurs.
The extraction retains the complete template in raw input and an audit notice.
"""
import re


def project(template):
    name = str(template.name).strip().lower()
    def arg(key, default=""):
        return str(template.get(key).value).strip() if template.has(key) else default
    def plain(value):
        import mwparserfromhell as mw
        return mw.parse(value).strip_code().strip()
    numbers = r"[+−-]?\d[\d,.]*(?:\s*(?:million|billion))?"
    if name in ("ill", "interlanguage link") and arg(1):
        return plain(arg("lt", arg(1)))
    input_units = {"mm", "cm", "m", "meters", "km", "mi", "ft", "in", "acres", "ha", "kg", "km/h", "m2", "C"}
    if name in ("convert", "conv", "cvt") and re.fullmatch(numbers, arg(1)) and arg(2) in input_units:
        # Keep the supplied measurement; computed counterpart and rounding are
        # deliberately absent because their values are not in the pinned text.
        return f"{arg(1)} {arg(2)}"
    if name == "m" and re.fullmatch(numbers, arg(2)) and arg(1) in ("w", "s", "L", "l", "b", "d"):
        return f"{arg(2)} M{arg(1)}"
    if name in ("euro", "usd", "gbp", "renminbi") and not arg(1):
        return {"euro": "€", "usd": "US$", "gbp": "£", "renminbi": "CN¥"}[name]
    if name == "sub" and arg(1):
        return plain(arg(1))
    if name == "mpl" and arg(1) and arg(2):
        return plain(arg(1)) + plain(arg(2))
    if name == "ship" and arg(1) and arg(2):
        return plain(arg(1)) + " " + plain(arg(2))
    if name in ("uss", "mv") and arg(1):
        return name.upper() + " " + plain(arg(1))
    if name == "'" and not template.params:
        return "'"
    if name == "fxconvert" and arg("cursign"):
        # Only literal expressions are accepted. Never evaluate arbitrary #expr
        # or synthesize the template's externally supplied currency conversion.
        amount = arg(2)
        match = re.fullmatch(r"\{\{#expr:\s*(\d+)\s*\}\}", amount)
        if match:
            amount = match.group(1)
        if re.fullmatch(numbers, amount):
            return plain(arg("cursign")) + amount
    return None
