"""Paths and constants. Everything lives under the AudienceOS folder on this Mac."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("AUDIENCEOS_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = Path(os.environ.get("AUDIENCEOS_DATA", ROOT / "data"))
DB_PATH = DATA_DIR / "audienceos.db"
UPLOADS_DIR = DATA_DIR / "uploads"
MEDIA_DIR = DATA_DIR / "media"
REPORTS_DIR = DATA_DIR / "reports"
EXPORTS_DIR = DATA_DIR / "exports"
BACKUPS_DIR = DATA_DIR / "backups"
LOGS_DIR = DATA_DIR / "logs"
RUNTIME_DIR = ROOT / "runtime"
WHISPER_DIR = RUNTIME_DIR / "whisper"
FRONTEND_DIST = ROOT / "frontend" / "dist"
FIXTURES_DIR = ROOT / "fixtures"

HOST = "127.0.0.1"
PORT = int(os.environ.get("AUDIENCEOS_PORT", "8760"))
OLLAMA_URL = os.environ.get("AUDIENCEOS_OLLAMA_URL", "http://127.0.0.1:11434")

# Resource limits
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024        # 1 GB per file (video)
MAX_PAGE_BYTES = 15 * 1024 * 1024            # 15 MB per fetched web page
MAX_MEDIA_DOWNLOAD_BYTES = 300 * 1024 * 1024 # 300 MB podcast enclosure
MAX_TEXT_CHARS_PER_ITEM = 400_000
MAX_FRAMES_PER_VIDEO = 6
FETCH_TIMEOUT_S = 20
KEYCHAIN_SERVICE = "AudienceOS"

for d in (DATA_DIR, UPLOADS_DIR, MEDIA_DIR, REPORTS_DIR, EXPORTS_DIR, BACKUPS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)
