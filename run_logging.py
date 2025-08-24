# run_logging.py
from __future__ import annotations
import os, uuid, time, json, logging, platform, subprocess
from pathlib import Path
from contextlib import contextmanager

# ---- Public API --------------------------------------------------------------

RUN_ID = os.environ.get("RUN_ID", str(uuid.uuid4())[:8])
ART_DIR = Path(os.getenv("FEDRATE_ART_DIR", "runs"))
ART_DIR.mkdir(parents=True, exist_ok=True)

# Import RunFiles class
from run_files import RunFiles
RUN_FILES = RunFiles(RUN_ID, ART_DIR)

def init_logging(level: str | None = None) -> logging.Logger:
    lvl = getattr(logging, (level or os.getenv("LOGLEVEL", "INFO")).upper(), logging.INFO)
    logger = logging.getLogger("fedrate")
    logger.setLevel(lvl)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(_JsonFormatter())
        logger.addHandler(h)
    return logger

def write_manifest(extra_env_prefix: str = "FEDRATE_") -> Path:
    git_rev = _git_rev()
    manifest = {
        "run_id": RUN_ID,
        "git_rev": git_rev,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "tz": time.tzname,
        "env_flags": {k: v for k, v in os.environ.items() if k.startswith(extra_env_prefix)},
        "ts": _now_iso(),
    }
    p = RUN_FILES.manifest()
    p.write_text(json.dumps(manifest, indent=2))
    logging.getLogger("fedrate").info(json.dumps({"event":"manifest_written","path":str(p)}))
    return p

def save_artifact(name: str, data) -> Path:
    """
    Save any JSON‑serializable object or raw str/bytes under runs/<RUN_ID>.<name>.
    """
    p = ART_DIR / f"{RUN_ID}.{name}"
    if isinstance(data, (dict, list)):
        p.write_text(json.dumps(data, indent=2))
    elif isinstance(data, (str, bytes)):
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(p, mode) as f:
            f.write(data)
    else:
        p.write_text(json.dumps({"repr": repr(data)}, indent=2))
    logging.getLogger("fedrate").info(json.dumps({"event":"artifact_saved","name":name,"path":str(p)}))
    return p

def get_today(default_iso: str | None = None) -> str:
    """
    Use FEDRATE_TODAY if set; else 'default_iso' if provided; else current UTC date.
    """
    env = os.getenv("FEDRATE_TODAY")
    if env:
        return env
    if default_iso:
        return default_iso
    return _now_iso()[:10]

@contextmanager
def timed_span(name: str):
    t0 = time.time()
    try:
        yield
    finally:
        dt = round(time.time() - t0, 3)
        logging.getLogger("fedrate").info(json.dumps({"event":"timing","span":name,"secs":dt}))

# ---- Internals ---------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": _now_iso(),
            "lvl": record.levelname,
            "logger": record.name,
            "run_id": RUN_ID,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base)

def _git_rev() -> str:
    try:
        return subprocess.check_output(["git","rev-parse","--short","HEAD"], text=True).strip()
    except Exception:
        return "nogit"

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
