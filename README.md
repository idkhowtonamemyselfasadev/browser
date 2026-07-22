<div align="center">

<img src="icon.svg" width="96">

# Browser

**A small, fast, island-styled web browser — built with Python, Qt and the Chromium engine.**

Dark by default. No clutter, no telemetry, no account nagging.
Just tabs, a search bar, and a start page you can make your own.

</div>

---

## Why

Big browsers do a hundred things. This one does the things you actually use,
in ~300 lines of Python you can read in one sitting — and it still renders
every site perfectly, because the engine underneath is the same Chromium
that powers Chrome.

## Features

**Browsing**
- Full Chromium rendering — sites look and work like in Chrome
- Chrome-sized tabs with round close buttons; closing the last tab gives you a fresh start page instead of a dead window
- Smart address bar: URLs open directly, anything else searches Google
- Suggestions while you type — domain guesses (`wiki` → `wikipedia.org`), sites you've visited before, and live Google suggestions
- Websites are told you prefer dark mode; sites without a dark theme get auto-darkened
- Logins and cookies survive restarts; downloads land in `~/Downloads`
- Fullscreen video (YouTube etc.) works
- Single instance: launching again just opens a new tab in the running window

**Start page**
- Clock, date, and a Google search box
- Quick-link shortcuts you can edit: hover one to remove it, hit the round **+** to add your own (it guesses the site and fills in the name for you)
- **⚙ Customization menu**: pick one of four bundled nature backgrounds, use any image of your own, or keep the clean dark look — your choice is remembered

## Install (Linux)

```sh
git clone https://github.com/hypervierx-netizen/browser.git
cd browser
./install.sh
```

The script installs the one dependency (PyQt6 WebEngine — via dnf, apt,
pacman, or pip, whatever your system has) and adds **Browser** with its icon
to your app menu.

No install, just run it:

```sh
python3 browser.py
```

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+T` | New tab |
| `Ctrl+W` | Close tab |
| `Ctrl+L` | Jump to address bar |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Next / previous tab |
| `Ctrl+R` / `F5` | Reload |
| `F11` | Fullscreen |
| `Ctrl+Q` | Quit |

## Make it yours

Everything lives in two readable files:

| File | What it is |
|------|------------|
| `browser.py` | The whole browser — window, tabs, address bar, suggestions. Colors are plain CSS-like rules in the `STYLE` string at the top. |
| `start.html` | The start page — a single ordinary HTML file. Edit it like any web page. |
| `backgrounds/` | The bundled background photos. Drop in more if you like. |

The look is based on [Catppuccin](https://github.com/catppuccin/catppuccin) Mocha
colors: base `#11111b`, surface `#1e1e2e`, accent `#89b4fa`.

## Uninstall

```sh
rm -rf ~/.local/share/applications/browser.desktop \
       ~/.local/share/icons/hicolor/scalable/apps/browser.svg
```

…then delete the cloned folder. Browsing data (cookies, storage) lives in
`~/.local/share/browser/` if you want that gone too.
