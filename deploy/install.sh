#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/codebase/upgrade_linux}"
SERVICE_NAME="${SERVICE_NAME:-esp32-upgrade}"
PORT="${ESP_UPGRADE_PORT:-8010}"

echo "Installing ${SERVICE_NAME} into ${APP_DIR}"

sudo mkdir -p "${APP_DIR}"
sudo rsync -a --delete \
  --exclude ".git" \
  --exclude "backend/.venv" \
  --exclude "backend/upgrade_server/__pycache__" \
  ./ "${APP_DIR}/"

cd "${APP_DIR}/backend"
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

service_tmp="$(mktemp)"
sed "s@/codebase/upgrade_linux@${APP_DIR}@g" "${APP_DIR}/deploy/systemd/esp32-upgrade.service" > "${service_tmp}"
sudo cp "${service_tmp}" "/etc/systemd/system/${SERVICE_NAME}.service"
rm -f "${service_tmp}"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "Done. Open http://SERVER_IP:${PORT}"
