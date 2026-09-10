#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

echo "=== Cài đặt phím tắt LADA ROCm GFX906 ==="

DESKTOP_DIR="$HOME/Desktop"
APP_DIR="$HOME/.local/share/applications"

mkdir -p "$DESKTOP_DIR" "$APP_DIR"

SHORTCUT_FILE="$DESKTOP_DIR/Lada-ROCm-AMD.desktop"

cat <<EOF > "$SHORTCUT_FILE"
[Desktop Entry]
Name=Lada ROCm AMD
Comment=Phục hồi video AI Mosaic bằng GPU AMD (ROCm GFX906)
Exec=$SCRIPT_DIR/lada_rocm.sh
Icon=$SCRIPT_DIR/assets/io.github.ladaapp.lada.png
Terminal=false
Type=Application
Categories=AudioVideo;Video;Graphics;
EOF

chmod +x "$SHORTCUT_FILE"
cp "$SHORTCUT_FILE" "$APP_DIR/"

echo "-> Đã tạo phím tắt tại: $SHORTCUT_FILE"
echo "-> Đã thêm vào Menu ứng dụng: $APP_DIR/Lada-ROCm-AMD.desktop"
echo "Hoàn tất! Bạn có thể nhấp đúp vào icon trên Desktop hoặc chạy ./lada_rocm.sh."
