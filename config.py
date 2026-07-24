import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

DB_PATH = Path(os.environ.get("KAPA_DB_PATH", BASE_DIR / "kapa.db"))
HOST = os.environ.get("KAPA_HOST", "0.0.0.0")
PORT = int(os.environ.get("KAPA_PORT", "5050"))
DEBUG = os.environ.get("KAPA_DEBUG", "False").lower() in ("1", "true", "yes")
SECRET_KEY = os.environ.get("KAPA_SECRET_KEY", "kapa-dev-key-change-in-production")
LOG_FILE = Path(os.environ.get("KAPA_LOG_FILE", BASE_DIR / "kapa.log"))
LOG_LEVEL = os.environ.get("KAPA_LOG_LEVEL", "INFO")

BACKUP_DIR = Path(os.environ.get("KAPA_BACKUP_DIR", BASE_DIR / "backups"))
BACKUP_MAX_COUNT = int(os.environ.get("KAPA_BACKUP_MAX", "10"))

RATE_LIMIT_REQUESTS = int(os.environ.get("KAPA_RATE_LIMIT", "60"))
RATE_LIMIT_WINDOW = int(os.environ.get("KAPA_RATE_WINDOW", "60"))

GOOGLE_COLORS = [
    "#039be5",
    "#33b679",
    "#f4511e",
    "#7986cb",
    "#e67c73",
    "#8e24aa",
    "#f6bf26",
    "#0b8043",
    "#d50000",
    "#3f51b5",
    "#616161",
]

TEAM_MEMBERS_SEED = [
    n.strip()
    for n in os.environ.get(
        "KAPA_TEAM_SEED", "Dominic Meier,Tony Freudenthal"
    ).split(",")
    if n.strip()
]

SQLITE_RETRY_MAX = int(os.environ.get("KAPA_SQLITE_RETRY", "5"))
SQLITE_RETRY_BACKOFF = float(os.environ.get("KAPA_SQLITE_BACKOFF", "0.1"))
