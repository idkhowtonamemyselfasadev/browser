#!/usr/bin/env bash
# Installs the PyQt6 WebEngine dependency and adds Browser to the app launcher.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing dependency (PyQt6 WebEngine)..."
if python3 -c "import PyQt6.QtWebEngineWidgets" 2>/dev/null; then
    echo "    already installed"
elif command -v dnf >/dev/null; then
    sudo dnf install -y python3-pyqt6-webengine
elif command -v apt >/dev/null; then
    sudo apt install -y python3-pyqt6.qtwebengine
elif command -v pacman >/dev/null; then
    sudo pacman -S --needed --noconfirm python-pyqt6-webengine
else
    pip install --user PyQt6 PyQt6-WebEngine
fi

echo "==> Adding launcher entry + icon..."
mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
cp "$DIR/icon.svg" ~/.local/share/icons/hicolor/scalable/apps/browser.svg
cat > ~/.local/share/applications/browser.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Browser
Comment=Minimal island-styled browser
Exec=python3 $DIR/browser.py
Terminal=false
Categories=Network;WebBrowser;
Icon=browser
StartupWMClass=browser
EOF
gtk-update-icon-cache ~/.local/share/icons/hicolor 2>/dev/null || true
update-desktop-database ~/.local/share/applications 2>/dev/null || true

echo "==> Done. Launch 'Browser' from your app menu or run: python3 $DIR/browser.py"
