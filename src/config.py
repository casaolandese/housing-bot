"""Central configuration. Secrets come from the environment only."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv is optional on CI, where real env vars are injected
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SEEN_FILE = DATA_DIR / "seen_listings.json"

# --- Search scope -----------------------------------------------------------
# Kamernet slugs. Its search always includes a ~5km radius we cannot override
# via query params, so nearby towns are filtered client-side by CITY_ALLOWLIST.
CITIES = ["amsterdam", "utrecht"]

# Cities we accept. Kamernet's fixed radius pulls in commuter towns; these are
# all within a short train/metro ride of Amsterdam or Utrecht, which the brief
# explicitly asked to include.
CITY_ALLOWLIST = {
    # Amsterdam metro
    "amsterdam", "amstelveen", "diemen", "duivendrecht", "badhoevedorp",
    "zaandam", "hoofddorp", "ouderkerk aan de amstel", "landsmeer", "weesp",
    "haarlem", "purmerend", "almere",
    # Utrecht metro
    "utrecht", "nieuwegein", "de meern", "maarssen", "zeist", "bilthoven",
    "houten", "vleuten", "bunnik", "ijsselstein", "driebergen", "amersfoort",
}

MAX_RENT = int(os.getenv("MAX_RENT", "900"))
MIN_SURFACE = 6           # m2; below this is almost always a mislabelled listing

# Move-in window: September / October 2026, plus anything available sooner
# (immediate move-in is always acceptable).
MOVE_IN_EARLIEST = "2026-08-01"
MOVE_IN_LATEST = "2026-10-31"

# Pages of results to pull per city per run. Default sort is roughly newest
# first, and we poll often, so a couple of pages comfortably covers new stock.
PAGES_PER_CITY = 3

# --- Eligibility ------------------------------------------------------------
# Reject only on positive evidence of exclusion. Unspecified => allowed.
FEMALE_ONLY_PATTERNS = [
    r"\bfemale[s]?\s*(only|preferred)\b", r"\bwomen\s*only\b", r"\bno\s+men\b",
    r"\bgirls?\s*only\b", r"\balleen\s+(een\s+)?vrouw", r"\balleen\s+meiden\b",
    r"\balleen\s+dames\b", r"\bvrouwen\s*only\b", r"\bvoor\s+vrouwen\b",
    r"\benkel\s+vrouwen\b", r"\bdameshuis\b", r"\bvrouwenhuis\b",
    r"\bgeen\s+mannen\b", r"\bmeisjeshuis\b",
]
NO_STUDENT_PATTERNS = [
    r"\bno\s+students\b", r"\bgeen\s+studenten\b", r"\bstudenten\s+niet\b",
    r"\bworking\s+(professionals?|people)\s+only\b", r"\balleen\s+werkenden\b",
    r"\bwerkende[n]?\s+only\b", r"\bnot\s+suitable\s+for\s+students\b",
]
# Listing types that are not a room to live in.
BANNED_TYPE_PATTERNS = [
    r"\bparking\b", r"\bparkeer", r"\bgarage\b", r"\bberging\b", r"\bstorage\b",
    r"\bchalet\b", r"\bstacaravan\b", r"\boffice\b", r"\bkantoor\b",
    r"\bgaragebox\b", r"\bwoonboot\b", r"\bligplaats\b",
]

# --- Email ------------------------------------------------------------------
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "")
ALERT_RECIPIENT_EMAIL = os.getenv("ALERT_RECIPIENT_EMAIL", "")

# At or below this many new listings, send one email each (fastest to act on).
# Above it, send a single digest so Gmail's rate limits are never tripped.
INDIVIDUAL_EMAIL_THRESHOLD = 4
# Hard ceiling on emails per run, protects against a runaway first run.
MAX_EMAILS_PER_RUN = 12

DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

# --- HTTP -------------------------------------------------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0",
]
REQUEST_TIMEOUT = 30
MAX_RETRIES = 4
BACKOFF_BASE = 1.6
