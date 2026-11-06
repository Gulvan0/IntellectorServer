#!/usr/bin/env bash
# Once per fresh VPS (Debian 12), as root, from /srv/intellector/infra: packages and repos, users, folders, MySQL, Python.
# Idempotent and additive: it never touches what already listens on the machine.
#   --authorized-key "<public key>"   the key of the deploy user (needed the first time)
#   --firewall                        ufw: 22, 80, 443 only. Not by default: v1 still serves from other ports
#   --harden-ssh                      key-only login, no root login. Not by default: v1's backup scripts use root's password
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BASE=/srv/intellector
AUTHORIZED_KEY=""
FIREWALL=no
HARDEN_SSH=no
while [ $# -gt 0 ]; do
    case "$1" in
        --authorized-key) AUTHORIZED_KEY="$2"; shift ;;
        --firewall) FIREWALL=yes ;;
        --harden-ssh) HARDEN_SSH=yes ;;
        *) echo "unknown option $1" >&2; exit 1 ;;
    esac
    shift
done
export DEBIAN_FRONTEND=noninteractive

log() { echo "== $*"; }

log "base packages"
# the MySQL repo's key is refreshed first, or the update below would fail on a stale one
if [ -f /etc/apt/sources.list.d/mysql.list ]; then
    curl -fsS https://repo.mysql.com/RPM-GPG-KEY-mysql-2025 | gpg --dearmor --yes -o /usr/share/keyrings/mysql.gpg
fi
apt-get update -qq
apt-get install -y -qq sudo rclone zstd curl gnupg ca-certificates python3-yaml python3-venv python3-pip debian-archive-keyring apt-transport-https ufw >/dev/null

log "user and folders"
id intellector >/dev/null 2>&1 || adduser --disabled-password --gecos "Intellector" intellector
mkdir -p "$BASE/server/releases"
if [ -n "$AUTHORIZED_KEY" ]; then
    install -d -m 700 -o intellector -g intellector /home/intellector/.ssh
    grep -qxF "$AUTHORIZED_KEY" /home/intellector/.ssh/authorized_keys 2>/dev/null || echo "$AUTHORIZED_KEY" >> /home/intellector/.ssh/authorized_keys
    chown intellector:intellector /home/intellector/.ssh/authorized_keys
    chmod 600 /home/intellector/.ssh/authorized_keys
fi
chown intellector:intellector "$BASE" "$BASE/server" "$BASE/server/releases"
chown -R intellector:intellector "$BASE/infra"

log "sudoers"
cat > /etc/sudoers.d/intellector <<'SUDOERS'
intellector ALL=(root) NOPASSWD: /usr/bin/systemctl restart intellector-server, /usr/bin/systemctl restart intellector-server.service
intellector ALL=(root) NOPASSWD: /usr/bin/systemctl start intellector.target, /usr/bin/systemctl stop intellector.target
intellector ALL=(root) NOPASSWD: /usr/bin/systemctl start intellector-backup.service
intellector ALL=(root) NOPASSWD: /srv/intellector/infra/apply.sh, /srv/intellector/infra/apply.sh --check
intellector ALL=(root) NOPASSWD: /srv/intellector/infra/scripts/restore.sh *
SUDOERS
chmod 440 /etc/sudoers.d/intellector
visudo -cf /etc/sudoers.d/intellector >/dev/null

log "MySQL 8.4 LTS"
if ! command -v mysqld >/dev/null; then
    # the config goes in first: MySQL 8.4 listens on all interfaces unless told otherwise
    install -D -m 644 "$HERE/mysql/intellector.cnf" /etc/mysql/conf.d/intellector.cnf
    curl -fsS https://repo.mysql.com/RPM-GPG-KEY-mysql-2025 | gpg --dearmor --yes -o /usr/share/keyrings/mysql.gpg
    echo "deb [signed-by=/usr/share/keyrings/mysql.gpg] http://repo.mysql.com/apt/debian bookworm mysql-8.4-lts" > /etc/apt/sources.list.d/mysql.list
    apt-get update -qq
    echo "mysql-community-server mysql-community-server/root-pass password" | debconf-set-selections
    echo "mysql-community-server mysql-community-server/re-root-pass password" | debconf-set-selections
    apt-get install -y -qq mysql-community-server >/dev/null
fi
systemctl enable --now mysql >/dev/null

log "databases and users"
if [ ! -f "$BASE/db-app.password" ]; then
    APP_PW="$(openssl rand -hex 24)"
    BK_PW="$(openssl rand -hex 24)"
    mysql <<SQL
CREATE DATABASE IF NOT EXISTS main CHARACTER SET utf8mb4;
CREATE DATABASE IF NOT EXISTS intellector_logs CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'intellector_app'@'localhost' IDENTIFIED BY '$APP_PW';
ALTER USER 'intellector_app'@'localhost' IDENTIFIED BY '$APP_PW';
GRANT ALL ON main.* TO 'intellector_app'@'localhost';
GRANT ALL ON intellector_logs.* TO 'intellector_app'@'localhost';
CREATE USER IF NOT EXISTS 'intellector_backup'@'localhost' IDENTIFIED BY '$BK_PW';
ALTER USER 'intellector_backup'@'localhost' IDENTIFIED BY '$BK_PW';
GRANT SELECT, SHOW VIEW, TRIGGER, EVENT, LOCK TABLES ON main.* TO 'intellector_backup'@'localhost';
SQL
    umask 077
    echo "$APP_PW" > "$BASE/db-app.password"
    printf '[client]\nuser=intellector_backup\npassword=%s\n' "$BK_PW" > "$BASE/mysql-backup.cnf"
    chown intellector:intellector "$BASE/db-app.password" "$BASE/mysql-backup.cnf"
fi

# for people (MySQL Workbench over an SSH tunnel): localhost only, so it is unreachable except through the tunnel.
# Root-only password file: the app user must not be able to read it.
if [ ! -f "$BASE/db-admin.password" ]; then
    ADMIN_PW="$(openssl rand -hex 24)"
    mysql <<SQL
CREATE USER IF NOT EXISTS 'intellector_admin'@'localhost' IDENTIFIED BY '$ADMIN_PW';
ALTER USER 'intellector_admin'@'localhost' IDENTIFIED BY '$ADMIN_PW';
GRANT ALL ON main.* TO 'intellector_admin'@'localhost';
GRANT ALL ON intellector_logs.* TO 'intellector_admin'@'localhost';
SQL
    (umask 077; echo "$ADMIN_PW" > "$BASE/db-admin.password")
fi

log "Caddy (installed, kept disabled until v1 gives up ports 80 and 443)"
if ! command -v caddy >/dev/null; then
    # the key stays armored: apt rejects the dearmored one, whose signing subkey it cannot find
    curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key -o /usr/share/keyrings/caddy-stable.asc
    curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt         | sed 's#/usr/share/keyrings/caddy-stable-archive-keyring.gpg#/usr/share/keyrings/caddy-stable.asc#' > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq
    apt-get install -y -qq caddy >/dev/null
    systemctl disable --now caddy >/dev/null 2>&1 || true
fi

log "Python 3.14 (uv)"
sudo -u intellector bash -s <<'USER_SCRIPT'
set -euo pipefail
[ -x /srv/intellector/tools/bin/uv ] || {
    python3 -m venv /srv/intellector/tools
    /srv/intellector/tools/bin/pip install -q uv
}
UV_PYTHON_INSTALL_DIR=/srv/intellector/python /srv/intellector/tools/bin/uv python install 3.14
USER_SCRIPT

log "configs"
"$HERE/apply.sh"

if [ "$FIREWALL" = yes ]; then
    log "firewall"
    ufw default deny incoming >/dev/null
    ufw default allow outgoing >/dev/null
    ufw allow 22/tcp >/dev/null && ufw allow 80/tcp >/dev/null && ufw allow 443/tcp >/dev/null
    ufw --force enable
fi

if [ "$HARDEN_SSH" = yes ]; then
    log "SSH hardening"
    [ -s /home/intellector/.ssh/authorized_keys ] || { echo "No deploy key installed: refusing to disable passwords" >&2; exit 1; }
    cat > /etc/ssh/sshd_config.d/10-intellector.conf <<'SSHD'
PasswordAuthentication no
PermitRootLogin no
SSHD
    sshd -t && systemctl reload ssh
fi

log "done"
