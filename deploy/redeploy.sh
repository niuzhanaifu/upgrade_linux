#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/codebase/upgrade_linux}"
SERVICE_NAME="${SERVICE_NAME:-esp32-upgrade}"
APP_REPO_URL="${UPGRADE_APP_REPO_URL:-}"
APP_BRANCH="${UPGRADE_APP_BRANCH:-main}"
ENV_FILE="${ENV_FILE:-/etc/esp32-upgrade.env}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

ensure_app_dir_owner() {
  local parent_dir
  parent_dir="$(dirname "${APP_DIR}")"
  sudo mkdir -p "${parent_dir}"
  if [ ! -e "${APP_DIR}" ]; then
    sudo mkdir -p "${APP_DIR}"
  fi
  sudo chown -R "$(id -u):$(id -g)" "${APP_DIR}"
}

pull_or_clone_app() {
  ensure_app_dir_owner

  if [ -d "${APP_DIR}/.git" ]; then
    log "Pulling latest app code in ${APP_DIR}"
    cd "${APP_DIR}"
    git fetch --all --prune
    if [ -n "${APP_BRANCH}" ]; then
      git checkout "${APP_BRANCH}"
    fi
    git pull --ff-only
    return
  fi

  if [ -n "$(find "${APP_DIR}" -mindepth 1 -maxdepth 1 2>/dev/null)" ]; then
    log "ERROR: ${APP_DIR} exists but is not a git repository."
    log "Move it away, or set APP_DIR to an empty directory."
    exit 1
  fi

  if [ -z "${APP_REPO_URL}" ]; then
    log "ERROR: UPGRADE_APP_REPO_URL is empty."
    log "First deploy example:"
    log "  UPGRADE_APP_REPO_URL=https://github.com/your-org/upgrade_linux.git ./deploy/redeploy.sh"
    exit 1
  fi

  log "Cloning app code into ${APP_DIR}"
  if [ -n "${APP_BRANCH}" ]; then
    git clone --branch "${APP_BRANCH}" "${APP_REPO_URL}" "${APP_DIR}"
  else
    git clone "${APP_REPO_URL}" "${APP_DIR}"
  fi
  cd "${APP_DIR}"
}

ensure_env_file() {
  if [ -f "${ENV_FILE}" ]; then
    log "Keeping existing ${ENV_FILE}"
    append_missing_env_keys
    return
  fi

  log "Creating ${ENV_FILE}"
  sudo cp "${APP_DIR}/deploy/esp32-upgrade.env.example" "${ENV_FILE}"
  log "Edit ${ENV_FILE} later to fill ESP32 repo/build/upgrade settings."
}

append_missing_env_keys() {
  local example_file
  example_file="${APP_DIR}/deploy/esp32-upgrade.env.example"

  while IFS= read -r line || [ -n "${line}" ]; do
    case "${line}" in
      ""|\#*) continue ;;
    esac

    local key
    key="${line%%=*}"
    if ! sudo grep -q "^${key}=" "${ENV_FILE}"; then
      log "Adding missing env key ${key} to ${ENV_FILE}"
      printf '%s\n' "${line}" | sudo tee -a "${ENV_FILE}" >/dev/null
    fi
  done < "${example_file}"
}

install_python_deps() {
  log "Installing backend dependencies"
  cd "${APP_DIR}/backend"
  python3 -m venv .venv
  . .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
}

install_systemd_service() {
  log "Installing systemd service ${SERVICE_NAME}"
  local service_tmp
  service_tmp="$(mktemp)"
  sed \
    -e "s@/codebase/upgrade_linux@${APP_DIR}@g" \
    -e "s@/etc/esp32-upgrade.env@${ENV_FILE}@g" \
    "${APP_DIR}/deploy/systemd/esp32-upgrade.service" > "${service_tmp}"
  sudo cp "${service_tmp}" "/etc/systemd/system/${SERVICE_NAME}.service"
  rm -f "${service_tmp}"
  sudo systemctl daemon-reload
  sudo systemctl enable "${SERVICE_NAME}"
}

restart_service() {
  log "Restarting ${SERVICE_NAME}"
  sudo systemctl restart "${SERVICE_NAME}"
  sudo systemctl --no-pager --full status "${SERVICE_NAME}" || true
}

pull_or_clone_app
ensure_env_file
install_python_deps
install_systemd_service
restart_service

log "Deploy complete. Open http://14.103.183.47:8010"
