#!/bin/bash
# One-line macOS installer for Browser. No Homebrew, no admin, no dragging files.
#   /bin/bash -c "$(curl -fsSL https://idkhowtonamemyselfasadev.github.io/browser/install-mac.sh)"
set -e
echo "== Browser for macOS =="
if ! command -v python3 >/dev/null 2>&1; then
  echo "First you need Apple's command-line tools (for python3)."
  echo "A box will pop up - click Install, wait for it to finish, then paste this same line again."
  xcode-select --install 2>/dev/null || true
  exit 1
fi
PY="$(command -v python3)"
echo "Installing the engine (PyQt6) - a few minutes..."
"$PY" -m pip install --user --quiet --upgrade PyQt6 PyQt6-WebEngine 2>/dev/null \
  || "$PY" -m pip install --user --break-system-packages --quiet --upgrade PyQt6 PyQt6-WebEngine
echo "Downloading the browser..."
TMP="$(mktemp -d)"
curl -fsSL https://idkhowtonamemyselfasadev.github.io/browser/browser-mac.tar -o "$TMP/b.tar"
tar xf "$TMP/b.tar" -C "$TMP"
DEST="$HOME/Applications/Browser"
rm -rf "$DEST"; mkdir -p "$DEST"
cp -R "$TMP/browser-mac/browser-mac/." "$DEST/"
LAUNCH="$HOME/Applications/Browser.command"
printf '#!/bin/bash\nexec "%s" "%s/browser.py" "$@"\n' "$PY" "$DEST" > "$LAUNCH"
chmod +x "$LAUNCH"
rm -rf "$TMP"
echo ""
echo "Done. Opening it now. Next time just double-click:  ~/Applications/Browser.command"
exec "$PY" "$DEST/browser.py"
