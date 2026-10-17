#!/usr/bin/env bash
# ============================================================
#  程星 ONVIF / ChengXing ONVIF - 启动脚本
# ============================================================
set -e
cd "$(dirname "$0")"

if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

if [ "$1" = "--silent" ]; then
  nohup "$PY" -m cxonvif serve --silent >/dev/null 2>&1 &
  echo "程星 ONVIF 已在后台启动：http://localhost:5552"
  exit 0
fi

echo
echo "  程星 ONVIF 正在启动…"
echo "  网页控制台 http://localhost:5552"
echo
exec "$PY" -m cxonvif serve
