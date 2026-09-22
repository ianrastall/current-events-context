"""Actor-string cleanup, person/organization classification and role extraction."""
import re

TITLE = (r"(?:Acting |Interim |Former |Deputy |Vice |Prime |Chief |Senior |Supreme |Lt\.? |Lieutenant |Crown |Royal |House |"
         r"Opposition |Foreign |Defen[cs]e |Interior |Education |Finance |Justice |Energy |Trade |Health |Economy |"
         r"Attorney |Governor[- ]|U\.S\. |US |UK |EU |UN )*"
         r"(?:President|Prime Minister|Premier|Minister|Secretary(?: of State| General)?|Attorney General|Chancellor|King|"
         r"Queen|Prince|Emir|Commissioner|Speaker|Ambassador|Leader|Chair(?:man|woman)?|Gen\.|General|Gov\.|Governor|"
         r"Representative|Rep\.|Senator|Sen\.|Justice|Judge|Mayor|Spokes(?:person|man|woman)|Commander|Director|"
         r"Governor-General|Ayatollah|Pope|Patriarch|Envoy|CEO|Chief Executive|Coach|Captain|Prosecutor|Chief of Staff)")
TITLE_RE = re.compile(rf"^((?:[A-Z][\w.'’-]*\s+)*?{TITLE}(?:\s+of\s+[A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*)*)?)\s+([A-Z][\w.'’-]+(?:\s+(?:[A-Z][\w.'’-]*|de|da|del|van|von|bin|al|el|la|le|di|dos|das|y)){{1,4}})$")

ORG_HINT = re.compile(r"(?i)\b(ministry|police|forces?|army|party|council|agency|office|court|government|union|bank|"
                      r"commission|organi[sz]ation|department|group|company|corp\.?|inc\.?|plc|ltd|university|université|"
                      r"association|committee|league|movement|front|authority|services?|guard|news|network|institute|"
                      r"federation|programme|program|coalition|alliance|club|airlines?|airways|parliament|congress|senate|"
                      r"assembly|cabinet|military|navy|air force|corps|brigade|militia|cartel|gang|hamas|hezbollah|houthis?|"
                      r"taliban|isis|islamic state|al-shabaab|nato|united nations|opec|fbi|cia|dhs|doj|pentagon|"
                      r"white house|kremlin|board|fund|foundation|society|reserve|exchange|media|press|times|post|journal|"
                      r"tribunal|legislature|regime|administration|ngo|red cross|red crescent|imf|wto|iaea|irgc|idf|"
                      r"tatmadaw|junta|team|airport|hospital|school|church|mosque|temple|watch|international|intelligence|"
                      r"bet|research|customs|patrol|democrats|republicans|executives|penal|officials|authorities|"
                      r"protesters|residents|civilians|workers|miners|farmers|herders|villagers|inmates|families|"
                      r"communities|investors|markets|participants|operators|firms|states|governments|forces|"
                      r"shin bet|mossad|interpol|europol|olympic|paralympic|fifa|uefa|icc|cricket|wnba|nba|nfl|"
                      r"energies|petroleum|oil|gas|motors?|technologies|industries|holdings|systems|sistema|"
                      r"embassy|consulate|mission|secretariat|electorate|population|diaspora|survivors|"
                      r"sheriff|constabulary|gendarmerie|coast guard|navy|aerospace|defence|defense|lukoil|"
                      r"zarubezhneft|chevron|exxonmobil|conocophillips|shell|totalenergies|qatarenergy|aramco|"
                      r"grab|gojek|lineman|mandiant|ericsson|jawwal|ooredoo|sungrow|anduril|uber|motional|meta|"
                      r"xinhua|kcna|netblocks|hrana|infid|mercosur|g7|eurogroup|rescue|colectivos|naparamas|caucus|"
                      r"commissariat|directorate|bureau|chamber|house|panel|tribe|clan|protesters|demonstrators)\b")

DESCRIPTIVE = re.compile(r"(?i)^(none|various|unspecified|unidentified (?!gunman)|local |rescue/|officials reporting|"
                         r"global |public-sector|provincial |external |protest movements|anti-corruption officials|"
                         r"civilian institutions|participating |migrants aboard|u\.s\. officials pursuing|incident of|"
                         r"defense-industry|civil society/|jewish community|organized-crime|state broadcasters|"
                         r"migrant communities|human-rights and|recruited |national institutions|joint-statement|"
                         r"gulf exporting|shipping-data|israeli officials cited|u\.s\. officials cited|chinese policymakers|"
                         r"cuban security/|cuban higher|arizona election|kazakh electorate|defendants )")


PARTICLES = {"de", "da", "del", "der", "den", "ter", "van", "von", "bin", "bint", "ibn", "abu", "ben", "al", "el", "la",
             "le", "di", "dos", "das", "du", "y", "e"}
UPPER_TOKENS = {"us": "U.S.", "u.s.": "U.S.", "eu": "EU", "un": "UN", "uk": "UK", "uae": "UAE", "nato": "NATO",
                "ceo": "CEO", "fbi": "FBI", "irgc": "IRGC", "idf": "IDF", "unfccc": "UNFCCC", "who": "WHO", "imf": "IMF"}


def fix_role(r):
    if not r:
        return r
    words = r.split()
    out = [UPPER_TOKENS.get(w.lower(), w) if w.lower() in UPPER_TOKENS and not (w.lower() == "who" and i) else w
           for i, w in enumerate(words)]
    r = " ".join(out)
    return r[0].upper() + r[1:]


def clean_actor(a):
    a = a.strip()
    a = re.sub(r"\s+\d{1,3}(?:\s*,\s*\d{1,3})*$", "", a)       # trailing footnote refs
    a = re.split(r"\s+[–—]\s+", a)[0]                            # "X – launching crackdown"
    a = a.strip().rstrip(".;,").strip()
    a = re.sub(r"^(?:and|the)\s+(?=[A-Z])", "", a)
    return a


def split_title(name):
    m = TITLE_RE.match(name)
    if m and not ORG_HINT.search(m.group(2)):
        return m.group(2).strip(), m.group(1).strip()
    return name, ""


def classify(a, countries, aliases):
    """Return (kind, name, role) with kind in person/org/state/skip."""
    a = clean_actor(a)
    if not a or DESCRIPTIVE.search(a) or a[0].islower():
        return "skip", a, ""
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", a)
    name, paren = (m.group(1).strip(), m.group(2).strip()) if m else (a, "")
    base = aliases.get(name, name)
    if base in countries:
        return "state", base, paren
    pname, title = split_title(name)
    if title:
        return "person", pname, title + (f" ({paren})" if paren else "")
    if ORG_HINT.search(name):
        return "org", name, paren
    words = name.split()
    namey = all(w[:1].isupper() or w in PARTICLES or re.match(r"^(?:al|el|ad|as|ash|ibn|bin|abu|ben|de|d)[-'’][A-Z]", w)
                for w in words)
    if 2 <= len(words) <= 5 and namey and not re.search(r"\d", name):
        return "person", name, paren
    return "org", name, paren


def role_from_context(name, text):
    """Find a title/appositive for `name` in the event's own prose."""
    if not text or name not in text:
        return ""
    esc = re.escape(name)
    m = re.search(rf"((?:[A-Z][\w.'’-]*\s+|of\s+|the\s+){{0,5}}?{TITLE}(?:\s+of\s+(?:the\s+)?[A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*)*)?)\s+{esc}", text)
    if m:
        r = m.group(1).strip()
        r = re.sub(r"^(?:The|the|of)\s+", "", r)
        if 3 <= len(r) <= 80:
            return r[0].upper() + r[1:]
    m = re.search(rf"{esc},\s+(?:the\s+|a\s+|an\s+)?([^,;()]{{4,90}}?)(?:,|;|\.\s|\))", text)
    if m and re.search(TITLE, m.group(1), re.I | re.S) is not None and not re.match(r"(?i)(who|which|said|says|and)\b", m.group(1)):
        r = m.group(1).strip()
        return r[0].upper() + r[1:]
    return ""
