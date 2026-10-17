#!/usr/bin/env bash
# ============================================================
#  程星 ONVIF / ChengXing ONVIF - 一键安装（Linux / macOS）
#  用法： sudo ./install.sh [--with-ai] [--service] [--skip-binaries]
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
VENDOR="$ROOT/vendor"
WITH_AI=0
WITH_SERVICE=0
SKIP_BINARIES=0
for arg in "$@"; do
  case "$arg" in
    --with-ai) WITH_AI=1 ;;
    --service) WITH_SERVICE=1 ;;
    --skip-binaries) SKIP_BINARIES=1 ;;
    *) echo "未知参数：$arg"; exit 1 ;;
  esac
done

cyan() { printf '\033[36m%s\033[0m\n' "$*"; }
ok() { printf '\033[32m  [OK] %s\033[0m\n' "$*"; }
warn() { printf '\033[33m  [!] %s\033[0m\n' "$*"; }

echo
echo "  程星 ONVIF v1.0.0 安装程序"
echo "  =============================="

# ------------------------------------------------------------------ Python
cyan "检查 Python"
PY=""
for candidate in python3 python3.12 python3.11 python3.10 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      PY="$candidate"; break
    fi
  fi
done
if [ -z "$PY" ]; then
  echo "需要 Python 3.10+，请先安装："
  echo "  Ubuntu/Debian: sudo apt install -y python3 python3-venv python3-pip"
  echo "  macOS:         brew install python@3.12"
  exit 1
fi
ok "$($PY --version)  ($(command -v $PY))"

# ------------------------------------------------------------------ venv
cyan "创建虚拟环境"
if [ ! -x ".venv/bin/python" ]; then
  $PY -m venv .venv
fi
VPY=".venv/bin/python"
ok "虚拟环境就绪"

cyan "安装 Python 依赖"
$VPY -m pip install --upgrade pip --quiet
$VPY -m pip install -r requirements.txt
$VPY -m pip install "opencv-python-headless>=4.9"
if [ "$WITH_AI" = "1" ]; then
  $VPY -m pip install ultralytics
fi
ok "依赖安装完成"

# ------------------------------------------------------------------ FFmpeg
if [ "$SKIP_BINARIES" = "0" ]; then
  cyan "准备 FFmpeg"
  if command -v ffmpeg >/dev/null 2>&1; then
    ok "系统已安装 $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)"
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq && sudo apt-get install -y ffmpeg
    ok "FFmpeg 已通过 apt 安装"
  elif command -v brew >/dev/null 2>&1; then
    brew install ffmpeg
    ok "FFmpeg 已通过 brew 安装"
  else
    warn "未找到包管理器，请手动安装 FFmpeg"
  fi

  # ---------------------------------------------------------------- MediaMTX
  cyan "准备 MediaMTX"
  MTX_DIR="$VENDOR/mediamtx"
  mkdir -p "$MTX_DIR"
  if [ -x "$MTX_DIR/mediamtx" ]; then
    ok "已存在 $MTX_DIR/mediamtx"
  else
    OS="$(uname -s)"; ARCH="$(uname -m)"
    ASSET=""
    if [ "$OS" = "Darwin" ]; then
      [ "$ARCH" = "arm64" ] && ASSET="darwin_arm64.tar.gz" || ASSET="darwin_amd64.tar.gz"
    else
      case "$ARCH" in
        aarch64|arm64) ASSET="linux_arm64v8.tar.gz" ;;
        *) ASSET="linux_amd64.tar.gz" ;;
      esac
    fi
    URL="$(curl -fsSL -H 'User-Agent: cxonvif-installer' https://api.github.com/repos/bluenviron/mediamtx/releases/latest \
      | grep -o "https://[^\"]*${ASSET}" | head -1)"
    if [ -n "$URL" ]; then
      TMP="$(mktemp -d)"
      echo "  下载 $URL"
      curl -fsSL "$URL" -o "$TMP/mediamtx.tar.gz"
      tar -xzf "$TMP/mediamtx.tar.gz" -C "$TMP"
      cp "$TMP/mediamtx" "$MTX_DIR/mediamtx"
      chmod +x "$MTX_DIR/mediamtx"
      rm -rf "$TMP"
      ok "MediaMTX 已安装到 vendor/mediamtx"
    else
      warn "MediaMTX 下载失败，首次启动时会自动重试"
    fi
  fi
fi

# ------------------------------------------------------------------ 服务
if [ "$WITH_SERVICE" = "1" ]; then
  cyan "安装 systemd / launchd 服务"
  $VPY -m cxonvif autostart install || warn "服务安装失败（可能需要 sudo）"
fi

chmod +x start.sh 2>/dev/null || true

cyan "安装完成"
cat <<EOF

  启动命令：
    ./start.sh
    或  ./.venv/bin/python -m cxonvif serve

  网页控制台： http://localhost:5552
  默认账号：   admin / cx123456  （首次登录会要求修改）

  常用命令：
    ./.venv/bin/python -m cxonvif doctor
    ./.venv/bin/python -m cxonvif autostart install
    ./.venv/bin/python -m cxonvif password 新密码

EOF
