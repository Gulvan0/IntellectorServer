"""
Guards against forgetting to bump API_VERSION: `api.lock` holds the version and a hash of the OpenAPI
schema it was last confirmed for. The WebSocket protocol isn't covered.

    python src/api_lock.py check    exits non-zero if the schema changed while API_VERSION didn't
    python src/api_lock.py confirm  rewrites api.lock (after a bump, or for a backward-compatible change)
"""
import hashlib
import json
import sys
from pathlib import Path

from other.api_version import API_VERSION

ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = ROOT / "api.lock"


def compute_schema_hash() -> str:
    from main import app

    return hashlib.sha256(json.dumps(app.openapi(), sort_keys=True).encode()).hexdigest()


def write_lock() -> None:
    LOCK_PATH.write_text(json.dumps({"api_version": API_VERSION, "schema_hash": compute_schema_hash()}, indent=2) + "\n", encoding="utf-8")


def check() -> int:
    if not LOCK_PATH.exists():
        print("api.lock is missing: run `python src/api_lock.py confirm`")
        return 1

    locked = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if locked["api_version"] != API_VERSION:
        print(f"API_VERSION is {API_VERSION} but api.lock was made for {locked['api_version']}: run `python src/api_lock.py confirm`")
        return 1

    if locked["schema_hash"] != compute_schema_hash():
        print(
            f"The API schema changed while API_VERSION stayed {API_VERSION}.\n"
            "Bump API_VERSION in src/other/api_version.py (and the client's Config.API_VERSION) if the change is breaking,\n"
            "then run `python src/api_lock.py confirm`; run it as is if the change is backward-compatible."
        )
        return 1

    print("api.lock is up to date")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "confirm":
        write_lock()
        print("api.lock rewritten")
    elif len(sys.argv) == 2 and sys.argv[1] == "check":
        sys.exit(check())
    else:
        sys.exit(__doc__)
