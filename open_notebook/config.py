import os
from typing import MutableMapping

# ROOT DATA FOLDER
DATA_FOLDER = "./data"

# LANGGRAPH CHECKPOINT FILE
sqlite_folder = f"{DATA_FOLDER}/sqlite-db"
os.makedirs(sqlite_folder, exist_ok=True)
LANGGRAPH_CHECKPOINT_FILE = f"{sqlite_folder}/checkpoints.sqlite"

# UPLOADS FOLDER
UPLOADS_FOLDER = f"{DATA_FOLDER}/uploads"
os.makedirs(UPLOADS_FOLDER, exist_ok=True)

# PODCASTS FOLDER
# Matches the root that build_episode_output_dir() (commands/podcast_commands.py)
# creates episode directories under when called with DATA_FOLDER in production.
PODCASTS_FOLDER = f"{DATA_FOLDER}/podcasts"
os.makedirs(PODCASTS_FOLDER, exist_ok=True)

# TIKTOKEN CACHE FOLDER
# Reads TIKTOKEN_CACHE_DIR from the environment so Docker can redirect the cache
# to a path outside /data/ (which is typically volume-mounted and would hide the
# pre-baked encoding baked into the image at build time).
TIKTOKEN_CACHE_DIR = (
    os.environ.get("TIKTOKEN_CACHE_DIR", "").strip() or f"{DATA_FOLDER}/tiktoken-cache"
)
os.makedirs(TIKTOKEN_CACHE_DIR, exist_ok=True)

# LLM TIMEOUT
# Since esperanto 2.28, to_langchain() enforces ESPERANTO_LLM_TIMEOUT on every
# provider (default 60 s; before, most providers used their SDK default and
# Ollama waited forever). 60 s cuts off long answers and slow local models, so
# MCIT AI defaults it to 180 s, well below the web UI's 600 s request
# timeout (NEXT_PUBLIC_API_TIMEOUT_MS). An explicit value always wins. Both the API and
# the worker import this module before any model is created.
DEFAULT_LLM_TIMEOUT_SECONDS = 180


def ensure_llm_timeout_default(environ: MutableMapping[str, str] = os.environ) -> None:
    """Set ESPERANTO_LLM_TIMEOUT to MCIT AI's default when unset or blank."""
    if not environ.get("ESPERANTO_LLM_TIMEOUT", "").strip():
        environ["ESPERANTO_LLM_TIMEOUT"] = str(DEFAULT_LLM_TIMEOUT_SECONDS)


ensure_llm_timeout_default()

# =============================================================================
# CENTRALIZED DEPLOYMENT SETTINGS (single source of truth)
# -----------------------------------------------------------------------------
# Capacity numbers, service addresses and model names/configurations that
# used to be scattered as literals across api/ and open_notebook/ live here,
# each overridable from the environment (documented in .env.example). Modules
# must import these instead of repeating "http://localhost:<port>" or a
# model name, so a deployment change is one .env edit, not a code hunt.
# =============================================================================


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


# --- Service addresses -------------------------------------------------------
# PUBLIC_URL: address users open in the browser (shared login, OIDC, MCP).
PUBLIC_URL = _env_str("MCIT_PUBLIC_URL", "http://localhost:8502")
# INTERNAL_API_URL: how server-side components reach this API.
INTERNAL_API_URL = _env_str("MCIT_INTERNAL_API_URL", "http://localhost:5055")
# AGENT_URL: TuT Agent web UI (file downloads, agent redirects).
AGENT_URL = _env_str("TUT_AGENT_PUBLIC_URL", "http://localhost:3210")
# OLLAMA_BASE_URL: local model server (chat + embeddings).
OLLAMA_BASE_URL = _env_str("OLLAMA_API_BASE", "http://localhost:11434")
# OMLX_BASE_URL: local OpenAI-compatible model server (Apple Silicon builds).
OMLX_BASE_URL = _env_str("OMLX_API_BASE", "http://localhost:11435/v1")
# STORAGE_PUBLIC_URL: browser-reachable TuT Agent file storage (S3).
STORAGE_PUBLIC_URL = _env_str("TUT_S3_PUBLIC_URL", "http://localhost:9000")
# SURREAL_ADDRESS: SurrealDB host (port is fixed by the database client).
SURREAL_ADDRESS = _env_str("SURREAL_ADDRESS", "localhost")

# --- Model names / configurations -------------------------------------------
OLLAMA_CHAT_MODEL = _env_str("OLLAMA_CHAT_MODEL", "qwen2.5:7b")
OLLAMA_EMBEDDING_MODEL = _env_str("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
# Context size above which model provisioning switches to large_context_model.
LARGE_CONTEXT_THRESHOLD_TOKENS = _env_int(
    "OPEN_NOTEBOOK_LARGE_CONTEXT_THRESHOLD", 105_000
)

# --- Capacity numbers --------------------------------------------------------
# Default upload cap, in MB. None means NO cap: uploads of any size are
# accepted (the default). api.middleware.get_max_upload_size_bytes() re-reads
# OPEN_NOTEBOOK_MAX_UPLOAD_SIZE_MB on every call, so a positive number there
# caps uploads, while a blank, zero, negative or malformed value means no cap.
DEFAULT_MAX_UPLOAD_SIZE_MB = None
# Largest document the office viewer may save back, in MB.
OFFICE_MAX_SAVE_MB = _env_int("OPEN_NOTEBOOK_OFFICE_MAX_SAVE_MB", 100)
# How long an office-viewer ticket stays valid, in hours.
OFFICE_TICKET_HOURS = _env_int("OPEN_NOTEBOOK_OFFICE_TICKET_HOURS", 4)
# Bytes streamed per read while saving an uploaded file, so a huge upload
# never has to sit whole in memory.
UPLOAD_STREAM_CHUNK_BYTES = _env_int(
    "OPEN_NOTEBOOK_UPLOAD_STREAM_CHUNK_BYTES", 1024 * 1024
)
