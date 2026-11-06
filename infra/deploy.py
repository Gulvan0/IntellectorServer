"""One-command deploy from the developer's PC: builds and checks both repos, publishes the client to the static hosting,
installs infra changes and a new server release on the VPS, then starts the drain of the old server.

    python infra/deploy.py [--skip-static] [--skip-server] [--skip-checks] [--no-drain] [--dry-run]

Settings come from the untracked infra/.env (see .env.example). The VPS is reached with the system `ssh`; the static
hosting with ftplib. A step that needs nothing (same infra, same server code) is skipped.
"""

import argparse
import ftplib
import hashlib
import io
import json
import os
import re
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NoReturn

SERVER_REPO = Path(__file__).resolve().parent.parent
INFRA_DIR = SERVER_REPO / "infra"
BASE = "/srv/intellector"
KEPT_CLIENT_VERSIONS = 3
SHELL_FILES = ["index.html", "sw.js", "manifest.json", ".htaccess"]
SERVER_PATHS = ["src", "alembic", "alembic.ini", "resources", "requirements.txt", "api.lock"]
SERVER_EXCLUDES = ["__pycache__", ".mypy_cache", "resources/config/secret.yaml", "resources/cert"]
CLIENT_FILES = ["bin/app.js", "bin/hxconda.js", "bin/version.json", "manifest.json"]
CLIENT_DIRS = ["assets"]


def fail(message: str) -> NoReturn:
    sys.exit(f"deploy: {message}")


def step(message: str) -> None:
    print(f"\n== {message}", flush=True)


def load_env() -> dict[str, str]:
    env_path = INFRA_DIR / ".env"
    if not env_path.exists():
        fail(f"{env_path} is missing: copy .env.example and fill it in")
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def run(command: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, input_bytes: bytes | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, input=input_bytes)
    if result.returncode != 0:
        fail(f"`{' '.join(command)}` failed:\n{result.stdout.decode(errors='replace')}\n{result.stderr.decode(errors='replace')}")
    return result.stdout.decode(errors="replace")


class Vps:
    def __init__(self, env: dict[str, str]) -> None:
        key = str(Path(env.get("VPS_SSH_KEY", "~/.ssh/intellector_deploy")).expanduser())
        self.target = f"{env['VPS_USER']}@{env['VPS_HOST']}"
        self.ssh_args = ["ssh", "-i", key, "-o", "BatchMode=yes", self.target]

    def run(self, script: str) -> str:
        return run([*self.ssh_args, "bash -s"], input_bytes=script.encode())

    def read(self, remote_path: str) -> str | None:
        result = subprocess.run([*self.ssh_args, f"cat {remote_path}"], capture_output=True)
        return result.stdout.decode().strip() if result.returncode == 0 else None

    def upload_tar(self, source_dir: Path, names: list[str], excludes: list[str], remote_dir: str) -> None:
        """Streams a tar archive through ssh, so that no extra tool is needed on either side"""
        tar_command = ["tar", "-cf", "-", "-C", str(source_dir)]
        for exclude in excludes:
            tar_command += ["--exclude", exclude]
        tar_command += names
        archive = subprocess.run(tar_command, capture_output=True)
        if archive.returncode != 0:
            fail(f"tar failed: {archive.stderr.decode(errors='replace')}")
        run([*self.ssh_args, f"mkdir -p {remote_dir} && tar -xf - -C {remote_dir}"], input_bytes=archive.stdout)


def is_excluded(relative: str, excludes: list[str]) -> bool:
    return any(exclude in relative.split("/") or relative.startswith(exclude) for exclude in excludes)


def tree_hash(root: Path, names: list[str], excludes: list[str]) -> str:
    digest = hashlib.sha256()
    for name in names:
        base = root / name
        files = [base] if base.is_file() else sorted(path for path in base.rglob("*") if path.is_file())
        for path in files:
            relative = path.relative_to(root).as_posix()
            if is_excluded(relative, excludes):
                continue
            digest.update(relative.encode())
            digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


# ---------------------------------------------------------------------------------------------------- checks

def read_api_version() -> int:
    match = re.search(r"API_VERSION\s*(?::\s*int\s*)?=\s*(\d+)", (SERVER_REPO / "src/other/api_version.py").read_text())
    if not match:
        fail("cannot read API_VERSION from src/other/api_version.py")
    return int(match.group(1))


def build_and_check(env: dict[str, str], skip_checks: bool, skip_static: bool) -> tuple[str, int]:
    frontend = Path(env["FRONTEND_REPO"])
    step("Building the client")
    run(["haxe", "build.hxml"], cwd=frontend)
    version = json.loads((frontend / "bin/version.json").read_text())
    build, api = str(version["build"]), int(version["api"])
    if build == "dev":
        fail("bin/version.json says build=dev: the release build did not stamp it")
    if api != read_api_version():
        fail(f"the client is built for API {api}, the server serves API {read_api_version()}")
    if not skip_static:
        index = (frontend / "index.html").read_text(encoding="utf-8")
        declared = re.search(r'var API_BASE_URL = "([^"]*)"', index)
        if declared is None:
            fail("index.html does not declare API_BASE_URL")
        elif declared.group(1).rstrip("/") != env["API_BASE_URL"].rstrip("/"):
            fail(f"index.html points at {declared.group(1)}, expected {env['API_BASE_URL']}")

    if skip_checks:
        return build, api

    step("Client unit tests")
    run(["haxe", "test.hxml"], cwd=frontend)
    step("Server checks (api.lock, Alembic)")
    server_env = {"STAGE": "test", "PYTHONPATH": "src"}
    run([sys.executable, "src/api_lock.py", "check"], cwd=SERVER_REPO, env=server_env)
    heads = [line for line in run([sys.executable, "-m", "alembic", "heads"], cwd=SERVER_REPO, env=server_env).splitlines() if "(head)" in line]
    if len(heads) != 1:
        fail(f"Alembic has {len(heads)} heads, expected exactly one: {heads}")
    run([sys.executable, "-m", "alembic", "check"], cwd=SERVER_REPO, env=server_env)
    return build, api


# ---------------------------------------------------------------------------------------------------- static hosting

class Ftp:
    """The hosting resets sessions now and then, so every operation reconnects and retries"""

    RETRIES = 6

    def __init__(self, env: dict[str, str]) -> None:
        self.env = env
        self.ftp: ftplib.FTP
        self.known_dirs: set[str] = set()
        self._connect()

    def _connect(self) -> None:
        env = self.env
        mode = env.get("FTP_TLS", "auto")
        if mode in ("auto", "yes"):
            try:
                tls = ftplib.FTP_TLS(env["FTP_HOST"], timeout=60)
                tls.login(env["FTP_USER"], env["FTP_PASSWORD"])
                tls.prot_p()
                self.ftp = tls
            except Exception as error:  # ftplib's errors, but also the socket and SSL ones
                if mode == "yes":
                    fail(f"FTPS is required but failed: {error}")
                print(f"FTPS unavailable ({error}); falling back to plain FTP")
                self.ftp = self._plain(env)
        else:
            self.ftp = self._plain(env)
        self.ftp.cwd(env["FTP_BASE_DIR"])

    @staticmethod
    def _plain(env: dict[str, str]) -> ftplib.FTP:
        ftp = ftplib.FTP(env["FTP_HOST"], timeout=60)
        ftp.login(env["FTP_USER"], env["FTP_PASSWORD"])
        return ftp

    def _retrying[T](self, operation: Callable[[], T]) -> T:
        for attempt in range(self.RETRIES):
            try:
                return operation()
            except (ConnectionError, EOFError, TimeoutError, ssl.SSLError, ftplib.error_temp) as error:
                if attempt == self.RETRIES - 1:
                    raise
                print(f"FTP connection lost ({type(error).__name__}); reconnecting", flush=True)
                time.sleep(2 * (attempt + 1))
                try:
                    self.ftp.close()
                except Exception:
                    pass
                self._connect()
        raise AssertionError

    def _ignoring_missing(self, operation: Callable[[], object]) -> None:
        """A retried delete may find its target gone already: the reply to the first attempt was what got lost"""
        try:
            self._retrying(operation)
        except ftplib.error_perm as error:
            if not str(error).startswith("550"):
                raise

    def exists(self, path: str) -> bool:
        parent, _, name = path.rpartition("/")
        return self._retrying(lambda: name in [entry.rsplit("/", 1)[-1] for entry in self.ftp.nlst(parent or ".")])

    def makedirs(self, path: str) -> None:
        current = ""
        for part in path.strip("/").split("/"):
            current = f"{current}/{part}" if current else part
            if current in self.known_dirs:
                continue
            try:
                self._retrying(lambda: self.ftp.mkd(current))
            except ftplib.error_perm:
                pass  # exists already
            self.known_dirs.add(current)

    def put_file(self, local: Path, remote: str) -> None:
        def upload() -> None:
            with local.open("rb") as handle:
                self.ftp.storbinary(f"STOR {remote}", handle)

        self._retrying(upload)

    def put_tree(self, local_root: Path, remote_root: str, workers: int = 4) -> int:
        """Each file costs a TLS handshake on the data channel, so the files go over several connections at once"""
        files = sorted(p for p in local_root.rglob("*") if p.is_file())
        for directory in sorted({f"{remote_root}/{p.relative_to(local_root).as_posix()}".rpartition("/")[0] for p in files}):
            self.makedirs(directory)

        local = threading.local()
        done = 0
        lock = threading.Lock()

        def upload(path: Path) -> None:
            nonlocal done
            if not hasattr(local, "ftp"):
                local.ftp = Ftp(self.env)
            local.ftp.put_file(path, f"{remote_root}/{path.relative_to(local_root).as_posix()}")
            with lock:
                done += 1
                if done % 25 == 0:
                    print(f"  {done}/{len(files)}", flush=True)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in [pool.submit(upload, path) for path in files]:
                future.result()
        return len(files)

    def read(self, remote: str) -> bytes | None:
        def download() -> bytes | None:
            buffer = io.BytesIO()
            try:
                self.ftp.retrbinary(f"RETR {remote}", buffer.write)
            except ftplib.error_perm:
                return None
            return buffer.getvalue()

        return self._retrying(download)

    def remove_tree(self, path: str) -> None:
        for entry in self._retrying(lambda: list(self.ftp.mlsd(path, facts=["type"]))):
            name, facts = entry
            if name in (".", ".."):
                continue
            child = f"{path}/{name}"
            if facts.get("type") == "dir":
                self.remove_tree(child)
            else:
                self._ignoring_missing(lambda: self.ftp.delete(child))
        self._ignoring_missing(lambda: self.ftp.rmd(path))

    def client_versions(self) -> list[int]:
        if not self.exists("v"):
            return []
        return sorted(int(name) for name, facts in self._retrying(lambda: list(self.ftp.mlsd("v", facts=["type"]))) if facts.get("type") == "dir" and name.isdigit())


def publish_client(env: dict[str, str], api: int, dry_run: bool) -> None:
    frontend = Path(env["FRONTEND_REPO"])
    step(f"Publishing the client of API {api}")
    if dry_run:
        print("dry run: nothing uploaded")
        return

    staging = frontend / "bin" / "_release"
    # the release folder is assembled locally so that the upload is a plain tree copy
    for relative in CLIENT_FILES:
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((frontend / relative).read_bytes())
    for directory in CLIENT_DIRS:
        for path in (frontend / directory).rglob("*"):
            if path.is_file():
                target = staging / path.relative_to(frontend)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())

    ftp = Ftp(env)
    temp, final, old = f"v/{api}.tmp", f"v/{api}", f"v/{api}.old"
    ftp.makedirs("v")
    for leftover in (temp, old):
        if ftp.exists(leftover):
            ftp.remove_tree(leftover)
    count = ftp.put_tree(staging, temp)
    print(f"uploaded {count} files")
    if ftp.exists(final):
        ftp._retrying(lambda: ftp.ftp.rename(final, old))
    ftp._retrying(lambda: ftp.ftp.rename(temp, final))
    if ftp.exists(old):
        ftp.remove_tree(old)

    for obsolete in ftp.client_versions()[:-KEPT_CLIENT_VERSIONS]:
        print(f"pruning v/{obsolete}")
        ftp.remove_tree(f"v/{obsolete}")

    for name in SHELL_FILES:
        local = frontend / name
        if local.exists() and ftp.read(name) != local.read_bytes():
            print(f"updating {name}")
            ftp.put_file(local, name)


# ---------------------------------------------------------------------------------------------------- VPS

def deploy_infra(vps: Vps, dry_run: bool) -> None:
    local_hash = tree_hash(INFRA_DIR, [p.name for p in INFRA_DIR.iterdir() if p.name != ".env"], ["__pycache__", ".mypy_cache"])
    if vps.read(f"{BASE}/infra/.hash") == local_hash:
        print("infra unchanged")
        return
    step("Installing infra changes")
    if dry_run:
        print("dry run: infra would be uploaded and applied")
        return
    vps.upload_tar(INFRA_DIR, [p.name for p in INFRA_DIR.iterdir() if p.name != ".env"], ["__pycache__", ".mypy_cache"], f"{BASE}/infra")
    vps.run(f"""set -e
chmod +x {BASE}/infra/*.sh {BASE}/infra/ictl {BASE}/infra/scripts/*.sh
caddy validate --adapter caddyfile --config {BASE}/infra/caddy/Caddyfile
sudo {BASE}/infra/apply.sh
echo {local_hash} > {BASE}/infra/.hash
""")


def deploy_server(vps: Vps, env: dict[str, str], dry_run: bool, drain: bool) -> None:
    code_hash = tree_hash(SERVER_REPO, SERVER_PATHS, SERVER_EXCLUDES)
    deployed_hash = vps.read(f"{BASE}/server/current/.code-hash")
    if deployed_hash == code_hash:
        print("server code unchanged")
        return

    sha = run(["git", "rev-parse", "--short", "HEAD"], cwd=SERVER_REPO).strip()
    dirty = bool(run(["git", "status", "--porcelain", "--", *SERVER_PATHS], cwd=SERVER_REPO).strip())
    revision = f"{sha}-dirty" if dirty else sha
    release = f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{revision}"
    release_dir = f"{BASE}/server/releases/{release}"

    step(f"Uploading server release {release}")
    if dry_run:
        print("dry run: nothing uploaded")
        return
    vps.upload_tar(SERVER_REPO, SERVER_PATHS, SERVER_EXCLUDES, release_dir)
    vps.run(f"""set -e
cd {release_dir}
echo {revision} > REVISION
echo {code_hash} > .code-hash
ln -s {BASE}/secret.yaml resources/config/secret.yaml
export UV_PYTHON_INSTALL_DIR={BASE}/python
{BASE}/tools/bin/uv venv --python 3.14 venv
{BASE}/tools/bin/uv pip install --python venv/bin/python -r requirements.txt
ln -sfn {release_dir} {BASE}/server/current.tmp
mv -T {BASE}/server/current.tmp {BASE}/server/current
""")
    print(f"current -> {release}")

    if not drain:
        print("--no-drain: the old server keeps running until it is restarted")
        return
    if vps.run("systemctl is-active intellector-server || true").strip() != "active":
        step("The server is not running: starting it")
        vps.run("sudo systemctl start intellector.target")
        return
    step("Starting the drain")
    start_drain(env)


def start_drain(env: dict[str, str]) -> None:
    base = env["API_BASE_URL"].rstrip("/")

    def post(path: str, payload: dict[str, str] | None, token: str | None) -> bytes:
        headers = {"content-type": "application/json"}
        if token:
            headers["intellector-user-token"] = token
        request = urllib.request.Request(base + path, data=json.dumps(payload).encode() if payload is not None else b"", headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body: bytes = response.read()
                return body
        except urllib.error.HTTPError as error:
            fail(f"POST {path} answered {error.code}: {error.read().decode(errors='replace')}")

    token: str = json.loads(post("/auth/signin", {"login": env["ADMIN_LOGIN"], "password": env["ADMIN_PASSWORD"]}, None))["token"]
    post("/shutdown", None, token)
    print("drain started: the server exits when the ongoing games are over, and systemd starts the new release")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-static", action="store_true", help="do not publish the client")
    parser.add_argument("--skip-server", action="store_true", help="do not touch the VPS")
    parser.add_argument("--skip-checks", action="store_true", help="skip the test suites and schema checks (the builds still run)")
    parser.add_argument("--no-drain", action="store_true", help="switch `current` but leave the old server running")
    parser.add_argument("--dry-run", action="store_true", help="build and check, then only say what would be uploaded")
    args = parser.parse_args()

    started = time.monotonic()
    env = load_env()
    _build, api = build_and_check(env, args.skip_checks, args.skip_static)

    if not args.skip_static:
        publish_client(env, api, args.dry_run)

    if not args.skip_server:
        vps = Vps(env)
        deploy_infra(vps, args.dry_run)
        deploy_server(vps, env, args.dry_run, drain=not args.no_drain)

    print(f"\ndone in {time.monotonic() - started:.0f}s")


if __name__ == "__main__":
    main()
