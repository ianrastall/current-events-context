"""Build schema-2.2 expanded day files from deep-research markdown (or an older
schema-2.1 expansion) plus the pinned portal revision.

    python build.py 2026-01-06 [...]        # write expanded/<Y>/<M>/<date>.yaml
    python build.py --report 2026-01-06     # print matching/review report only
"""
import copy
import datetime as dt
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from urllib.parse import urlparse, unquote

import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import wikiportal  # noqa: E402
import entities  # noqa: E402
import inputs  # noqa: E402
import corrections  # noqa: E402
import references  # noqa: E402

REPO = HERE.resolve().parents[1]
DR = REPO / "reference" / "deep-research"
OUT = REPO / "expanded"
OVERLAYS = HERE / "overlays"
LEGACY_COMMIT = "0f5cbef6"  # checkpoint holding the schema-2.1 expansions before the seed regeneration
LEGACY_FIX = HERE / "legacy_fix"


def legacy_doc(date):
    rel = f"{date[:4]}/{date[5:7]}/{date}.yaml"
    if (LEGACY_FIX / rel).exists():
        import hashlib
        guard = json.loads((HERE / "legacy-fixes.json").read_text(encoding="utf-8"))[date]
        original = subprocess.check_output(["git", "-C", str(REPO), "show", f"{guard['commit']}:{rel}"])
        if hashlib.sha256(original).hexdigest() != guard["original_sha256"] or inputs.digest(LEGACY_FIX / rel, text=True) != guard["corrected_sha256"]:
            raise ValueError(f"Legacy interpretation input drift for {date}")
        return yaml.safe_load((LEGACY_FIX / rel).read_text(encoding="utf-8"))
    text = subprocess.run(["git", "-C", str(REPO), "show", f"{LEGACY_COMMIT}:{rel}"],
                          capture_output=True, check=True).stdout.decode("utf-8")
    return yaml.safe_load(text)
FETCHED = "2026-09-22"
ROLES_PATH = HERE / "roles.json"
ROLES = json.loads(ROLES_PATH.read_text(encoding="utf-8")) if ROLES_PATH.exists() else {}

ENUM_SUPPORTS = ["summary", "key_data", "casualty_report", "details.what_happened", "details.why_it_matters"]

COUNTRIES = set("""Afghanistan|Albania|Algeria|Andorra|Angola|Antigua and Barbuda|Argentina|Armenia|Australia|Austria|Azerbaijan|Bahamas|Bahrain|Bangladesh|Barbados|Belarus|Belgium|Belize|Benin|Bhutan|Bolivia|Bosnia and Herzegovina|Botswana|Brazil|Brunei|Bulgaria|Burkina Faso|Burundi|Cambodia|Cameroon|Canada|Cape Verde|Central African Republic|Chad|Chile|China|Colombia|Comoros|Congo|Democratic Republic of the Congo|Republic of the Congo|Costa Rica|Croatia|Cuba|Cyprus|Czech Republic|Czechia|Denmark|Djibouti|Dominica|Dominican Republic|East Timor|Ecuador|Egypt|El Salvador|Equatorial Guinea|Eritrea|Estonia|Eswatini|Ethiopia|Fiji|Finland|France|Gabon|Gambia|The Gambia|Georgia|Germany|Ghana|Greece|Grenada|Guatemala|Guinea|Guinea-Bissau|Guyana|Haiti|Honduras|Hungary|Iceland|India|Indonesia|Iran|Iraq|Ireland|Israel|Italy|Ivory Coast|Jamaica|Japan|Jordan|Kazakhstan|Kenya|Kiribati|Kosovo|Kuwait|Kyrgyzstan|Laos|Latvia|Lebanon|Lesotho|Liberia|Libya|Liechtenstein|Lithuania|Luxembourg|Madagascar|Malawi|Malaysia|Maldives|Mali|Malta|Marshall Islands|Mauritania|Mauritius|Mexico|Micronesia|Moldova|Monaco|Mongolia|Montenegro|Morocco|Mozambique|Myanmar|Namibia|Nauru|Nepal|Netherlands|New Zealand|Nicaragua|Niger|Nigeria|North Korea|North Macedonia|Norway|Oman|Pakistan|Palau|Palestine|Panama|Papua New Guinea|Paraguay|Peru|Philippines|Poland|Portugal|Qatar|Romania|Russia|Rwanda|Saint Kitts and Nevis|Saint Lucia|Samoa|San Marino|Saudi Arabia|Senegal|Serbia|Seychelles|Sierra Leone|Singapore|Slovakia|Slovenia|Solomon Islands|Somalia|South Africa|South Korea|South Sudan|Spain|Sri Lanka|Sudan|Suriname|Sweden|Switzerland|Syria|Taiwan|Tajikistan|Tanzania|Thailand|Togo|Tonga|Trinidad and Tobago|Tunisia|Turkey|Türkiye|Turkmenistan|Tuvalu|Uganda|Ukraine|United Arab Emirates|United Kingdom|United States|Uruguay|Uzbekistan|Vanuatu|Vatican City|Venezuela|Vietnam|Yemen|Zambia|Zimbabwe|Greenland|Niue|Cook Islands|Somaliland|Northern Cyprus|Western Sahara|Puerto Rico|Hong Kong""".split("|"))
COUNTRY_ALIASES = {"U.S.": "United States", "US": "United States", "USA": "United States", "UK": "United Kingdom",
                   "U.K.": "United Kingdom", "DRC": "Democratic Republic of the Congo", "UAE": "United Arab Emirates",
                   "DR Congo": "Democratic Republic of the Congo", "Britain": "United Kingdom"}

HIGH_TIER = ("reuters.com", "apnews.com", "afp.com", "bbc.", "theguardian.com", "nytimes.com", "wsj.com", "ft.com",
             "bloomberg.com", "washingtonpost.com", "aljazeera.com", "npr.org", "economist.com", "cnn.com",
             "france24.com", "dw.com", "abc.net.au", "cbc.ca", "rfi.fr", "politico", "axios.com", "nhk.or.jp")
OFFICIAL = (".gov", ".gov.", ".mil", "un.org", "who.int", "europa.eu", "nato.int", "imf.org", "worldbank.org",
            "iaea.org", "ecb.europa.eu", "president.", "kremlin.ru", ".gouv.", "gc.ca", "admin.ch", "icc-cpi.int",
            "ohchr.org", "unhcr.org", "unicef.org", "wfp.org", "iea.org", "opec.org", "fifa.com", "olympics.com")
NGO = ("hrw.org", "amnesty.org", "msf.org", "icrc.org", "rsf.org", "cpj.org", "acleddata.com", "crisisgroup.org",
       "savethechildren", "oxfam", "hrana", "iranhr.net", "iom.int")
SPECIALIST = ("lloydslist", "spglobal.com", "defensenews.com", "janes.com", "thediplomat.com", "foreignpolicy.com",
              "justsecurity.org", "lawfaremedia.org", "understandingwar.org", "nature.com", "science.org",
              "bellingcat.com", "carnegieendowment.org", "csis.org", "chathamhouse.org", "brookings.edu",
              "atlanticcouncil.org", "globalissues.org", "war.gov", "twz.com", "eurasiareview.com")
BROADCAST = ("archive.org/details/BBC", "c-span.org")
ENCYCLOPEDIA = ("wikipedia.org", "britannica.com")

SOURCE_TYPE_MAP = {
    "news_agency": "news_report", "wire_service": "news_report", "wire service": "news_report",
    "global news agency": "news_report", "news agency": "news_report", "major_news_outlet": "news_report",
    "national news agency": "news_report", "news network": "broadcast", "news publisher": "news_report",
    "newspaper": "news_report", "regional_news": "news_report", "state news agency": "news_report",
    "state_affiliated": "news_report", "state_media": "news_report", "state media": "news_report",
    "news graphics": "news_report", "national public service outlet": "broadcast", "public broadcaster": "broadcast",
    "official_release": "official_release", "official press release": "official_release",
    "government_agency": "official_release", "official_communication": "official_release",
    "military official statement": "official_release", "international organization": "official_release",
    "science agency": "official_release", "energy agency report": "official_release",
    "sports governing body": "official_release", "university research release": "official_release",
    "NGO_report": "ngo_report", "ngo statement": "ngo_report", "cybersecurity report": "specialist_publication",
    "defense news outlet": "specialist_publication", "peer-reviewed journal": "specialist_publication",
    "medical abstract database": "specialist_publication", "trade_publication": "trade_publication",
    "news_report": "news_report", "broadcast": "broadcast", "encyclopedia": "encyclopedia",
    "ngo_report": "ngo_report", "advocacy_organization": "advocacy_organization",
    "specialist_publication": "specialist_publication",
}

OUTLET_BY_DOMAIN = {
    "reuters.com": "Reuters", "apnews.com": "Associated Press", "bbc.com": "BBC News", "bbc.co.uk": "BBC News",
    "theguardian.com": "The Guardian", "aljazeera.com": "Al Jazeera", "nytimes.com": "The New York Times",
    "washingtonpost.com": "The Washington Post", "cnn.com": "CNN", "npr.org": "NPR", "france24.com": "France 24",
    "dw.com": "Deutsche Welle", "bloomberg.com": "Bloomberg", "ft.com": "Financial Times", "wsj.com": "The Wall Street Journal",
    "en.wikipedia.org": "Wikipedia", "whitehouse.gov": "The White House", "timesofisrael.com": "The Times of Israel",
    "abc.net.au": "ABC News (Australia)", "euronews.com": "Euronews", "politico.com": "Politico", "politico.eu": "Politico Europe",
    "axios.com": "Axios", "cbsnews.com": "CBS News", "nbcnews.com": "NBC News", "abcnews.go.com": "ABC News",
    "foxnews.com": "Fox News", "independent.co.uk": "The Independent", "telegraph.co.uk": "The Telegraph",
    "news.un.org": "UN News", "rfi.fr": "RFI", "scmp.com": "South China Morning Post", "japantimes.co.jp": "The Japan Times",
    "straitstimes.com": "The Straits Times", "thehindu.com": "The Hindu", "hindustantimes.com": "Hindustan Times",
    "dawn.com": "Dawn", "kyivindependent.com": "The Kyiv Independent", "jpost.com": "The Jerusalem Post",
    "cnbc.com": "CNBC", "latimes.com": "Los Angeles Times", "usatoday.com": "USA Today", "time.com": "Time",
    "thenationalnews.com": "The National", "arabnews.com": "Arab News", "africanews.com": "Africanews",
    "channelnewsasia.com": "CNA", "sky.com": "Sky News", "news.sky.com": "Sky News", "lemonde.fr": "Le Monde",
    "theconversation.com": "The Conversation", "voanews.com": "Voice of America", "rferl.org": "Radio Free Europe/Radio Liberty",
    "economist.com": "The Economist", "cbc.ca": "CBC News", "globalnews.ca": "Global News", "9news.com.au": "9News",
    "smh.com.au": "The Sydney Morning Herald", "nzherald.co.nz": "The New Zealand Herald", "rnz.co.nz": "RNZ",
    "premiumtimesng.com": "Premium Times", "punchng.com": "Punch", "dailypost.ng": "Daily Post",
    "thecitizen.co.tz": "The Citizen", "nation.africa": "Nation", "capitalfm.co.ke": "Capital FM",
    "ukrinform.net": "Ukrinform", "pravda.com.ua": "Ukrainska Pravda", "meduza.io": "Meduza", "tass.com": "TASS",
    "understandingwar.org": "Institute for the Study of War", "hrw.org": "Human Rights Watch", "amnesty.org": "Amnesty International",
    "iranintl.com": "Iran International", "irna.ir": "IRNA", "tehrantimes.com": "Tehran Times", "presstv.ir": "Press TV",
    "gov.uk": "UK Government", "state.gov": "U.S. Department of State", "justice.gov": "U.S. Department of Justice",
    "defense.gov": "U.S. Department of Defense", "war.gov": "U.S. Department of War", "europa.eu": "European Union",
    "ec.europa.eu": "European Commission", "consilium.europa.eu": "Council of the EU", "nato.int": "NATO",
    "who.int": "World Health Organization", "imf.org": "International Monetary Fund", "espn.com": "ESPN",
    "theathletic.com": "The Athletic", "variety.com": "Variety", "hollywoodreporter.com": "The Hollywood Reporter",
    "deadline.com": "Deadline", "nhk.or.jp": "NHK", "kyodonews.net": "Kyodo News", "yonhapnews.co.kr": "Yonhap",
    "en.yna.co.kr": "Yonhap", "koreaherald.com": "The Korea Herald", "focustaiwan.tw": "Focus Taiwan",
    "taipeitimes.com": "Taipei Times", "globaltimes.cn": "Global Times", "xinhuanet.com": "Xinhua", "news.cn": "Xinhua",
    "english.news.cn": "Xinhua", "cgtn.com": "CGTN", "thejakartapost.com": "The Jakarta Post", "bangkokpost.com": "Bangkok Post",
    "rappler.com": "Rappler", "inquirer.net": "Philippine Daily Inquirer", "gmanetwork.com": "GMA News",
    "abs-cbn.com": "ABS-CBN News", "batimes.com.ar": "Buenos Aires Times", "mercopress.com": "MercoPress",
    "efe.com": "EFE", "elpais.com": "El País", "infobae.com": "Infobae", "swissinfo.ch": "Swissinfo",
    "thelocal.fr": "The Local France", "rte.ie": "RTÉ", "irishtimes.com": "The Irish Times", "spiegel.de": "Der Spiegel",
    "lemonde.fr/en": "Le Monde", "vox.com": "Vox", "semafor.com": "Semafor", "newsweek.com": "Newsweek",
    "thehill.com": "The Hill", "nypost.com": "New York Post", "startribune.com": "Star Tribune", "mprnews.org": "MPR News",
    "military.com": "Military.com", "defensenews.com": "Defense News", "breakingdefense.com": "Breaking Defense",
    "twz.com": "The War Zone", "aviation-safety.net": "Aviation Safety Network", "globalissues.org": "Global Issues",
    "justsecurity.org": "Just Security", "crisisgroup.org": "International Crisis Group", "acleddata.com": "ACLED",
    "archive.org": "Internet Archive", "britannica.com": "Encyclopaedia Britannica", "cfr.org": "Council on Foreign Relations",
    "csis.org": "CSIS", "brookings.edu": "Brookings Institution", "atlanticcouncil.org": "Atlantic Council",
    "chathamhouse.org": "Chatham House", "thediplomat.com": "The Diplomat", "foreignpolicy.com": "Foreign Policy",
    "eurasiareview.com": "Eurasia Review", "middleeasteye.net": "Middle East Eye", "al-monitor.com": "Al-Monitor",
    "english.alarabiya.net": "Al Arabiya", "alarabiya.net": "Al Arabiya", "gulfnews.com": "Gulf News",
    "khaleejtimes.com": "Khaleej Times", "saudigazette.com.sa": "Saudi Gazette", "ahram.org.eg": "Al-Ahram",
    "english.ahram.org.eg": "Al-Ahram", "haaretz.com": "Haaretz", "ynetnews.com": "Ynetnews", "i24news.tv": "i24NEWS",
    "kurdistan24.net": "Kurdistan24", "rudaw.net": "Rudaw", "sudantribune.com": "Sudan Tribune",
    "dabangasudan.org": "Radio Dabanga", "garoweonline.com": "Garowe Online", "hiiraan.com": "Hiiraan Online",
    "theeastafrican.co.ke": "The EastAfrican", "allafrica.com": "AllAfrica", "news24.com": "News24",
    "dailymaverick.co.za": "Daily Maverick", "timeslive.co.za": "TimesLIVE", "tolonews.com": "TOLOnews",
    "geo.tv": "Geo News", "tribune.com.pk": "The Express Tribune", "thedailystar.net": "The Daily Star",
    "bdnews24.com": "bdnews24.com", "kathmandupost.com": "The Kathmandu Post", "myrepublica.nagariknetwork.com": "MyRepublica",
    "ndtv.com": "NDTV", "indianexpress.com": "The Indian Express", "timesofindia.indiatimes.com": "The Times of India",
    "economictimes.indiatimes.com": "The Economic Times", "livemint.com": "Mint", "deccanherald.com": "Deccan Herald",
}


# ---------------------------------------------------------------- text helpers

ENTITY_RE = re.compile(r'entity\[\s*"([^"]*)"\s*,\s*"([^"]*)"\s*(?:,\s*"([^"]*)"\s*)?\]')
CITE_TOKEN_RE = re.compile(r"\s*cite(?:turn\w+?)+(?=\s|$|[.,;:)\]])")
CITE_TOKEN_RE2 = re.compile(r"\s*\ue200?cite\ue202?turn[\w\ue202]*\ue201?")


def strip_markup(s):
    s = ENTITY_RE.sub(lambda m: m.group(2), s)
    s = CITE_TOKEN_RE2.sub("", s)
    s = re.sub(r"\s*\bcite(?:turn\d+\w*?)+\b", "", s)
    s = re.sub(r"\s*citeturn\S*", "", s)
    s = s.replace("\\-", "-").replace("\\=", "=").replace("\\_", "_").replace("\\.", ".").replace("\\*", "*")
    s = s.replace("\\#", "#").replace("\\+", "+").replace("\\!", "!").replace("\\[", "[").replace("\\]", "]")
    s = s.replace("\\$", "$").replace("\\~", "~").replace("\\<", "<").replace("\\>", ">").replace("\\&", "&")
    s = re.sub(r"\s*【[^】]*】", "", s)
    s = s.replace("**", "")
    s = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"\1", s)  # *italic*
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def take_footnotes(s, max_ref):
    """Strip trailing numeric footnote markers (Jan-1 report style); return (text, refs)."""
    refs = []
    if not max_ref:
        return s, refs

    def repl(m):
        nums = [int(x) for x in re.split(r"[ ,]+", m.group(1)) if x]
        if all(1 <= n <= max_ref for n in nums):
            refs.extend(nums)
            return ""
        return m.group(0)

    pat = re.compile(r"(?:(?<=[^\d\s][.!?\u201d\"\u2019)\]:;,])|(?<=[a-z%]))(\d{1,3}(?:[ ,]\d{1,3})*)(?=\s|$|[.,;:](?:\s|$))")
    out = pat.sub(repl, s)
    out = re.sub(r"[ \t]+", " ", out).strip()
    return out, refs


def entities_in(raw):
    return [(m.group(1), m.group(2), m.group(3) or "") for m in ENTITY_RE.finditer(raw)]


def kebab(s):
    s = s.lower()
    s = re.sub(r"[’'\"()]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def domain(url):
    try:
        net = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return net[4:] if net.startswith("www.") else net


def outlet_for(url):
    d = domain(url)
    parts = d.split(".")
    for i in range(len(parts) - 1):
        k = ".".join(parts[i:])
        if k in OUTLET_BY_DOMAIN:
            return OUTLET_BY_DOMAIN[k]
    return d


def source_type_for(url, outlet=""):
    u = url.lower()
    d = domain(url)
    if any(x in u for x in BROADCAST):
        return "broadcast"
    if any(x in d for x in ENCYCLOPEDIA):
        return "encyclopedia"
    if any(x in d for x in NGO):
        return "ngo_report"
    if any(x in d for x in SPECIALIST):
        return "specialist_publication"
    if d.endswith(".gov") or ".gov." in d or d.endswith(".mil") or any(x in d for x in OFFICIAL):
        return "official_release"
    return "news_report"


def tier_for(url, stype):
    d = domain(url)
    if stype == "official_release":
        return "high"
    if any(x in d for x in HIGH_TIER):
        return "high"
    if stype == "encyclopedia":
        return "medium"
    return "medium"


def url_date(url):
    m = re.search(r"(20\d\d)[/-](\d\d)[/-](\d\d)", url)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    m = re.search(r"/(20\d\d)/(\d{1,2})/(\d{1,2})/", url)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    return None


MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}


def parse_human_date(s):
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", s)
    if m:
        return m.group(0)
    m = re.search(r"([A-Z][a-z]+)\s+(\d{1,2}),\s*(20\d\d)", s)
    if m and m.group(1).lower() in MONTHS:
        return dt.date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))).isoformat()
    return None


def title_from_url(url):
    path = unquote(urlparse(url).path).rstrip("/")
    seg = path.split("/")[-1] if path else ""
    seg = re.sub(r"\.(html?|php|aspx?|cms)$", "", seg)
    seg = re.sub(r"-?20\d\d-\d\d-\d\d$", "", seg)
    seg = re.sub(r"[-_]?[0-9a-f]{16,}$", "", seg)
    seg = re.sub(r"[-_]\d{5,}$", "", seg)
    words = [w for w in re.split(r"[-_+]", seg) if w]
    if len(words) < 3:
        return None
    t = " ".join(words)
    return t[0].upper() + t[1:]


def norm_url(u):
    u = u.strip().rstrip(").,;")
    u = u.replace("\\_", "_")
    return u.rstrip("/")


# ---------------------------------------------------------------- markdown parse

LABELS = {
    "category & subcategory": "category", "category and subcategory": "category", "category": "category",
    "geography": "geography", "summary": "summary", "what happened": "what_happened",
    "why it matters": "why_it_matters", "actors": "actors", "casualties/damage": "casualties",
    "casualties / damage": "casualties", "casualties": "casualties", "sources": "sources",
    "uncertainty": "uncertainty", "uncertainty notes": "uncertainty", "key data": "key_data_text",
}


def parse_works(lines):
    works = {}
    for ln in lines:
        m = re.match(r"^\s*(\d+)\.\s+(.*)$", ln)
        if not m:
            continue
        n = int(m.group(1))
        body = m.group(2).strip()
        um = re.search(r"\((https?://[^)\s]+)\)", body) or re.search(r"(https?://\S+)", body)
        if not um:
            continue
        url = norm_url(um.group(1))
        head = body.split(", accessed")[0] if ", accessed" in body else body.split("[http")[0]
        head = strip_markup(head).strip().rstrip(",")
        acc = None
        am = re.search(r"accessed\s+([A-Z][a-z]+ \d{1,2}, 20\d\d)", body)
        if am:
            acc = parse_human_date(am.group(1))
        title, outlet = head, None
        for sep in (" - ", " | ", " — ", " – "):
            if sep in head:
                a, b = head.rsplit(sep, 1)
                if 0 < len(b) <= 60:
                    title, outlet = a.strip(), b.strip()
                    break
        works[n] = {"id": n, "title": title or url, "outlet": outlet or outlet_for(url), "url": url, "accessed": acc}
    return works


def normalize_pua(t):
    """Deep-research exports wrap entity/cite markup in private-use characters."""
    t = re.sub("cite[^]*", "", t)
    return t.replace("", "").replace("", "").replace("", "")


def parse_md(path):
    raw_lines = normalize_pua(path.read_text(encoding="utf-8")).splitlines()
    intro, outro, events, works_lines = [], [], [], []
    mode = "intro"
    cur = None
    for ln in raw_lines:
        be = re.match(r"^\s*\*\*\s*Event:\s*(.+?)\s*\*\*\s*$", ln)
        if be:
            cur = {"title": strip_markup(be.group(1)), "lines": []}
            events.append(cur)
            mode = "event"
            continue
        h = re.match(r"^(#{1,6})\s*(.*)$", ln)
        if h:
            title = strip_markup(h.group(2)).strip()
            low = title.lower()
            if low.startswith("event:") or low.startswith("event "):
                cur = {"title": title.split(":", 1)[1].strip() if ":" in title else title, "lines": []}
                events.append(cur)
                mode = "event"
                continue
            if "works cited" in low or low in ("sources", "references", "bibliography"):
                mode = "works"
                continue
            if title in ("---", "") or h.group(1) == "#":
                continue
            if mode == "event":
                mode = "outro"
            continue
        if mode == "intro":
            intro.append(ln)
        elif mode == "event":
            cur["lines"].append(ln)
        elif mode == "outro":
            outro.append(ln)
        else:
            works_lines.append(ln)
    works = parse_works(works_lines)
    max_ref = max(works) if works else 0
    parsed = [parse_event_block(e, max_ref) for e in events]
    return {"intro": paragraphs(intro, max_ref), "outro": paragraphs(outro, max_ref), "events": parsed,
            "works": works, "max_ref": max_ref}


def paragraphs(lines, max_ref):
    out = []
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("|") or s == "---" or s.startswith("#"):
            continue
        if s.startswith(("* ", "- ")):
            continue
        t, _ = take_footnotes(strip_markup(s), max_ref)
        if len(t) > 60:
            out.append(t)
    return out


def parse_event_block(ev, max_ref):
    fields = {"title": strip_markup(ev["title"]), "raw": "\n".join(ev["lines"])}
    fields["entities"] = entities_in(fields["raw"] + " " + ev["title"])
    label = None
    tables = []
    tbl = None
    extra = []
    for ln in ev["lines"]:
        s = ln.rstrip()
        if s.strip().startswith("|"):
            cells = [c.strip() for c in s.strip().strip("|").split("|")]
            if tbl is None:
                tbl = {"header": cells, "rows": []}
                tables.append(tbl)
            elif all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                pass
            else:
                tbl["rows"].append(cells)
            continue
        tbl = None
        m = re.match(r"^\s{0,1}[*-]\s+\*\*([^*:]+?):?\*\*:?\s*(.*)$", s)
        if m and m.group(1).strip().lower().rstrip(":") in LABELS:
            label = LABELS[m.group(1).strip().lower().rstrip(":")]
            rest = m.group(2).strip()
            if label in ("category", "geography", "summary", "casualties", "uncertainty", "key_data_text"):
                fields[label] = rest
            else:
                fields.setdefault(label, [])
                if rest:
                    fields[label].append(rest)
            continue
        m = re.match(r"^\s+[*-]\s+(.*)$", s)
        if m and label:
            item = m.group(1).strip()
            if label in ("summary", "casualties", "category", "geography", "uncertainty"):
                fields[label] = (fields.get(label, "") + " " + item).strip()
            else:
                fields.setdefault(label, []).append(item)
            continue
        if s.strip():
            if label == "summary":
                fields["summary"] = fields.get("summary", "") + " " + s.strip()
            else:
                extra.append(s.strip())
    fields["tables"] = tables
    fields["extra"] = extra
    fields["max_ref"] = max_ref
    return fields


# ---------------------------------------------------------------- field builders

NUMWORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                        "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
NUMWORDS.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
                 "hundred": 100, "a dozen": 12, "dozen": 12})


def first_int(s):
    if s is None:
        return None
    t = s.replace(",", "")
    m = re.search(r"\d+", t)
    if m:
        return int(m.group(0))
    low = s.lower()
    for w, n in sorted(NUMWORDS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{w}\b", low):
            return n
    return None


def parse_casualties(text):
    rep = {"killed": None, "injured": None, "displaced": None, "missing": None, "arrest_count": None, "damage": None}
    notes = []
    if not text:
        return rep, notes
    t = strip_markup(text)
    keys = [("killed", r"Killed|Deaths?|Dead|Fatalities"), ("injured", r"Injured|Wounded"),
            ("displaced", r"Displaced"), ("missing", r"Missing"), ("arrest_count", r"Arrest(?:s| Count)?|Arrested|Detained"),
            ("damage", r"Damage(?: Descriptions?)?")]
    spans = []
    for k, pat in keys:
        m = re.search(rf"(?:^|[;,.]\s*|\s)({pat})\s*:\s*", t, re.I)
        if m:
            spans.append((m.start(1), m.end(), k))
    spans.sort()
    for i, (st, en, k) in enumerate(spans):
        end = spans[i + 1][0] if i + 1 < len(spans) else len(t)
        val = t[en:end].strip().rstrip(";,").strip()
        val, _ = take_footnotes(val, 999)
        if k == "damage":
            rep["damage"] = None if re.fullmatch(r"(?i)(unknown|none|n/?a|not reported|none reported)\.?", val) else val
            continue
        low = val.lower()
        if re.match(r"(?i)(unknown|not (?:reported|specified|stated|confirmed)|unclear|n/?a|none reported|no\b.*reported)", low):
            rep[k] = None
            continue
        if re.match(r"(?i)none\b|zero\b|0\b", low):
            rep[k] = 0
            continue
        n = first_int(val)
        rep[k] = n
        if n is not None and re.search(r"(?i)\d\s*[–-]\s*\d|\d\s+to\s+\d|conflict|disput|vary|varies|contradict|between\s+\d", val):
            notes.append(f"{k.replace('_', ' ').capitalize()} figure is reported as a range or disputed: {val}")
    return rep, notes


def split_list(s):
    s = strip_markup(s)
    parts, depth, buf = [], 0, ""
    sep = ";" if ";" in s else ","
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    parts.append(buf)
    out = []
    for p in parts:
        p, _ = take_footnotes(p.strip().rstrip("."), 999)
        p = p.strip()
        if not p or p.lower() in ("and",):
            continue
        p = re.sub(r"^and\s+", "", p)
        if out and re.fullmatch(r"[A-Z]{2,3}(?:\s*\(.*\))?", p):
            out[-1] = out[-1] + ", " + p      # "Attorneys General of CA, CO, IL" stays one actor
            continue
        out.append(p)
    return out


PERSON_ROLE = re.compile(r"(?i)\b(president|minister|premier|chancellor|king|queen|prince|leader|chief|ceo|chair|"
                         r"secretary|general|spokes|governor|mayor|senator|representative|mp\b|judge|justice|"
                         r"owner|founder|director|commander|envoy|ambassador|official|head|lawmaker|politician|"
                         r"actor|actress|player|coach|athlete|journalist|activist|cleric|ayatollah|pope|suspect|"
                         r"victim|author|singer|rapper|economist|scientist|attorney|prosecutor|lawyer|pilot|"
                         r"captain|founder|candidate|deputy|emir|sultan|sheikh|crown|dictator|rebel leader|"
                         r"director-general|commissioner|chairman|chairwoman|executive)\b")
ORG_WORD = re.compile(r"(?i)\b(ministry|police|forces?|army|party|council|agency|office|court|government|union|bank|"
                      r"commission|organi[sz]ation|department|group|company|corp|inc|university|association|"
                      r"committee|league|movement|front|authority|service|guard|news|network|institute|federation|"
                      r"programme|program|coalition|alliance|club|airlines?|parliament|congress|senate|assembly|"
                      r"cabinet|military|navy|air force|corps|brigade|militia|cartel|gang|hamas|hezbollah|houthis?|"
                      r"taliban|isis|islamic state|al-shabaab|nato|un\b|united nations|eu\b|european|opec|fbi|cia|"
                      r"ice\b|dhs|doj|pentagon|white house|kremlin|board|fund|foundation|society|reserve|exchange|"
                      r"media|press|times|post|journal|tribunal|legislature|regime|administration|ngo|red cross|"
                      r"red crescent|who\b|imf|wto|iaea|rsf|sdf|rsf\b|irgc|idf|tatmadaw|junta|commission|team|"
                      r"airport|station|hospital|school|church|mosque|temple|companies|operators|firms|residents|"
                      r"populations?|civilians|protesters|investors|markets?|participants|officials|authorities|"
                      r"workers|miners|farmers|families|communities|groups|states)\b")


def classify_actor(a):
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", a)
    name, role = (m.group(1).strip(), m.group(2).strip()) if m else (a.strip(), "")
    base = COUNTRY_ALIASES.get(name, name)
    if base in COUNTRIES:
        return "state", base, role
    if role and PERSON_ROLE.search(role) and not ORG_WORD.search(name):
        return "person", name, role
    if ORG_WORD.search(name) or ORG_WORD.search(role):
        return "org", name, role
    words = name.split()
    if 2 <= len(words) <= 4 and all(w[:1].isupper() for w in words if w not in ("de", "da", "van", "von", "bin", "al", "el", "la", "le", "di", "dos", "das", "del")):
        return "person", name, role
    return "org", name, role


def countries_in(text):
    """Country names in order of appearance; longer names are matched first and masked
    so "South Sudan" does not also yield "Sudan"."""
    work = text
    hits = []
    for c in sorted(COUNTRIES | set(COUNTRY_ALIASES), key=lambda c: (-len(c), c)):
        pat = rf"(?<![\w$-]){re.escape(c)}(?![\w$-])"
        if c == "Jordan":
            pat = rf"(?<![A-Z]\. ){pat}"          # "Michael B. Jordan"
        for m in re.finditer(pat, work):
            name = COUNTRY_ALIASES.get(c, c)
            if name == "Georgia" and re.search(r"Georgia\s*\(U\.?S\.? state\)|, Georgia|Atlanta", text):
                continue
            hits.append((m.start(), name))
        work = re.sub(pat, lambda m: "#" * len(m.group(0)), work)
    found = []
    for _, name in sorted(hits):
        if name not in found:
            found.append(name)
    return found


def order_by_position(names, text):
    return sorted(names, key=lambda n: (text.find(n) if text.find(n) >= 0 else 10 ** 6))


# ---------------------------------------------------------------- portal matching

STOP = set("""the a an of in on at to for and or with by from as is are was were be been has have had its it this that
those these into over after before during amid against their his her they them than more most at least people killed
injured others other says said reports reported report government new also including which who while where when two
three four five six seven eight nine ten per cent percent us u.s. united states president minister prime""".split())


def sig_words(t):
    ws = re.findall(r"[A-Za-zÀ-ÿ][\w'’-]+|\d[\d,.]*", t)
    return {w.lower().strip("'’") for w in ws if w.lower() not in STOP and len(w) > 2}


def similarity(md_text, portal_text):
    a, b = sig_words(md_text), sig_words(portal_text)
    if not a or not b:
        return 0.0
    return len(a & b) / (len(b) ** 0.85)


# ---------------------------------------------------------------- source records

def parse_source_line(item, max_ref, file_date):
    raw = item
    urls = re.findall(r"\]\((https?://[^)\s]+)\)", raw) or re.findall(r"`(https?://[^`\s]+)`", raw) or \
        re.findall(r"<(https?://[^>\s]+)>", raw) or re.findall(r"(https?://[^\s)\]`,]+)", raw)
    if not urls:
        t = strip_markup(raw)
        m = re.match(r"^\s*([^:(—]+?)\s*(?:\(([^)]*)\))?\s*[:—-]", t)
        return {"no_url": True, "outlet": (m.group(1).strip() if m else t[:60]), "when": (m.group(2) if m and m.group(2) else "")}
    url = norm_url(urls[0])
    pos = raw.find(urls[0])
    lead = raw[:pos]
    lead = re.sub(r"\[[^\]]*$", "", lead)
    outlet = strip_markup(lead).strip().strip("`").strip()
    outlet = re.sub(r"\s*[—–:,\-]+\s*$", "", outlet).strip()
    outlet = re.sub(r"^\s*(Source|Outlet(?: Name)?)\s*:\s*", "", outlet, flags=re.I)
    outlet = re.sub(r"\s*[;,]?\s*URL\s*:?\s*$", "", outlet, flags=re.I).strip().rstrip(";,").strip()
    if not outlet or len(outlet) > 80 or outlet.lower().startswith("http") or re.fullmatch(r"[\w.-]+\.[a-z]{2,}", outlet):
        outlet = outlet_for(url)
    tail = raw[pos + len(urls[0]):]
    tail_clean = strip_markup(tail)
    pdate = None
    pm = re.search(r"Publication Date:\s*([^—;|]+)", tail_clean, re.I)
    if pm:
        pdate = parse_human_date(pm.group(1))
    if not pdate:
        pdate = parse_human_date(tail_clean[:80])
    if not pdate:
        pdate = url_date(url) or file_date
    quotes = []
    qm = re.search(r"Quotes?:\s*(.*)$", tail_clean, re.I)
    qsrc = qm.group(1) if qm else (tail_clean if max_ref else "")
    for q in re.findall(r"[“\"]([^”\"]{12,400})[”\"]", qsrc):
        q = q.strip()
        if q and q not in quotes:
            quotes.append(q)
    refs = []
    if max_ref:
        _, refs = take_footnotes(tail_clean.strip(), max_ref)
    sm = re.search(r"Supports?:\s*(.*?)(?:Quotes?:|$)", tail_clean, re.I)
    sup_text = (sm.group(1) if sm else tail_clean).lower()
    supports = ["summary", "details.what_happened"]
    if re.search(r"killed|death|dead|casualt|injur|wounded|toll|fatalit|missing|displac", sup_text):
        supports.append("casualty_report")
    if re.search(r"\d", sup_text) and re.search(r"figure|percent|%|\$|billion|million|price|rate|count|number|data|statistic|toll", sup_text):
        supports.append("key_data")
    if re.search(r"implication|signific|context|reaction|matters|impact|framing|analysis|criticism|concern", sup_text):
        supports.append("details.why_it_matters")
    stype = source_type_for(url, outlet)
    return {"outlet": outlet, "url": url, "publication_date": pdate, "source_type": stype,
            "reliability_tier": tier_for(url, stype), "supports": supports, "contradicts": [],
            "quoted_material": quotes[:3], "refs": refs}


# ---------------------------------------------------------------- event assembly

def md_event_to_record(f, date):
    max_ref = f["max_ref"]
    cat_raw = strip_markup(f.get("category", "")) or "Uncategorized"
    cat_raw, _ = take_footnotes(cat_raw, max_ref)
    if "/" in cat_raw:
        category, subcategory = [x.strip() for x in cat_raw.split("/", 1)]
    elif " - " in cat_raw:
        category, subcategory = [x.strip() for x in cat_raw.split(" - ", 1)]
    else:
        category, subcategory = cat_raw.strip(), ""
    summary, sref = take_footnotes(strip_markup(f.get("summary", "")), max_ref)
    wh, why = [], []
    for it in f.get("what_happened", []):
        t, _ = take_footnotes(strip_markup(it), max_ref)
        if t:
            wh.append(t)
    for it in f.get("why_it_matters", []):
        t, _ = take_footnotes(strip_markup(it), max_ref)
        if t:
            why.append(t)
    unc = []
    if f.get("uncertainty"):
        t, _ = take_footnotes(strip_markup(f["uncertainty"]), max_ref)
        if t and not re.fullmatch(r"(?i)none\.?", t):
            unc.append(t)
    # actors
    prim, sec = [], []
    for it in f.get("actors", []):
        t = strip_markup(it)
        m = re.match(r"(?i)^(primary|secondary)\s*(?:actors?)?\s*:\s*(.*)$", t)
        if m:
            (prim if m.group(1).lower() == "primary" else sec).extend(split_list(m.group(2)))
        else:
            prim.extend(split_list(t))
    # entities
    people, orgs, states, places = [], [], [], []
    seen = set()
    for typ, name, desc in f["entities"]:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        tl = typ.lower()
        if tl == "country":
            states.append(COUNTRY_ALIASES.get(name, name))
        elif tl in ("people", "person", "politician", "athlete", "musician", "actor", "military_person", "journalist"):
            people.append({"name": name, "role": entities.fix_role(desc)})
        elif tl in ("place", "city", "region", "location", "state", "province", "geographic_feature", "body_of_water", "point_of_interest", "building"):
            if COUNTRY_ALIASES.get(name, name) in COUNTRIES:
                states.append(COUNTRY_ALIASES.get(name, name))
            elif "organization" in desc.lower():
                orgs.append({"name": name, "description": entities.fix_role(desc)})
            else:
                places.append(name)
        else:
            orgs.append({"name": name, "description": entities.fix_role(desc)})
    prim = [entities.clean_actor(a) for a in prim if entities.clean_actor(a)]
    sec = [entities.clean_actor(a) for a in sec if entities.clean_actor(a)]
    for a in prim + sec:
        kind, name, role = entities.classify(a, COUNTRIES, COUNTRY_ALIASES)
        if kind == "skip" or name.lower() in seen:
            continue
        seen.add(name.lower())
        if kind == "state":
            states.append(name)
        elif kind == "person":
            people.append({"name": name, "role": role})
        else:
            orgs.append({"name": name, "description": role})
    # geography
    geo_raw = strip_markup(f.get("geography", ""))
    geo_raw, _ = take_footnotes(geo_raw, max_ref)
    countries, gplaces = [], []
    for part in re.split(r"[;,]", geo_raw):
        p = part.strip().rstrip(".")
        if not p:
            continue
        base = COUNTRY_ALIASES.get(p, p)
        if base in COUNTRIES:
            if base not in countries:
                countries.append(base)
        elif p.lower() not in ("global", "worldwide", "international"):
            if p not in gplaces:
                gplaces.append(p)
    for s in states:
        if s not in countries and s in COUNTRIES:
            countries.append(s)
    for p in places:
        if p not in gplaces:
            gplaces.append(p)
    for c in countries:
        if c not in states:
            states.append(c)
    cas, cas_notes = parse_casualties(f.get("casualties", ""))
    unc.extend(cas_notes)
    # key data
    key_data = []
    for tb in f["tables"]:
        hdr = [take_footnotes(strip_markup(h), max_ref)[0] for h in tb["header"]]
        for row in tb["rows"]:
            cells = [strip_markup(c) for c in row]
            if len(cells) < 2 or not cells[0]:
                continue
            refs = []
            vals = []
            for c in cells[1:]:
                toks = c.split()
                if max_ref and len(toks) > 1 and re.fullmatch(r"\d{1,3}", toks[-1]) and 1 <= int(toks[-1]) <= max_ref:
                    refs.append(int(toks[-1]))
                    c = " ".join(toks[:-1])
                c, r2 = take_footnotes(c, max_ref)
                refs.extend(r2)
                vals.append(c)
            label = take_footnotes(cells[0], max_ref)[0]
            if len(vals) == 1:
                value = vals[0]
            else:
                value = "; ".join(f"{h}: {v}" for h, v in zip(hdr[1:], vals) if v)
            key_data.append({"label": label, "value": value, "refs": sorted(set(refs))})
    sources, unsourced = [], []
    for it in f.get("sources", []):
        s = parse_source_line(it, max_ref, date)
        if s and s.get("no_url"):
            unsourced.append(s["outlet"] + (f" ({s['when']})" if s["when"] else ""))
        elif s:
            sources.append(s)
    return {
        "category": category, "subcategory": subcategory, "headline": f["title"].rstrip("*").strip(),
        "summary": summary, "what_happened": wh, "why_it_matters": why, "uncertainty_notes": unc,
        "actors": {"primary": prim, "secondary": sec},
        "entities": {"people": people, "organizations": orgs, "states": states},
        "geography": {"countries": countries, "places": gplaces, "coordinates": []},
        "casualty_report": cas, "key_data": key_data, "sources": sources, "summary_refs": sref,
        "legacy_notes": ("The deep-research report names these sources without URLs: " + "; ".join(unsourced) + ".") if unsourced else "",
    }


def legacy_event_to_record(e, date):
    def lst(x):
        if x is None:
            return []
        return [str(i) for i in x] if isinstance(x, list) else [str(x)]

    det = e.get("details") or {}
    ent = e.get("entities") or {}
    people = []
    for p in ent.get("people") or []:
        people.append(p if isinstance(p, dict) else {"name": str(p), "role": ""})
    orgs = []
    for o in ent.get("organizations") or []:
        orgs.append(o if isinstance(o, dict) else {"name": str(o), "description": ""})
    geo = e.get("geography") or {}
    cas = dict(e.get("casualty_report") or {})
    rep = {k: cas.get(k) for k in ("killed", "injured", "displaced", "missing", "arrest_count")}
    for k in list(rep):
        v = rep[k]
        if isinstance(v, str):
            rep[k] = first_int(v)
    rep["damage"] = cas.get("damage") if isinstance(cas.get("damage"), (str, type(None))) else str(cas.get("damage"))
    sources = []
    for s in (e.get("sources") or {}).get("external") or []:
        url = norm_url(str(s.get("url", "")))
        if not url.startswith("http"):
            continue
        st = SOURCE_TYPE_MAP.get(str(s.get("source_type")), None) or source_type_for(url)
        sup_raw = lst(s.get("supports"))
        sup = [x for x in sup_raw if x in ENUM_SUPPORTS]
        if not sup:
            sup = ["summary", "details.what_happened"]
            text = " ".join(sup_raw).lower()
            if re.search(r"killed|death|dead|casualt|injur|wounded|toll", text):
                sup.append("casualty_report")
        con = [x for x in lst(s.get("contradicts")) if x in ENUM_SUPPORTS]
        pd = str(s.get("publication_date") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", pd):
            pd = parse_human_date(pd) or url_date(url) or date
        tier = s.get("reliability_tier") if s.get("reliability_tier") in ("high", "medium", "low") else tier_for(url, st)
        qm = s.get("quoted_material")
        quotes = [str(q) for q in qm] if isinstance(qm, list) else []
        sources.append({"outlet": str(s.get("outlet") or outlet_for(url)), "url": url, "publication_date": pd,
                        "source_type": st, "reliability_tier": tier, "supports": sup, "contradicts": con,
                        "quoted_material": quotes, "refs": []})
    imp = e.get("importance")
    if isinstance(imp, str):
        imp = {"high": 8, "medium": 6, "low": 4}.get(imp.lower())
    wp = (e.get("sources") or {}).get("wikipedia_portal") or {}
    return {
        "category": str(e.get("category") or "Uncategorized"), "subcategory": str(e.get("subcategory") or ""),
        "headline": str(e.get("headline") or ""), "summary": " ".join(str(e.get("summary") or "").split()),
        "what_happened": lst(det.get("what_happened")), "why_it_matters": lst(det.get("why_it_matters")),
        "uncertainty_notes": lst(det.get("uncertainty_notes")),
        "actors": {"primary": lst((e.get("actors") or {}).get("primary")), "secondary": lst((e.get("actors") or {}).get("secondary"))},
        "entities": {"people": people, "organizations": orgs, "states": lst(ent.get("states"))},
        "geography": {"countries": lst(geo.get("countries")), "places": lst(geo.get("places")), "coordinates": []},
        "casualty_report": rep, "key_data": [], "sources": sources, "summary_refs": [],
        "legacy_topics": lst(e.get("topics")), "legacy_importance": imp,
        "legacy_event_type": [kebab(x) for x in lst((e.get("classification") or {}).get("event_type"))],
        "legacy_tags": [kebab(x) for x in lst((e.get("classification") or {}).get("tags"))],
        "legacy_time": e.get("time") or {}, "legacy_portal": wp, "legacy_notes": str(e.get("notes") or ""),
        "legacy_confidence": e.get("confidence") or {},
    }


PORTAL_CASUALTY = [
    ("killed", r"(?:(at least|more than|over|about|around|nearly|up to)\s+)?([\w,-]+(?:\s+hundred)?)\s+(?:\w+\s+){0,4}?(?:people\s+|others\s+|persons\s+|civilians\s+|soldiers\s+)?(?:are|were|is|was|have been|has been)\s+(?:\w+\s+)?killed"),
    ("injured", r"([\w,-]+)\s+(?:others?\s+|people\s+)?(?:are|were|is|was)?\s*(?:\w+\s+)?(?:injured|wounded)"),
    ("missing", r"([\w,-]+)\s+(?:others?\s+|people\s+)?(?:are|were)?\s*(?:reported\s+)?missing"),
]


def portal_casualties(text):
    rep = {"killed": None, "injured": None, "displaced": None, "missing": None, "arrest_count": None, "damage": None}
    t = text
    m = re.search(r"(?i)(?:at least |more than |over |about |around |nearly )?(\d[\d,]*|[a-z]+(?:-[a-z]+)?)\s+(?:[\w'-]+\s+){0,8}?(?:are|were|is|was|have been|has been)\s+(?:\w+\s+)?killed", t)
    if m:
        rep["killed"] = first_int(m.group(1)) if first_int(m.group(1)) is not None else None
    m = re.search(r"(?i)(\d[\d,]*|[a-z]+)\s+(?:others?\s+|people\s+|more\s+)?(?:are\s+|were\s+)?(?:\w+\s+)?(?:injured|wounded)", t)
    if m and rep["killed"] is not None or m and re.search(r"(?i)\binjur|wound", t):
        v = first_int(m.group(1)) if m else None
        rep["injured"] = v
    m = re.search(r"(?i)(\d[\d,]*|[a-z]+)\s+(?:others?\s+|people\s+)?(?:are\s+|were\s+)?(?:reported\s+)?missing", t)
    if m:
        rep["missing"] = first_int(m.group(1))
    m = re.search(r"(?i)(?:arrest|detain)\w*\s+(\d+|[a-z]+)\b", t)
    if m and first_int(m.group(1)) is not None and m.group(1).lower() in NUMWORDS or (m and m.group(1).isdigit()):
        rep["arrest_count"] = first_int(m.group(1))
    if re.search(r"(?i)\bone person is killed\b|\ba (?:man|woman|child|person|palestinian|soldier)\b[^.]{0,40}\bis killed\b", t):
        rep["killed"] = 1
    return rep


CAT_EVENT_TYPE = {
    "Armed conflicts and attacks": ["armed-conflict"], "Disasters and accidents": ["disaster"],
    "Law and crime": ["law-and-crime"], "Politics and elections": ["politics"],
    "International relations": ["international-relations"], "Business and economy": ["economy"],
    "Health and environment": ["health-and-environment"], "Science and technology": ["science-and-technology"],
    "Arts and culture": ["arts-and-culture"], "Sports": ["sports"],
}


PORTAL_CATS = ["Armed conflicts and attacks", "Arts and culture", "Business and economy", "Disasters and accidents",
               "Health and environment", "International relations", "Law and crime", "Politics and elections",
               "Science and technology", "Sports"]
CAT_RULES = [
    (r"\bsports?\b", "Sports"), (r"arts|culture", "Arts and culture"), (r"migration", "Politics and elections"),
    (r"disaster|accident|emergenc|humanitarian", "Disasters and accidents"),
    (r"cyber|science|technolog", "Science and technology"), (r"health", "Health and environment"),
    (r"international|diplom|geopolit", "International relations"),
    (r"armed|military|defen|terror|security", "Armed conflicts and attacks"),
    (r"crime|law|court|justice", "Law and crime"),
    (r"econom|business|market|trade|energy|transport", "Business and economy"),
    (r"politic|election|govern|policy|unrest|protest|social|labor|civil liberties", "Politics and elections"),
]


def canon_category(c):
    for pc in PORTAL_CATS:
        if c.strip().lower() == pc.lower():
            return pc
    for pat, pc in CAT_RULES:
        if re.search(pat, c, re.I):
            return pc
    return c


def portal_event_record(pe, date):
    text = pe["text"]
    topics = list(pe["topics"])
    countries = countries_in(text)
    rep = portal_casualties(text)
    outlets = [c["outlet"] for c in pe["cites"] if c["outlet"]]
    etype = list(CAT_EVENT_TYPE.get(pe["category"], [kebab(pe["category"] or "event")]))
    low = text.lower()
    for kw, et in (("airstrike", "airstrike"), ("drone", "drone-strike"), ("missile", "missile-strike"),
                   ("shooting", "shooting"), ("bomb", "bombing"), ("crash", "crash"), ("collide", "collision"),
                   ("earthquake", "earthquake"), ("flood", "flood"), ("fire", "fire"), ("election", "election"),
                   ("arrest", "arrest"), ("sentenced", "sentencing"), ("protest", "protest"), ("sanction", "sanctions"),
                   ("tariff", "tariffs"), ("capsiz", "maritime-accident"), ("avalanche", "avalanche"), ("storm", "storm"),
                   ("resign", "resignation"), ("dies", "death"), ("wins", "competition-result")):
        if kw in low and et not in etype:
            etype.append(et)
    return {
        "category": pe["category"] or "Uncategorized",
        "subcategory": topics[-1] if topics else "",
        "headline": None, "summary": text, "what_happened": [text], "why_it_matters": [], "uncertainty_notes": [],
        "actors": {"primary": [], "secondary": []},
        "entities": {"people": [], "organizations": [], "states": list(countries)},
        "geography": {"countries": list(countries), "places": [], "coordinates": []},
        "casualty_report": rep, "key_data": [], "sources": [], "summary_refs": [],
        "topics": topics, "event_type": etype, "tags": [kebab(t) for t in topics][:6],
        "portal_outlets": outlets,
    }


# ---------------------------------------------------------------- main assembly

def deep_merge(base, patch):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict) and not k.startswith("="):
            deep_merge(base[k], v)
        else:
            base[k.lstrip("=")] = copy.deepcopy(v)
    return base


def md_path_for(date):
    report = inputs.selection(date).get("report")
    return inputs.resolve(report) if report else None


def git_added_date(path):
    try:
        out = subprocess.run(["git", "-C", str(REPO), "log", "--diff-filter=A", "--format=%ad", "--date=short", "--",
                              str(path.relative_to(REPO)).replace("\\", "/")], capture_output=True, text=True).stdout.split()
        return out[-1] if out else None
    except Exception:
        return None


def build(date, report_only=False):
    selected = inputs.selection(date)
    if selected["mode"] == "authored_snapshot":
        if report_only:
            print(f"{date}: replay authored snapshot from {selected['source_commit']} "
                  f"with {selected['report']}; historical positional overlays are inactive")
            return None
        doc = yaml.safe_load(inputs.resolve(selected["snapshot"]).read_bytes())
        if doc["date"] != date:
            raise ValueError(f"Snapshot date mismatch: {date}")
        correction = corrections.path(date)
        records = json.loads(correction.read_text(encoding="utf-8")) if correction.exists() else []
        return corrections.apply(doc, selected, records)
    overlay_path = OVERLAYS / f"{date}.json"
    ov = json.loads(overlay_path.read_text(encoding="utf-8")) if overlay_path.exists() else {}
    meta, portal = wikiportal.parse(date)
    if selected.get("portal_sha256") and meta["sha256"] != selected["portal_sha256"]:
        raise ValueError(f"Pinned portal source drift for {date}")
    if overlay_path.exists() and not all(k in selected for k in ("portal_sha256", "portal_items_sha256", "overlay_sha256")):
        raise ValueError(f"Positional overlay for {date} has no source/interpretation guards")
    if ov.get("drop_portal"):
        raise ValueError("Portal events cannot be silently excluded by a synthesis overlay")
    mdp = md_path_for(date)
    md = parse_md(mdp) if mdp else None
    if "portal_items_sha256" in selected:
        import hashlib
        digest = hashlib.sha256(json.dumps(portal, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        if digest != selected["portal_items_sha256"]:
            raise ValueError(f"Portal interpretation drift for {date}; positional overlay requires review")
    if "report_events_sha256" in selected:
        import hashlib
        digest = hashlib.sha256(json.dumps(md["events"], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        if digest != selected["report_events_sha256"]:
            raise ValueError(f"Research event interpretation drift for {date}; positional overlay requires review")
    if "overlay_sha256" in selected and inputs.digest(overlay_path, text=True) != selected["overlay_sha256"]:
        raise ValueError(f"Overlay drift for {date}; update its guarded identity explicitly")
    mode = ov.get("mode") or ("md" if md and md["events"] else "legacy")
    accessed_default = git_added_date(mdp) if mdp else date

    records = []
    if mode == "md":
        for f in md["events"]:
            records.append(md_event_to_record(f, date))
        works = {k: dict(v) for k, v in md["works"].items()}
        if ov.get("legacy_extra"):
            leg = legacy_doc(date)
            for k in ov["legacy_extra"]:
                rec = legacy_event_to_record(leg["events"][k], date)
                rec["legacy_notes"] = (rec["legacy_notes"] + " " if rec["legacy_notes"] else "") + \
                    "Carried forward from the earlier schema-2.1 expansion (commit 0f5cbef6); not in the deep-research report."
                records.append(rec)
    else:
        leg = legacy_doc(date)
        for e in leg["events"]:
            records.append(legacy_event_to_record(e, date))
        works = {k: dict(v) for k, v in (md["works"] if md else {}).items()}
    for i, r in enumerate(records):
        r["kind"] = "md"
        r["midx"] = i
    drop = set(ov.get("drop_md") or [])
    records = [r for r in records if r["midx"] not in drop]
    pos_of = {r["midx"]: i for i, r in enumerate(records)}
    for w in works.values():
        w["accessed"] = w.get("accessed") or accessed_default

    # ---- match deep-research events to portal bullets
    forced = {pos_of[int(k)]: v for k, v in (ov.get("match") or {}).items() if int(k) in pos_of}
    scores = []
    for i, r in enumerate(records):
        txt = " ".join([r["headline"], r["summary"], " ".join(r["what_happened"])])
        for j, pe in enumerate(portal):
            scores.append((similarity(txt, pe["text"]), i, j))
    scores.sort(reverse=True)
    match = {}
    used = set()
    for i, j in forced.items():
        match[i] = j
        if j is not None:
            used.add(j)
    for sc, i, j in scores:
        if sc < 0.75 or i in match or j in used:
            continue
        match[i] = j
        used.add(j)
    near = {}
    for sc, i, j in scores:
        if j not in used and sc >= 0.55:
            near.setdefault(j, (sc, i))

    if report_only:
        print(f"== {date}  mode={mode}  md_events={len(records)}  portal={len(portal)}  works={len(works)}")
        for i, r in enumerate(records):
            j = match.get(i)
            best = max(((sc, jj) for sc, ii, jj in scores if ii == i), default=(0, None))
            print(f"  md[{r['midx']}] {r['headline'][:80]}")
            print(f"        -> {('p[%d] ' % j + portal[j]['text'][:90]) if j is not None else 'NO MATCH'}   (best p[{best[1]}] {best[0]:.2f})")
        print("  portal-only:")
        for j, pe in enumerate(portal):
            if j not in used:
                n = near.get(j)
                print(f"   p[{j}] {pe['category']} | {' > '.join(pe['topics'])[:50]} || {pe['text'][:120]}" + (f"  ~md[{n[1]}] {n[0]:.2f}" if n else ""))
        return None

    for i, r in enumerate(records):
        j = match.get(i)
        r["portal"] = portal[j] if j is not None else None
    portal_only = []
    for j, pe in enumerate(portal):
        if j in used or j in (ov.get("drop_portal") or []):
            continue
        r = portal_event_record(pe, date)
        r["kind"] = "portal"
        r["pidx"] = j
        r["portal"] = pe
        r["near_md"] = near.get(j, (0, None))[1]
        portal_only.append(r)

    # ---- works cited: url -> id
    by_url = {norm_url(w["url"]).lower(): n for n, w in works.items()}
    next_id = (max(works) if works else 0) + 1

    def work_id_for(src):
        nonlocal next_id
        key = norm_url(src["url"]).lower()
        if key in by_url:
            return by_url[key]
        title = title_from_url(src["url"]) or f"{src['outlet']} report"
        works[next_id] = {"id": next_id, "title": title, "outlet": src["outlet"], "url": src["url"],
                          "accessed": src["publication_date"] if src["publication_date"] <= FETCHED else accessed_default}
        by_url[key] = next_id
        next_id += 1
        return next_id - 1

    all_records = records + portal_only
    for r in records:
        for s in r["sources"]:
            refs = [x for x in s["refs"] if x in works]
            wid = work_id_for(s)
            if wid not in refs:
                refs = [wid] + refs if not refs else refs
            s["citation_refs"] = sorted(set(refs))
    portal_id = next_id
    portal_url = f"https://en.wikipedia.org/w/index.php?title={meta['title'].replace(' ', '_')}&oldid={meta['revid']}"

    # ---- events
    events = []
    ov_events = ov.get("events") or {}
    for n, r in enumerate(all_records, 1):
        eid = f"evt-{date}-{n:03d}"
        r["id"] = eid
    for r in all_records:
        key = f"md:{r['midx']}" if r["kind"] == "md" else f"p:{r['pidx']}"
        pe = r["portal"]
        if r["kind"] == "md":
            topics = list(r.get("legacy_topics") or [])
            if pe:
                topics = topics + [t for t in pe["topics"] if t not in topics]
            for t in [r["subcategory"]] + r["geography"]["countries"][:2]:
                if t and t not in topics:
                    topics.append(t)
            n_hi = sum(1 for s in r["sources"] if s["reliability_tier"] == "high")
            killed = r["casualty_report"].get("killed") or 0
            imp = r.get("legacy_importance")
            if not isinstance(imp, int):
                imp = 6
                if r["category"].lower().startswith(("armed", "war", "military", "conflict")) or killed >= 20:
                    imp = 7
                if killed >= 100:
                    imp = 8
            etype = r.get("legacy_event_type") or ([kebab(r["subcategory"])] if r["subcategory"] else []) or \
                list(CAT_EVENT_TYPE.get(r["category"], [kebab(r["category"])]))
            tags = r.get("legacy_tags") or [kebab(t) for t in topics][:6]
            unc = list(r["uncertainty_notes"])
            if pe:
                pk = portal_casualties(pe["text"]).get("killed")
                mk = r["casualty_report"].get("killed")
                if pk is not None and mk is not None and pk != mk:
                    unc.append(f"The Wikipedia portal bullet reports {pk} killed; the deep-research report records {mk}.")
            lc = r.get("legacy_confidence") or {}
            conf = {
                "event_existence": lc.get("event_existence") if lc.get("event_existence") in ("high", "medium", "low") else ("high" if pe or n_hi >= 1 else "medium"),
                "detail_accuracy": lc.get("detail_accuracy") if lc.get("detail_accuracy") in ("high", "medium", "low") else ("high" if n_hi >= 2 and not unc else "medium"),
                "actor_identification": lc.get("actor_identification") if lc.get("actor_identification") in ("high", "medium", "low") else "high",
            }
            lt = r.get("legacy_time") or {}
            time = {"date": date, "time_known": bool(lt.get("time_known") and lt.get("time_detail")), "ongoing": bool(lt.get("ongoing", r["category"].lower().startswith("armed")))}
            if time["time_known"]:
                time = {"date": date, "time_known": True, "time_detail": str(lt["time_detail"]), "ongoing": time["ongoing"]}
            srcs = []
            for k, s in enumerate(r["sources"]):
                srcs.append({"id": f"src-{int(r['id'][-3:]):03d}-{chr(97 + k) if k < 26 else 'z' + str(k)}", "outlet": s["outlet"], "url": s["url"],
                             "publication_date": s["publication_date"], "source_type": s["source_type"],
                             "reliability_tier": s["reliability_tier"], "supports": s["supports"],
                             "contradicts": s["contradicts"], "quoted_material": s["quoted_material"],
                             "citation_refs": s["citation_refs"]})
            kd = [{"label": k["label"], "value": k["value"], "citation_refs": k["refs"] or (srcs[0]["citation_refs"][:1] if srcs else [portal_id])} for k in r["key_data"]]
            note_bits = []
            if r.get("legacy_notes"):
                note_bits.append(r["legacy_notes"])
            ev = {
                "id": r["id"], "category": pe["category"] if pe and pe["category"] else canon_category(r["category"]),
                "subcategory": r["subcategory"], "topics": topics,
                "importance": imp, "headline": r["headline"], "summary": r["summary"], "key_data": kd,
                "details": {"what_happened": r["what_happened"], "why_it_matters": r["why_it_matters"], "uncertainty_notes": unc},
                "actors": r["actors"], "entities": r["entities"], "geography": r["geography"], "time": time,
                "casualty_report": r["casualty_report"],
                "classification": {"event_type": etype, "tags": tags},
                "sources": {"wikipedia_portal": {"included": bool(pe), "text_fragment": pe["text"] if pe else None}, "external": srcs},
                "provenance": {"extracted_from_portal_bullet": bool(pe), "enriched_manually": True, "last_reviewed_by": None},
                "confidence": conf, "related_events": [],
                "notes": " ".join(note_bits),
            }
        else:
            outlets = r["portal_outlets"]
            killed = r["casualty_report"].get("killed") or 0
            imp = 4
            if r["category"].startswith("Armed") or killed >= 5:
                imp = 5
            if killed >= 20:
                imp = 6
            ev = {
                "id": r["id"], "category": r["category"], "subcategory": r["subcategory"], "topics": r["topics"],
                "importance": imp, "headline": r["headline"] or r["summary"][:100], "summary": r["summary"], "key_data": [],
                "details": {"what_happened": r["what_happened"], "why_it_matters": [], "uncertainty_notes": []},
                "actors": r["actors"], "entities": r["entities"], "geography": r["geography"],
                "time": {"date": date, "time_known": False, "ongoing": r["category"].startswith("Armed")},
                "casualty_report": r["casualty_report"],
                "classification": {"event_type": r["event_type"], "tags": r["tags"]},
                "sources": {"wikipedia_portal": {"included": True, "text_fragment": r["summary"]}, "external": []},
                "provenance": {"extracted_from_portal_bullet": True, "enriched_manually": False, "last_reviewed_by": None},
                "confidence": {"event_existence": "high", "detail_accuracy": "medium", "actor_identification": "medium"},
                "related_events": [],
                "notes": "Portal-derived event with no deep-research coverage; reported by "
                         + (" and ".join(outlets) if outlets else "an outlet cited") + " per the Wikipedia portal.",
            }
            if r["near_md"] is not None:
                other = records[r["near_md"]]["id"]
                ev["related_events"].append(other)
        patch = ov_events.get(key)
        if patch:
            deep_merge(ev, patch)
        sh = (ov.get("ev") or {}).get(key) or {}
        if "h" in sh:
            ev["headline"] = sh["h"]
        if "i" in sh:
            ev["importance"] = sh["i"]
        if "sub" in sh:
            ev["subcategory"] = sh["sub"]
        if "cat" in sh:
            ev["category"] = sh["cat"]
        for k_short, k_full in (("k", "killed"), ("w", "injured"), ("m", "missing"), ("a", "arrest_count"), ("d", "displaced")):
            if k_short in sh:
                ev["casualty_report"][k_full] = sh[k_short]
        if "dmg" in sh:
            ev["casualty_report"]["damage"] = sh["dmg"]
        if "pl" in sh:
            ev["geography"]["places"] = sh["pl"] + [p for p in ev["geography"]["places"] if p not in sh["pl"]]
        for c in sh.get("st", []):
            if c not in ev["entities"]["states"]:
                ev["entities"]["states"].append(c)
            if c not in ev["geography"]["countries"]:
                ev["geography"]["countries"].append(c)
        known = {o["name"] for o in ev["entities"]["organizations"]}
        for n, dsc in (sh.get("org") or {}).items():
            if n not in known:
                ev["entities"]["organizations"].append({"name": n, "description": dsc})
        knownp = {p["name"] for p in ev["entities"]["people"]}
        for n, rl in (sh.get("ppl") or {}).items():
            if n not in knownp:
                ev["entities"]["people"].append({"name": n, "role": rl})
        if "act" in sh:
            ev["actors"]["primary"] = sh["act"]
        if "act2" in sh:
            ev["actors"]["secondary"] = sh["act2"]
        if "tags" in sh:
            ev["classification"]["tags"] = sh["tags"]
        if "et" in sh:
            ev["classification"]["event_type"] = sh["et"]
        if "unc" in sh:
            ev["details"]["uncertainty_notes"] = ev["details"]["uncertainty_notes"] + sh["unc"]
        if "conf" in sh:
            ev["confidence"].update(sh["conf"])
        if "note" in sh:
            ev["notes"] = (ev["notes"] + " " + sh["note"]).strip()
        if "ongoing" in sh:
            ev["time"]["ongoing"] = sh["ongoing"]
        if "why" in sh:
            ev["details"]["why_it_matters"] = sh["why"]
        if "topics" in sh:
            ev["topics"] = sh["topics"] + [t for t in ev["topics"] if t not in sh["topics"]]
        if not ev["actors"]["primary"] and not ev["actors"]["secondary"]:
            ev["actors"]["primary"] = [p["name"] for p in ev["entities"]["people"]] + [o["name"] for o in ev["entities"]["organizations"]]
        if key in (ov.get("importance") or {}):
            ev["importance"] = ov["importance"][key]
        if key in (ov.get("headlines") or {}):
            ev["headline"] = ov["headlines"][key]
        as_org = set(ROLES.get("__as_org__", []))
        moved = [p for p in ev["entities"]["people"] if p["name"] in as_org]
        ev["entities"]["people"] = [p for p in ev["entities"]["people"] if p["name"] not in as_org]
        ev["entities"]["organizations"] += [{"name": p["name"], "description": p["role"]} for p in moved]
        ctx = " ".join([ev["summary"]] + ev["details"]["what_happened"] + ev["details"]["why_it_matters"])
        for p in ev["entities"]["people"]:
            if not p["role"] and p["name"] in ROLES:
                p["role"] = ROLES[p["name"]]
            if not p["role"]:
                p["role"] = entities.role_from_context(p["name"], ctx)
            p["role"] = entities.fix_role(p["role"])
        for o in ev["entities"]["organizations"]:
            if not o["description"] and o["name"] in ROLES:
                o["description"] = ROLES[o["name"]]
        if ev["time"].get("time_known") and "time_detail" not in ev["time"]:
            ev["time"]["time_known"] = False
        if not ev["time"].get("time_known"):
            ev["time"].pop("time_detail", None)
        events.append(ev)
    # overlay-declared relations, keyed "md:i" / "p:j"
    key_to_id = {}
    for r in all_records:
        key_to_id[f"md:{r['midx']}" if r["kind"] == "md" else f"p:{r['pidx']}"] = r["id"]
    idx = {e["id"]: e for e in events}
    for r in records:
        if r.get("portal") is not None:
            key_to_id[f"p:{portal.index(r['portal'])}"] = r["id"]
    for group in ov.get("related") or []:
        ids = [key_to_id[k] for k in group if k in key_to_id]
        for a in ids:
            for b in ids:
                if a != b and b not in idx[a]["related_events"]:
                    idx[a]["related_events"].append(b)
    # symmetric related_events
    for e in events:
        for o in list(e["related_events"]):
            if o in idx and e["id"] not in idx[o]["related_events"]:
                idx[o]["related_events"].append(e["id"])
    for e in events:
        e["related_events"] = sorted(set(e["related_events"]))
    # portal key_data refs placeholder -> portal id
    works_list = [works[k] for k in sorted(works)]
    works_list.append({"id": portal_id, "title": meta["title"], "outlet": "Wikipedia", "url": portal_url, "accessed": FETCHED})

    overview = ov.get("analytical_overview") or ("\n\n".join(md["intro"][:2]) if md and md["intro"] else "")
    conclusion = ov.get("strategic_conclusion") or ("\n\n".join(md["outro"][:2]) if md and md["outro"] else
                                                     (md["intro"][-1] if mode == "legacy" and md and len(md["intro"]) > 2 else ""))
    rel_md = str(mdp.relative_to(REPO)).replace("\\", "/") if mdp else None
    seed_rel = f"{date[:4]}/{date[5:7]}/{date}.yaml"
    seed_source = f"{meta['title']} (revision {meta['revid']}; seed {seed_rel})"
    if rel_md:
        seed_source += f" + deep-research report {rel_md}"
    if mode == "legacy":
        seed_source += " + schema-2.1 expansion from commit 0f5cbef6"
    doc = {
        "date": date,
        "source_page": {"portal": meta["title"], "language": "en", "wikipedia_revision_id": meta["revid"]},
        "dataset": {"schema_version": "2.2",
                    "compiler": {"mode": "llm_deep_research_broad_snapshot", "status": "draft", "reviewed": False},
                    "scope": {"seed_source": seed_source, "enrichment_sources_expected": True}},
        "editorial_policy": {"summary_style": "factual", "allow_inference": False, "require_source_support": True},
        "analytical_overview": overview,
        "events": events,
        "strategic_conclusion": conclusion,
        "works_cited": works_list,
    }
    references.reconcile(doc, FETCHED)
    return doc


# ---------------------------------------------------------------- emitter

def q(s):
    return json.dumps(s, ensure_ascii=False)


def scalar(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        return str(v)
    return q(str(v))


FOLDED = {"summary", "analytical_overview", "strategic_conclusion"}


def folded(text, indent):
    pad = " " * indent
    paras = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    lines = []
    for i, p in enumerate(paras):
        if i:
            lines.append("")
        for ln in textwrap.wrap(" ".join(p.split()), width=max(40, 92 - indent), break_long_words=False, break_on_hyphens=False):
            lines.append(pad + ln)
    return lines


def emit(obj, indent=0, key=None):
    pad = " " * indent
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FOLDED and isinstance(v, str) and v.strip() and "\n" not in v.strip()[:0]:
                out.append(f"{pad}{k}: >")
                out.extend(folded(v, indent + 2))
            elif isinstance(v, dict):
                if not v:
                    out.append(f"{pad}{k}: {{}}")
                else:
                    out.append(f"{pad}{k}:")
                    out.extend(emit(v, indent + 2, k))
            elif isinstance(v, list):
                if not v:
                    out.append(f"{pad}{k}: []")
                elif all(isinstance(x, int) and not isinstance(x, bool) for x in v):
                    out.append(f"{pad}{k}: [{', '.join(str(x) for x in v)}]")
                else:
                    out.append(f"{pad}{k}:")
                    out.extend(emit(v, indent + 2, k))
            else:
                out.append(f"{pad}{k}: {scalar(v)}")
            if indent == 0 and k in ("editorial_policy", "analytical_overview", "events", "strategic_conclusion"):
                out.append("")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                sub = emit(item, indent + 2)
                first = sub[0]
                out.append(f"{pad}- {first.lstrip()}")
                out.extend(sub[1:])
            else:
                out.append(f"{pad}- {scalar(item)}")
    return out


def dump(doc):
    return "\n".join(emit(doc)).rstrip("\n") + "\n"


def write(date):
    doc = build(date)
    selected = inputs.selection(date)
    if selected["mode"] == "authored_snapshot" and not corrections.path(date).exists():
        text = inputs.resolve(selected["snapshot"]).read_bytes().decode("utf-8")
    else:
        text = dump(doc)
    import importlib.util
    spec = importlib.util.spec_from_file_location("expansion_validator", REPO / "reference/schema/validate.py")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    errors = validator.schema_errors(doc) + validator.cross_ref_errors(doc)
    if errors:
        raise ValueError(f"{date}: invalid synthesis: {errors}")
    back = yaml.safe_load(text)
    norm = json.loads(json.dumps(doc))
    for k in ("analytical_overview", "strategic_conclusion"):
        back[k] = " ".join(str(back[k]).split())
        norm[k] = " ".join(str(norm[k]).split())
    for e1, e2 in zip(back["events"], norm["events"]):
        e1["summary"] = " ".join(e1["summary"].split())
        e2["summary"] = " ".join(e2["summary"].split())
    if back != norm:
        raise SystemExit(f"{date}: YAML round-trip mismatch")
    p = OUT / date[:4] / date[5:7] / f"{date}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def todo(date):
    doc = build(date)
    miss = {}
    for e in doc["events"]:
        for p in e["entities"]["people"]:
            if not p["role"]:
                miss.setdefault(p["name"], "person")
        for o in e["entities"]["organizations"]:
            if not o["description"]:
                miss.setdefault(o["name"], "org")
    print(f"== {date} missing roles/descriptions: {len(miss)}")
    for k, v in miss.items():
        print(f"  {v}: {k}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--todo":
        for d in args[1:]:
            todo(d)
    elif args and args[0] == "--report":
        for d in args[1:]:
            build(d, report_only=True)
    else:
        for d in args:
            print(write(d))
