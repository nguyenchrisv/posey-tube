#!/bin/bash
# posey-tube install script
# Run on the Pi as a normal user with sudo.
# Idempotent: safe to re-run.

set -euo pipefail

# --- Configuration ---
INSTALL_DIR="/opt/posey-tube"
CONFIG_DIR="/etc/posey-tube"
VENV_DIR="${INSTALL_DIR}/venv"
SERVICE_NAME="posey-tube"
SERVICE_USER="posey-tube"
SERVICE_GROUP="gpio"
REPO_URL="https://github.com/nguyenchrisv/posey-tube.git"
BRANCH="main"

# --- Helpers ---
log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

# Must run with sudo
if [[ $EUID -ne 0 ]]; then
    die "This script must be run with sudo (e.g., sudo ./install.sh)"
fi

# Detect if we're on a Raspberry Pi (optional check)
if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    log "WARNING: Not running on a Raspberry Pi. Proceeding anyway..."
fi

log "Updating apt cache..."
apt-get update -qq

log "Installing system dependencies..."
apt-get install -y -qq python3-lgpio python3-venv git

log "Creating service user and group..."
if ! getent group "${SERVICE_GROUP}" >/dev/null; then
    groupadd --system "${SERVICE_GROUP}"
fi
if ! getent passwd "${SERVICE_USER}" >/dev/null; then
    useradd --system --home-dir "${INSTALL_DIR}" --shell /usr/sbin/nologin \
        --groups "${SERVICE_GROUP}" "${SERVICE_USER}"
fi

log "Creating install directory..."
mkdir -p "${INSTALL_DIR}"
chown "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_DIR}"

log "Cloning/updating repository..."
if [[ -d "${INSTALL_DIR}/.git" ]]; then
    log "Repository exists, updating..."
    sudo -u "${SERVICE_USER}" git -C "${INSTALL_DIR}" fetch origin
    sudo -u "${SERVICE_USER}" git -C "${INSTALL_DIR}" checkout "${BRANCH}"
    sudo -u "${SERVICE_USER}" git -C "${INSTALL_DIR}" pull origin "${BRANCH}"
else
    sudo -u "${SERVICE_USER}" git clone --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
fi

log "Creating virtual environment with --system-site-packages..."
sudo -u "${SERVICE_USER}" python3 -m venv --system-site-packages "${VENV_DIR}"

log "Installing package into the venv (as ${SERVICE_USER}, no dev extras)..."
sudo -u "${SERVICE_USER}" "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
sudo -u "${SERVICE_USER}" "${VENV_DIR}/bin/pip" install --quiet --upgrade "${INSTALL_DIR}"

log "Creating config directory..."
mkdir -p "${CONFIG_DIR}"
chown root:"${SERVICE_GROUP}" "${CONFIG_DIR}"
chmod 0750 "${CONFIG_DIR}"

log "Installing example config if no config exists..."
if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then
    cp "${INSTALL_DIR}/deploy/config.example.toml" "${CONFIG_DIR}/config.toml"
    chown root:"${SERVICE_GROUP}" "${CONFIG_DIR}/config.toml"
    chmod 0640 "${CONFIG_DIR}/config.toml"
    log "Created ${CONFIG_DIR}/config.toml from example. Edit it with your pin configuration."
else
    log "Config ${CONFIG_DIR}/config.toml already exists, leaving unchanged."
fi

log "Setting up secrets file..."
if [[ ! -f "${CONFIG_DIR}/secrets.env" ]]; then
    # Create empty file with correct permissions; Christopher fills it in
    install -m 600 /dev/null "${CONFIG_DIR}/secrets.env"
    chown root:"${SERVICE_GROUP}" "${CONFIG_DIR}/secrets.env"
    log "Created ${CONFIG_DIR}/secrets.env (mode 600)."
    echo "  To set the API token, run:"
    echo "    sudo install -m 600 /dev/null ${CONFIG_DIR}/secrets.env"
    echo "    sudo sh -c 'read -rsp \"Posey-tube API token: \" token && echo \"POSEY_TUBE_TOKEN=\${token}\" > ${CONFIG_DIR}/secrets.env'"
else
    log "Secrets file ${CONFIG_DIR}/secrets.env already exists, leaving unchanged."
fi

log "Installing systemd service..."
cp "${INSTALL_DIR}/deploy/posey-tube.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
log "Service installed. Enable with: sudo systemctl enable --now ${SERVICE_NAME}"

log "Installation complete."
log ""
log "Next steps:"
log "  1. Edit ${CONFIG_DIR}/config.toml with your pin configuration."
log "  2. Set the API token in ${CONFIG_DIR}/secrets.env (see command above)."
log "  3. Enable and start the service:"
log "     sudo systemctl enable --now ${SERVICE_NAME}"
log "  4. Test: curl -H \"Authorization: Bearer <token>\" http://localhost:8090/health"
log ""
log "To update later, re-run this script (idempotent)."