#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "请使用 sudo 执行安装脚本。" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/usr/local/lib/stqb-updater"
ENV_FILE="/etc/stqb-updater.env"

install -d -m 0755 "${INSTALL_DIR}"
install -m 0755 "${SCRIPT_DIR}/stqb_updater.py" "${INSTALL_DIR}/stqb_updater.py"
install -m 0644 "${SCRIPT_DIR}/systemd/stqb-updater.service" /etc/systemd/system/stqb-updater.service
install -m 0644 "${SCRIPT_DIR}/systemd/stqb-updater.path" /etc/systemd/system/stqb-updater.path
install -m 0644 "${SCRIPT_DIR}/systemd/stqb-updater-check.service" /etc/systemd/system/stqb-updater-check.service
install -m 0644 "${SCRIPT_DIR}/systemd/stqb-updater-check.timer" /etc/systemd/system/stqb-updater-check.timer

if [[ ! -e "${ENV_FILE}" ]]; then
  install -m 0600 "${SCRIPT_DIR}/stqb-updater.env.example" "${ENV_FILE}"
else
  chmod 0600 "${ENV_FILE}"
fi

systemctl daemon-reload
systemctl enable --now stqb-updater.path stqb-updater-check.timer
/usr/bin/python3 "${INSTALL_DIR}/stqb_updater.py" initialize

echo "主机更新器已安装。请填写 ${ENV_FILE} 后执行："
echo "  sudo systemctl restart stqb-updater-check.timer"
echo "  sudo systemctl start stqb-updater-check.service"
