#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash ops/systemd/install-vm-services.sh"
  exit 1
fi

KAIROS_USER="${KAIROS_USER:-${SUDO_USER:-}}"
if [[ -z "${KAIROS_USER}" ]]; then
  KAIROS_USER="$(logname 2>/dev/null || true)"
fi
if [[ -z "${KAIROS_USER}" ]]; then
  echo "Cannot determine KAIROS_USER. Set it explicitly, e.g. KAIROS_USER=ubuntu."
  exit 1
fi

KAIROS_HOME="/home/${KAIROS_USER}"
REPO_DIR="${REPO_DIR:-${KAIROS_HOME}/revenuecat-agent}"

if [[ ! -d "${REPO_DIR}" ]]; then
  echo "Repo directory not found: ${REPO_DIR}"
  exit 1
fi
if [[ ! -f "${REPO_DIR}/docker-compose.yml" ]]; then
  echo "docker-compose.yml not found under ${REPO_DIR}"
  exit 1
fi
if [[ ! -f "${REPO_DIR}/ui/kairos-rain-chat/package.json" ]]; then
  echo "UI package.json not found under ${REPO_DIR}/ui/kairos-rain-chat"
  exit 1
fi

echo "[1/6] Installing cloudflared (if missing)..."
if ! command -v cloudflared >/dev/null 2>&1; then
  ARCH="$(dpkg --print-architecture)"
  if [[ "${ARCH}" != "amd64" && "${ARCH}" != "arm64" ]]; then
    echo "Unsupported architecture for cloudflared package: ${ARCH}"
    exit 1
  fi
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb" -o /tmp/cloudflared.deb
  apt-get update
  apt-get install -y /tmp/cloudflared.deb
fi

echo "[2/6] Ensuring Node.js runtime via nvm for ${KAIROS_USER}..."
if [[ ! -s "${KAIROS_HOME}/.nvm/nvm.sh" ]]; then
  su - "${KAIROS_USER}" -c 'curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash'
fi
su - "${KAIROS_USER}" -c "export NVM_DIR=\"\$HOME/.nvm\"; . \"\$NVM_DIR/nvm.sh\"; nvm install 20; nvm alias default 20"

echo "[3/6] Installing UI dependencies..."
su - "${KAIROS_USER}" -c "export NVM_DIR=\"\$HOME/.nvm\"; . \"\$NVM_DIR/nvm.sh\"; nvm use 20 >/dev/null; cd \"${REPO_DIR}/ui/kairos-rain-chat\"; npm install"

echo "[4/6] Rendering systemd units..."
render_unit() {
  local src="$1"
  local dst="$2"
  sed \
    -e "s#{{KAIROS_USER}}#${KAIROS_USER}#g" \
    -e "s#{{KAIROS_HOME}}#${KAIROS_HOME}#g" \
    -e "s#{{REPO_DIR}}#${REPO_DIR}#g" \
    "${src}" > "${dst}"
}

render_unit "${REPO_DIR}/ops/systemd/kairos-agent-backend.service.tpl" /etc/systemd/system/kairos-agent-backend.service
render_unit "${REPO_DIR}/ops/systemd/kairos-agent-ui.service.tpl" /etc/systemd/system/kairos-agent-ui.service
render_unit "${REPO_DIR}/ops/systemd/kairos-agent-tunnel.service.tpl" /etc/systemd/system/kairos-agent-tunnel.service

echo "[5/6] Enabling and starting services..."
systemctl daemon-reload
systemctl enable --now kairos-agent-backend.service
systemctl enable --now kairos-agent-ui.service
systemctl enable --now kairos-agent-tunnel.service

echo "[6/6] Service health and tunnel URL..."
systemctl --no-pager --full status kairos-agent-backend.service | sed -n '1,12p'
systemctl --no-pager --full status kairos-agent-ui.service | sed -n '1,12p'
systemctl --no-pager --full status kairos-agent-tunnel.service | sed -n '1,12p'

TUNNEL_URL="$(grep -Eo 'https://[-a-z0-9]+\.trycloudflare\.com' /var/log/kairos-cloudflared.log | tail -n 1 || true)"
if [[ -n "${TUNNEL_URL}" ]]; then
  echo "Tunnel URL: ${TUNNEL_URL}"
else
  echo "Tunnel URL not found yet. Run: journalctl -u kairos-agent-tunnel.service -n 50"
fi
