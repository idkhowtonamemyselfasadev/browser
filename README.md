<div align="center">

# browser

**A keyboard-driven web browser in a single Python file.**

Built on Chromium through Qt WebEngine. 116 themes that recolour the websites as well as
the window, six interface looks, per-site proxy routing, and no telemetry of any kind.

[![Licence: GPLv3](https://img.shields.io/badge/licence-GPLv3-5c7cfa?style=flat-square)](LICENSE)
[![Python 3](https://img.shields.io/badge/python-3-9bb1ff?style=flat-square)](https://www.python.org/)
[![Engine: Qt WebEngine](https://img.shields.io/badge/engine-Qt%20WebEngine-74c7ec?style=flat-square)](https://doc.qt.io/qt-6/qtwebengine-index.html)
[![Telemetry: none](https://img.shields.io/badge/telemetry-none-a6e3a1?style=flat-square)](#overview)
[![Linux](https://img.shields.io/badge/linux-%E2%9C%93-cba6f7?style=flat-square)](#install)

![The browser darkening Wikipedia](screenshots/dark-mode.png)

<sub>Wikipedia ships no dark theme of its own; the browser applies one.</sub>

</div>

---

## Overview

- **A single file.** The whole application is `browser.py`. No build step, no plugin
  framework and no dependency tree to audit: edit it, restart, and the change is live.
- **116 themes, applied to the web as well.** Choosing Gruvbox recolours more than the
  tabs: the websites are rendered in the same palette. A single setting turns that off.
- **Six interface looks.** A theme decides what colour the browser is; a look decides
  what shape it is. Classic, Taskbar, Dock, Circle, Liquid Glass and Flat mono, each of
  which works with all 116 palettes.
- **An address bar that computes.** `12*64+3`, `5 in to mm`, `200 c to f`,
  `days until 24.12.`, `time in tokyo`. Everything is evaluated locally; no query leaves
  the machine.
- **Virtual browsers.** Independent sessions within one window, each with its own cookie
  jar, so two accounts on the same site can be signed in at the same time.
- **A password manager that asks which account to use** before filling anything, and
  withholds the stored password from page scripts until the form is genuinely clicked.
- **Per-site proxy routing that fails closed.** A rule pointing at an unreachable proxy
  blocks the site rather than silently connecting directly.
- **No telemetry, no account, no sync.** All data remains in `~/.local/share/browser/`.

## Install

```sh
git clone https://github.com/idkhowtonamemyselfasadev/browser.git
cd browser
./install.sh
```

`install.sh` installs PyQt6 WebEngine through your package manager (dnf, apt or pacman,
with pip as a fallback) and registers a desktop entry with an icon.

To run it without installing:

```sh
python3 browser.py
```

**Requirements:** Python 3 and PyQt6 WebEngine.

Encrypted streams (Netflix, Spotify, Amazon Music) also play: if Chrome is present, the
browser locates its Widevine module and points the engine at it. Nothing is downloaded or
installed, and an absent Chrome means only that DRM-protected media will not play.

## A closer look

### 116 themes, and the websites wear them too

![Twelve of the 116 themes](screenshots/themes.png)

Twelve of them. Settings → Theme has the other 104, searchable, each shown as a swatch
of its own colours and applied on the spot — no restart, and open tabs change with it.
Most are credited palettes; a few, like the last three above, bring a face and a texture
of their own.

### Six looks

A theme decides what colour the browser is; a look decides what shape it is. Every look
works with all 116 palettes, because a look defines geometry only and never a colour.

| Classic | Taskbar |
|:--|:--|
| ![Classic](screenshots/look-classic.jpg) | ![Taskbar](screenshots/look-taskbar.jpg) |
| The browser as it is drawn — the default. | A strip along the bottom with a start button, the pinned sites and a clock. |
| **Dock** | **Circle** |
| ![Dock](screenshots/look-dock.jpg) | ![Circle](screenshots/look-circle.jpg) |
| A floating dock over the page with icon magnification, and a now-playing widget that works the transport of whatever is making the sound. | The start page becomes a ring: search in the middle, the quick links orbiting it, turned by the mouse wheel. |
| **Flat mono** | **Liquid Glass** |
| ![Flat mono](screenshots/look-flat.jpg) | Frosted, translucent chrome: the wallpaper shows softly through the tabs, the toolbar and the menus. Best seen running — a still of it is just the Classic shape. |

### Dark by default, not by filter

![Automatic dark mode](screenshots/dark-mode.png)

Sites that ship a dark theme are asked for it. Light-only sites are darkened
automatically. Sites that are already dark are left untouched, which keeps heavy pages
fast.

### The whole bookmark tree in one panel

| Favourites | Dragging one in |
|---|---|
| ![Favourites](screenshots/favorites-panel.png) | ![Dragging](screenshots/favorites-drag-into.png) |

`Ctrl+Shift+F`, or the folder in the toolbar: a search box at the top and one list
underneath, with folders opening in place rather than as fly-out submenus. Folders nest
to any depth. A row can be dragged into a folder, out of one, or between two to reorder
it; **Move to folder** on the row's `⋯` menu does the same without dragging.

### The account chooser

![The account chooser](screenshots/account-chooser.png)

When two accounts are saved for a site, nothing is filled in until one is chosen
(`Ctrl+Shift+M`, or the `@` in the address bar). The list is rendered by the browser
itself: the page cannot see it and never learns what it contains.

### A configurable start page

![Start page](screenshots/start-page.png)

A clock, a search field, editable quick links and background images of your own. The
quick links are the pinned sites: pinning from a page's context menu, from the taskbar's
`+`, or here all write to the same list, and clicking a pin brings its existing tab
forward rather than opening a second one.

## Features

<details>
<summary><b>Tabs, windows and navigation</b></summary>

- **Tabs and tab groups** — Chrome-style group pills, collapsible, colour-coded
- **Split view** — two pages side by side in one window, optionally scrolled together
- **A relocatable tab strip** — along the top, below the page, or **down either side
  as a sidebar** (`F9`): the tabs become a list of rows with the titles readable, the
  group pills folding in place, drag-to-reorder and a cross on the row under the
  pointer. `Shift+F9` folds it to 46 pixels of favicons. The width is a splitter
  handle. Along the top it can also run in up to four rows rather than scrolling
- **Workspaces** — named sets of tabs within one window; the outgoing set is saved
  before the incoming one opens, so switching between them preserves both
- **Virtual browsers** — several independent sessions in one window, each with its own
  cookie jar and logins; sign in to the same site twice without signing out
- **A side panel** (`Ctrl+Shift+Y`) holding any site beside the page (Discord, Amazon
  Music, Twitch chat and so on) as a real view on the same cookie jar, already signed in
- **A command palette** (`Ctrl+Shift+K`) and a **cheat sheet** (`Ctrl+/`); every
  shortcut can be changed in Settings
- **Tab search** (`Ctrl+Shift+A`) — every open tab of every virtual browser in one
  filtered list
- **Reopen closed tab** (`Ctrl+Shift+T`) — restores its position *and* its group;
  **Recently closed** in the tab menu lists the last 25, not only the last
- **A full tab context menu** — pin it (it shrinks to its icon, keeps its place across
  restarts and can be held to its own site), mute it (`Ctrl+M`) or play sound only
  here, lock it so it asks before closing, rename it so the page cannot change the
  title, duplicate it (`Ctrl+Shift+D`), open it in another virtual browser or in a
  private tab, copy the addresses of one tab or all of them (plain or Markdown), open
  every address in the clipboard, bookmark every tab into one folder, sort the tabs by
  site or title, group or close every tab of this site, close the others / to the
  right / to the left / the duplicates
- **A call indicator** — a tab using the microphone or camera is flagged, so it is clear
  which one is listening
- **A resource monitor** (`Ctrl+Shift+Esc`) — memory and processor use, per tab
- **Fullscreen video**, background tabs, sleeping tabs restored on demand

</details>

<details>
<summary><b>The address bar</b> — calculation, keywords, suggestions, clean links</summary>

- **Calculation and conversion** — `12*64+3`, `5 in to mm`, `200 c to f`, `4 gib to mb`,
  `time in tokyo`, `kw`, `days until 24.12.`, `#ff8800`. All worked out on this
  machine, with nothing sent anywhere; Enter copies the result
- **Search keywords** — `yt cats`, `mr sodium`, `gh repo`, `amz ssd`, `w term`; custom
  ones are defined in Settings as any URL containing `%s`
- **Local suggestions** — an open tab (Enter switches to it), a bookmark, or a page from
  your history matched on words in any order; an empty bar offers a recently copied link
  and your last searches
- **Copy clean address** — the same link without `utm_*`, `fbclid` and the rest of the
  tracking, also as a Markdown or HTML link, or "Title — address"
- `Ctrl+Enter` / `Ctrl+Shift+Enter` finish a bare name with `.com` / `.de`;
  `Shift+Delete` forgets a suggestion

</details>

<details>
<summary><b>Reading, media and gaming</b></summary>

- **Reader mode** (`Ctrl+Alt+R`), **link hints** (`Ctrl+Alt+K`), **read aloud**
  (`Ctrl+Alt+V`), and highlights that come back on the next visit
- **Game mode** (`Ctrl+Alt+G`) — suspends every other tab, mutes all audio and refuses
  notification requests; pressing it again wakes exactly those tabs
- **Screenshots** (`Ctrl+Shift+S`, the whole page with `Ctrl+Alt+Shift+S`) with password
  fields blurred before the shutter
- **Save any image** — right-click → *Save image* operates on whatever is drawn under
  the cursor: a picture under an overlay, a `<picture>`, a video poster, a CSS background,
  an inline SVG, a canvas. `Shift` + right-click brings the menu up on sites that block it
- **Minecraft server status** (`Ctrl+Alt+J`) — queries your servers with the same
  protocol request the game's own server list uses
- **Media keys** control the page's player, and the video has its own shortcuts
  (`Ctrl+Alt+Space`, `Ctrl+Alt+←/→`); `Ctrl+Shift+Space` pauses every playing tab at once
- **Page zoom from the keyboard** — `Ctrl` `+` / `Ctrl+-` / `Ctrl+0`, and `Ctrl`+wheel,
  per tab, 25 % to 500 %

</details>

<details>
<summary><b>Themes</b> — how site theming works</summary>

**Websites are themed as well as the window.** Every page is recoloured in the selected
palette, and the character themes bring their own typography and texture (Terminal glows,
Newspaper sets in serif). This is on by default; Settings → Appearance → *Theme websites*
disables it, and right-click → *Don't theme this site* exempts a single site. Sites that
are dark by design are left alone, and a themed page is never darkened twice.

The palettes live in `_CATALOGUE` in `browser.py`: one row of colours each, so adding
your own is a row rather than a stylesheet.

</details>

<details>
<summary><b>Privacy and security</b> — vault, proxy rules, permissions, trust boundary</summary>

- **Vault Password** — the built-in password manager, and optional: setup asks whether
  you want it, and Settings → Plugins switches it at any time. Off means off — the login
  watcher is never injected into a page, so no form is inspected and nothing is written
  to the vault. Disabling it deletes nothing; stored logins return when it is enabled
  again. While enabled, it offers to save logins and fills them on a genuine click, and
  withholds the stored password from page scripts until the form is actually interacted
  with, so an injected script reads an empty field.
- **Per-site proxy routing** — send chosen sites through a proxy while everything else
  goes direct, or the reverse. Enforced by a built-in local proxy and **fails closed**:
  a rule pointing at a dead proxy blocks the site rather than quietly going direct.
- **Site permissions** — microphone, camera and notification requests are asked per
  origin and remembered per origin, scheme and port. A denial can be revised later.
- **Private tab** (`Ctrl+Shift+N`) — leaves nothing behind: no history, no saved password
  and none offered, no download record, no favicon kept, and no cookies or site storage
  once the last one closes. Never saved as a tab, never restored at the next start. Two
  private tabs share one place; a normal tab sees none of it.
- **Panic** (`Ctrl+Alt+P`) — mutes all audio, blanks every tab and locks the vault.
  **Streamer mode** (`Ctrl+Alt+H`) hides the address bar's text.
- **History control** — pause it, search it, or clear it.
- **Trust boundary** — the browser's own pages get a privileged bridge to the
  application; websites never do, and cannot reach it through the underlying channel.

</details>

<details>
<summary><b>Downloads, printing, setup and configuration</b></summary>

- **Download manager** — a downloads page and a toolbar bar with progress, speed and
  time remaining; pause, resume, cancel; history that survives restarts
- **Print or save as PDF** (`Ctrl+P`) — the PDF lands in the downloads list with
  everything else
- **Graphics card selection** — on a machine with two GPUs the system's default is not
  always the faster one. A chooser shown before startup lists every card, marks the one
  the system boots on, and relaunches the browser with the environment that choice
  requires, because the engine's GPU is fixed when its process starts
- **Setup** — a seven-step first run: language, search engine, start page, site
  behaviour, privacy, quick links, summary. Re-runnable at any time
- **Settings** — opens as a pane over the window rather than a page you navigate to, so
  it costs no tab and no history entry
- **A toolbar you pick** — right-click the top row, or Settings → Toolbar, to choose
  which buttons are up there and in what order. Back, forward, reload and the address bar
  stay; everything else is yours, and eight more buttons that were only ever keyboard
  shortcuts can join them. Taking a button away never touches its shortcut
- **Userscripts** — Greasemonkey-style `*.user.js` files, per profile
- **Interface translations** — the UI follows the language you choose
- **Single instance** — links from other applications open as tabs in the running
  window; works as the system default browser
- **Built-in updates** — fetches the newest version from this repository, and refuses to
  proceed where that would discard uncommitted work

</details>

## Keyboard shortcuts

Shortcuts are handled by the browser itself, so they behave identically on any desktop or
window manager with no system configuration. All of them can be reassigned in Settings,
and `Ctrl+/` shows the complete list on a page.

| Key | Action |
|-----|--------|
| `Ctrl+T` / `Ctrl+W` | New tab / close tab (a pinned tab stays) |
| `Ctrl+Shift+N` | New private tab |
| `Ctrl+Shift+T` | Reopen closed tab |
| `Ctrl+Shift+K` | Command palette — every action by name |
| `Ctrl+Shift+Y` | Side panel — any site beside the page |
| `Ctrl+L` / `Ctrl+K` | Focus the address bar / ready for a search |
| `Ctrl+F` | Find in page |
| `Ctrl+Shift+A` | Search open tabs |
| `Ctrl+Shift+F` | Favourites — the whole bookmark tree in one panel |
| `Ctrl+Shift+M` | Choose which saved account signs in here |
| `Ctrl+Alt+R` | Reader mode |
| `Ctrl+Alt+G` | Game mode |
| `Ctrl+,` | Settings |
| `Ctrl+/` | Every shortcut, on one page |

<details>
<summary>The full list</summary>

| Key | Action |
|-----|--------|
| `Ctrl+Shift+D` | Duplicate tab |
| `Ctrl+Shift+Esc` | What the tabs are costing |
| `Ctrl+Alt+U` | Your own CSS for this site |
| `Ctrl+Alt+J` | Minecraft server status |
| `Ctrl+Alt+Q` / `Ctrl+Alt+Y` | Discord mute / deafen |
| `Ctrl+Alt+K` | Link hints — a letter on every link |
| `Ctrl+Alt+V` | Read the selection aloud |
| `Ctrl+Shift+S` | Screenshot of what is on screen |
| `Ctrl+Alt+Shift+S` | Screenshot of the whole page |
| `Ctrl+Alt+P` | Panic: mute everything, blank every tab, lock the vault |
| `Ctrl+Alt+H` | Streamer mode: hide the address bar's text |
| `Ctrl+Alt+Space` / `Ctrl+Alt+←→` | Play/pause / seek the page's video |
| `Ctrl+Shift+Space` | Pause every playing tab (again: resume) |
| Middle-click Back / Forward | That step, in a new tab |
| Hold Back / Forward | That tab's history, several steps at once |
| `Ctrl+M` | Mute / unmute this tab |
| `Ctrl+1` … `Ctrl+8` / `Ctrl+9` | Go to that tab / the last tab |
| `Ctrl+Shift+PgUp` / `PgDn` | Move this tab along the strip |
| `Alt+Enter` (in the bar) | Open what you typed in a new tab |
| `Ctrl+Enter` / `Ctrl+Shift+Enter` | Finish the name with `.com` / `.de` |
| `Shift+Delete` (in the bar) | Forget that suggestion |
| `Ctrl+P` | Print or save as PDF |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Next / previous tab |
| `Shift+Tab` | Next virtual browser |
| `Ctrl+R` / `F5` | Reload |
| `Ctrl+H` / `Ctrl+J` | History / downloads |
| `Ctrl+Shift+O` | Bookmarks |
| `Ctrl+Shift+B` | Bookmarks bar on / off |
| `Ctrl+Shift+P` | Passwords (with Vault Password installed) |
| `Ctrl+Shift+G` | Copy a fresh password to the clipboard |
| `Ctrl+` `+` / `Ctrl+-` / `Ctrl+0` | Zoom in / out / back to the level in Settings |
| `F9` / `Shift+F9` | Tabs down the side / fold the sidebar to icons |
| `F11` | Fullscreen |
| `F12` / `Ctrl+Shift+I` | Developer tools |
| `Ctrl+Q` | Quit |

</details>

Settings, History, Downloads, Bookmarks and Passwords are **panes, not tabs**: they open
over the current page, `Esc` (or the same shortcut again) closes them, and the page
underneath returns. They never appear in the tab strip or the address bar, and are never
restored as tabs at the next start.

## Configuration and data

Most settings live in the settings pane (`Ctrl+,`) and are stored in
`~/.local/share/browser/config.json`. Anything beyond that is intended to be changed in
the sources:

| Path | Contents |
|------|----------|
| `browser.py` | The application. Interface colours are in the `STYLE` string, the palettes in `_CATALOGUE`, and sites that skip auto-darkening in `NATIVE_DARK_SITES`. |
| `start.html` | Start page and first-run setup. |
| `settings.html` | Settings pane. |
| `history.html`, `downloads.html`, `bookmarks.html`, `passwords.html` | The other four panes. |
| `backgrounds/` | Bundled background images. |

User data — history, settings, saved logins, downloads and cookies — is stored under
`~/.local/share/browser/`. Saved passwords are obfuscated with a per-install key file;
the security boundary is the operating system account, not a master password.

## What the in-browser pages need from `browser.py`

The nine pages the browser serves itself — `start`, `history`, `downloads`,
`bookmarks`, `notes`, `passwords`, `settings`, `player`, `mictest` — are copied
into the Windows and macOS editions and ported
back from here, and `~/claude/browser-pages` keeps them in step. It carries
**HTML only** — so a page that starts calling a new `Bridge` method has a
dependency the manifest cannot see, and the port leaves that method undefined.
A `TypeError` inside a channel callback then abandons the rest of it, which
looks exactly like a page that loaded and drew nothing. That is how
`history.html` nearly shipped blank on Windows after an otherwise correct port:
the page needs `Bridge.siteIcons` and `Browser.site_icon_data`, and neither
travelled with it.

So: **changing a shared page to call a new bridge method is a change to this
table too.** 94 distinct methods across the nine pages as of 2026-10-28.

| Page | Bridge methods it calls | Not in `browser.py` |
|------|------------------------:|---------------------|
| `start.html` | 12 | — |
| `history.html` | 14 | — |
| `downloads.html` | 10 | — |
| `bookmarks.html` | 10 | — |
| `notes.html` | 3 | — |
| `passwords.html` | 22 | — |
| `settings.html` | 33 | — |
| `player.html` | 4 | `playerQueue`, `playerSubtitles` — guarded, and the feature is dead until it exists |
| `mictest.html` | 1 | — |

Ask for an optional one the way the pages already do — `if (bridge.x) { ... }`.
An unguarded call to a method that is not there throws, and an uncaught throw
in an inline script abandons every statement below it. `test_histrender.py`
catches that shape for `getElementById`; nothing yet catches it for the bridge,
so it is a review question.

**A method is not the only dependency.** `settings.html` calls two methods for
every one of its switches — `getSettings` and `setSetting` — so a new setting
adds no row to the table above and is still a change to this contract: the
*key* has to be in what `getSettings` answers, and `setSetting` has to route it
somewhere. The tab-sidebar picker added on 2026-10-29 needs `tabStrip` and
`tabStripWidth` in both. Ported into a tree without them, the picker draws, it
highlights the card that was clicked, it saves a config key nothing reads — and
nothing happens. That is quieter than a `TypeError` and harder to spot, so a
port of `settings.html` is finished when the new control has been *used*, not
when the page has loaded.

## Automation: the agent bridge

While the browser runs it listens on a second local socket, `$TMPDIR/browser-agent`
(`/tmp/browser-agent`); `agent.py` is the command-line client. A script can open a
background tab, read a page, click, type, wait for a node and capture a screenshot, all
on tabs that are not in front and **without the window ever being raised**. The purpose
is to let a local assistant use the web without taking over the screen.

```sh
python3 agent.py tabs                      # what is open
python3 agent.py open https://example.org  # background tab; prints its id
python3 agent.py text --tab 7              # the page as text
python3 agent.py click 'button.go' --tab 7
python3 agent.py type '#q' hello --enter --tab 7
python3 agent.py shot /tmp/page.png --tab 7
```

The socket is a Unix socket owned by your user account and is not reachable from the
network. It is disabled with `"agentBridge": false` in `config.json` or
`BROWSER_NO_AGENT=1`. `test_agent.py` is its offscreen test.

<details>
<summary><b>Security updates</b> — the monthly engine check, and how to act on it</summary>

Most of what can go wrong in a browser goes wrong in the engine, and the engine here is
Chromium inside Qt WebEngine. A scheduled job on GitHub therefore watches it. Nothing runs
on your machine and nothing is sent anywhere.

**On the first of every month** (GitHub cannot say "every five weeks", so this is the
closest it gets) a job runs and asks:

- which Chromium this browser is built on, and how far behind Google's current Chrome
  that is
- whether any Chrome holes *known to be used against people in the wild* are newer than
  that engine — the short list CISA publishes, not the thousands of theoretical ones
- whether a newer PyQt6 or PyQt6-WebEngine has been released
- whether the browser's own security checks still pass

**If there is nothing to do, it reports nothing.** No issue, no mail. That is the normal
outcome and it is deliberate: a check that notifies every month is a check that gets
ignored. The full report is always written to the run's summary page under the Actions tab
if you want to read it anyway.

**If there is something to do, it opens a single issue** titled "Browser security check"
and edits that same issue thereafter, so duplicates never accumulate. When the problem is
resolved it comments and closes the issue itself.

### What to do when an issue appears

The first section states which of the following cases applies:

- **"PyQt6-WebEngine x.y.z is out"** — the case that matters. Update the engine on
  your machine (`sudo dnf upgrade python3-pyqt6-webengine`, or whatever your distribution
  calls it) and merge the Dependabot pull request that bumps the pinned version here.
- **"The browser's own security checks are failing"** — a recent change has broken a
  protection that was previously fixed. The issue names the check; run
  `python3 .github/scripts/invariant_checks.py` to see it locally.
- **"N Chrome holes known to be exploited are newer than this engine"** — informational,
  and usually requires no action. Qt ships its own Chromium snapshot and backports
  security fixes into it, so it is always a few versions behind Chrome by design. Taking
  the next engine update promptly is the appropriate response.

To see which engine your own machine is running:

```sh
python3 -c "from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion as v; print(v())"
```

### Dependabot and pull-request checks

**Dependabot** opens a pull request when PyQt6, PyQt6-WebEngine or one of the workflow
actions has a new release. Merging it is the update.

**Every pull request** runs the security checks, so a change that breaks one cannot merge
without a red cross. They also run by hand:

```sh
python3 .github/scripts/invariant_checks.py
```

They start a headless browser against a throwaway profile — your real history, logins and
settings are never touched — and check that a website cannot reach the browser's internal
bridge, that the download and bookmark controls refuse a page that does not hold this
run's key, that a saved password stays out of the page until a real click, that
permissions are remembered per site *and* port, and that a site routed through a proxy
that is down gets blocked rather than quietly connected.

One caveat: **GitHub disables scheduled jobs on a repository with no activity for 60
days**, and sends a mail when it does. Any push re-enables them, as does pressing "Run
workflow" on the Actions tab.

</details>

## Windows

A Windows edition with the same feature set is maintained at
[idkhowtonamemyselfasadev/browser-windows](https://github.com/idkhowtonamemyselfasadev/browser-windows).

## Uninstall

```sh
rm ~/.local/share/applications/browser.desktop
rm ~/.local/share/icons/hicolor/scalable/apps/browser.svg
```

Browsing data in `~/.local/share/browser/` can be removed separately. Deleting the cloned
repository completes the removal.

## Licence

[GNU General Public License v3](LICENSE).
