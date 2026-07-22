# Browser

A minimal, island-styled web browser built with Python and Qt WebEngine (Chromium).

![icon](icon.svg)

## Features

- Chromium engine — sites work like in Chrome, logins/cookies are saved
- Dark island-style UI (Catppuccin colors), tabs with close buttons
- Google search from the address bar or the start page
- Start page with clock and quick links
- Dark mode forced for all websites
- Single instance — launching again opens a new tab in the running window
- Fullscreen video support, downloads go to `~/Downloads`

## Install (Linux)

```sh
git clone https://github.com/hypervierx-netizen/browser.git
cd browser
./install.sh
```

`install.sh` installs the PyQt6 WebEngine dependency (Fedora/Debian/Ubuntu/Arch)
and adds "Browser" to your app launcher with its icon.

Or run it directly without installing:

```sh
python3 browser.py
```

(needs `python3-pyqt6-webengine` / `PyQt6-WebEngine`)

## Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+T` | New tab |
| `Ctrl+W` | Close tab |
| `Ctrl+L` | Focus address bar |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Next / previous tab |
| `Ctrl+R` / `F5` | Reload |
| `F11` | Fullscreen |
| `Ctrl+Q` | Quit |
