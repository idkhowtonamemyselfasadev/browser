# Changelog

## 2026-10-22 (night) — the decoder goes with the card

Second correction, found while telling him to use it: **"let the system
decide" was taking hardware decoding away.** It cleared
`LIBVA_DRIVER_NAME` along with the variables the chooser had set — but
that one is not the chooser's to clear: the browser's own start-up line
sets it when an NVIDIA driver is installed, and wiping it leaves a
machine that had hardware decoding without it. Automatic now clears
only the five it set itself, and only a chosen card replaces the
decoder.

Reported straight after the chooser landed: YouTube **live** streams
come out black while ordinary videos play. The browser's own start-up
code sets `LIBVA_DRIVER_NAME=nvidia` whenever an NVIDIA driver is
installed — right while NVIDIA is also drawing, and wrong the moment
another card is chosen: the frames are then decoded on one card and
composited on another, which is a black rectangle with the sound still
playing, and it shows on a hardware-decoded live stream long before it
shows on a short clip.

The chosen card now carries its decoder with it (`nvidia`, `iHD`,
`radeonsi`), and "let the system decide" puts that back in the
machine's hands as well.

## 2026-10-22 (night) — which graphics card draws the pages

A machine with two cards hands the browser whichever one the system
feels like, and on his (an RTX 5080 beside the processor's own Intel
graphics) the quiet one is the laggy one.

**A window before the browser starts.** It lists every card this
machine has — read out of `/sys/class/drm`, with the names from
`lspci` where it is installed and the PCI ids where it is not — marks
the one the system boots on, and offers "let the system decide" beside
them. Picking one starts the browser again with the environment that
choice needs, because which card the engine uses is decided when its
GPU process starts, long before any window of ours exists: pretending
a change took effect later would be a lie.

- NVIDIA gets the PRIME offload trio (`__NV_PRIME_RENDER_OFFLOAD`,
  `__GLX_VENDOR_LIBRARY_NAME`, `__VK_LAYER_NV_optimus`) and its slot in
  `DRI_PRIME`; Mesa cards get `DRI_PRIME` and `MESA_VK_DEVICE_SELECT`;
  "let the system decide" takes all of them off again rather than
  leaving the last answer behind.
- The window is plain Qt widgets on purpose — no engine behind it, or
  the GPU process would already have started before the question was
  answered — and it wears the browser's own colours.
- **It is the browser that asks, not every launch.** A link handed over
  from Discord to a browser that is already running must not put a
  window in anyone's way, so the question waits until this process has
  claimed the single-instance socket, and gives that socket up before
  restarting itself. A card already chosen is applied at import, before
  Qt, asking nothing.
- One card is not a question: a machine with a single GPU is never
  asked.
- Settings → What this is costing has the card picker and an "ask at
  every start" switch, both of which say they take effect at the next
  start.

New `test_gpu.py`, 44 checks, against a `/sys/class/drm` of its own so
two cards can be measured on a machine that has one. **What this box
cannot prove: that the 5080 really takes the work.** It has one Intel
card, so the reading, the listing, the environment, the window and the
paths that do not ask are measured here; that the choice moves the
rendering is for his machine to show.

## 2026-10-22 (evening) — Settings: the rail back, with ten shelves on it

He did not like what the page became. The tiles, the chip strip across
the top, the twelve merged sections and the search box that took the
keyboard are all out, and the page is the one he had before them: the
rail down the side with all 25 sections under their own names.

What the rail gained instead is **ten shelves rather than four**.
"General" with seventeen sections under it said nothing; now the rail
reads **Finding things** (search, the address bar, getting around),
**Tabs and windows**, **Looks** (appearance, toolbar, theme, look),
**Reading and media**, **Notes, capture and downloads**, **Games and
streaming**, **Keys and the mouse**, **Privacy**, **Advanced** and
**The browser**. Both names of each are in English and German, and
test_setpage.py checks that the rail has more than the four it had,
that each shelf is named in both languages, and that none of them is
empty.

Everything else from earlier today stays: no section listed twice, the
switches that shared an id work, the see-through cards, and "carry on"
and the search history gone.

## 2026-10-22 — Settings: the whole page, nothing listed twice, see-through

**Twenty-four sections became twelve.** The navigation was never really
the problem: the count was. "Browsing", "Tabs", "Getting around",
"Reading a page", "Appearance", "Theme", "Look" and "Toolbar" were not
obviously different places to someone looking for one switch. They are
**Search and the address bar**, **Tabs and windows**, **Looks**,
**Reading and media**, **Keys and the mouse**, **Notes, capture and
games**, **Downloads**, **Privacy**, **Passwords**, **What this is
costing**, **For developers** and **The browser itself**. Nothing was
dropped; the cards moved. The count on each tile is the settings in it,
not the settings plus every choice in a picker.

**The search box has the keyboard from the first frame**, because typing
the name of a setting is the fastest way to it, and it is bigger now.

**A new way around it.** The sidebar is gone. Settings opens on a page
of tiles -- one per section, each with the line that says what is in it
and how many settings that is, under the four group headings -- and the
strip along the top carries the sections of the group you are in — its
neighbours, not a wall of all of them — and is out of the way
altogether while the tiles are up. A tile or a chip opens a section;
"All settings", the name in the corner and Escape come back to the
tiles.

**It uses the window now.** Settings was one 880px column down the middle
of a window twice that wide: two thirds of the page was empty, and a
section like Browsing was a mile of scrolling through a one-card-wide
stack. The cards of a section now flow into as many columns as the
window has room for — one on a phone, two on a laptop, three or four on
a big monitor — each card keeping a readable width, so a switch still
sits beside its own label. A shelf of pickers (the themes, the search
engines, anything with four choices or more) spans the lot. The rail is
narrower, the title block is one line instead of three, the rows are
tighter, and on a phone the rail becomes a strip across the top so the
settings get the whole width.

He opened Settings and found two sections called "The address bar", one
under the other. Pulling on that thread found the rest:

- **The duplicated section is gone.** It was a whole copy — markup,
  the JavaScript that fills it and the JavaScript that binds it — which
  is where **66 duplicated element ids** in one page came from. Zero now,
  and `test_setpage.py` keeps it that way.
- **Two switches that shared an id, so one of them did nothing.**
  "Pause animations in tabs nobody is looking at" and "Pause a video
  when its tab is hidden" were both `id="pausehidden"`; the first one
  the page found got the binding and the second was a dead control.
- **A switch that was quietly eating a list.** The never-sleep site
  list and the "keep the screen awake while a video plays" switch were
  both written to the config key `keepAwake` — a list and a boolean in
  one key, in the page *and* in the browser. The switch is `screenAwake`
  now, the list keeps `keepAwake`, and a config written by the old
  version hands the boolean over on the way in.
- **Eighteen headings were never translated**, because the map that
  translates them had never been told about them: in German the rail
  came out half in English. All eighteen are in the map.
- **"Browsing" was a dumping ground** — 23 cards and 128 rows, with
  cards named after other sections — while "Downloads" held two rows.
  The cards now sit where their names say: new **Tabs**, **Video and
  sound** and **Notes and tools** sections, keyboard shortcuts with the
  keys, the screenshot card with recording, both privacy cards (named
  apart: "Trackers and the home network", "Connections") under Privacy,
  and the two download sections merged into one.
- **The tab-click settings were offered twice** — a dropdown under Keys
  and the mouse and a card picker under Browsing, both writing the same
  setting. One place now, with the other tab settings.
- **You can see the window through it.** The rail, the search strip and
  every card are the palette's own colours at an alpha over a blur, and
  under the glass look the page itself goes see-through: one of the
  browser's own pages now asks the engine to paint no base colour
  behind it, so the translucent window reaches the desktop. Every
  colour is still a palette literal, so all 114 themes repaint exactly
  as before — `test_contrast.py` measures them.
- **Removed, by request: "carry on where you left off."** The row on
  the start page, the switch that offered it, the code that worked it
  out and its strings are all out, rather than switched off.
- **Removed, by request: the search history.** "If I click [the bar] I
  don't want to see what I have searched — I know what I search." So:
  the last-searches list an empty address bar offered, the searches
  page behind `searches.html`, the "Searches" view on the history page,
  the log that fed them, both switches in Settings and every string
  they used are out. A config that still holds `searchLog` /
  `recentSearches` has them dropped the first time this version reads
  it — the list is not kept, not merely hidden. An empty bar still
  offers a link sitting on the clipboard.
- **The tab-strip clicks existed twice, and Settings wrote to the dead
  one.** `mouse.tabDouble`, `mouse.tabMiddle` and `mouse.barDouble`
  were read by two methods nothing ever called; the strip's own event
  filter has always read `tabDoubleClick`, `tabMiddleClick` and
  `stripDoubleClick`. So whatever he picked in those three dropdowns
  never happened. The dead half is gone, and what he had picked is
  handed to the settings that work.

## 2026-10-18 — catching up to live, and six tests that were owed

- **Catching up to a live stream** instead of jumping to its edge: a
  stream he is behind on plays at 1.1x until he is level, then goes
  back to normal. Driven by the page's own `timeupdate`, so there is no
  timer of the browser's in front of a stream. (The jump to the edge
  was already there; this was the other half of that feature, and it
  had been missed.)
- Six features that were built but had no test naming them now have
  one: mute every tab, the wheel over a video, finding the tab that is
  making a noise, no autoplay-next, "show in folder" when a download
  finishes, and a capture a few seconds from now.
- Fixed: the QR dialog's copy button read "barCopyAddress" — a string
  key used in the code and never defined, so it printed its own name.
  Both of the two such keys are defined now, in both languages, and
  the whole table was checked: 3124 keys, nothing used that is not
  there, nothing in one language missing from the other.

## 2026-10-18 — the ones that were written off too early

Seven features in this browser's backlog were skipped earlier in this job
because a Python object handed to the engine was measured taking the
process down at exit. Those measurements were re-run, one at a time, with
and without: **none of the three mechanisms crashes**, and all three are
really consulted. So the features they blocked are built, and the one
real condition the old measurement had half-found is handled.

- **An ad and tracker blocker** (new `adblock.py`): EasyList-format
  lists, read from a folder of his own. `||host^`, `$third-party`,
  `$domain=`, type options, `@@` exceptions, `##` hiding and `#@#`
  unhiding; rules are indexed by host, so a request asks for its own
  host and its parents rather than walking a hundred thousand rules.
  Per-site off switch. **What these lists ask for that this does not do
  — regular-expression rules, `$redirect`, `$csp`, extended selectors —
  is counted and shown**, because a blocker that silently ignores a
  third of a list is worse than one that says so. Fetching lists is
  opt-in, on request, and shows up in the browser's own connection log.
- **Cookies from other sites can be refused**, with per-site exceptions
  for the sign-ins that go through somewhere else. One thing measured
  the hard way: `setCookieFilter(None)` does *not* take a filter off —
  the engine calls the None back and the process dies — so "off" is a
  pass-through function.
- **Mouse gestures, the rocker and buttons 4 to 9.** Right-drag:
  left is back, right forward, up reload, down a new tab, down-right
  closes one, up-down brings one back, all of it re-mappable. Right
  held + left click is back, left held + right click is forward, right
  held + the wheel walks the tabs. The trail is drawn in the page,
  because a widget over the view would take the mouse. The one real
  condition: an event filter left on the engine's widget **does**
  segfault at interpreter exit, so it is taken off in
  `_release_engine_hooks`, which atexit calls however the process ends.
- **Alt+click on a link saves it** — which needed none of that: the
  modifier is still held when the navigation arrives, so the navigation
  request is the honest place to ask. The old skip measured the wrong
  mechanism.
- **A key in the address bar** on a site he has a login for: fill it,
  copy the password (the clipboard is cleared a minute later) or open
  the entry. The old note said there was nowhere in this chrome for it;
  there is — it rides inside the bar exactly as the star and the copy,
  clear and QR buttons do.
- Fixed: a group's header in front made every keyboard shortcut raise
  `AttributeError` in `key_allowed_here` — a header is a tab with no
  `url()` — and an exception inside a Qt slot ends the process.
  `test_navguard.py` had been aborting on it.
- Fixed: the most-recently-used tab order kept Python wrappers round
  closed tabs and asked the strip about them, which raises — and an
  exception inside a Qt slot ends the process. `test_tabwork2.py` had
  been aborting on it. Dead rows are dropped now.

One more line was listed as something to build and skipped as "the
engine already does it" — **the scroll kept across a reload**. It is
marked done now, with a check that measures it instead of assuming it:
1500 px kept, even on a page whose own `onload` scrolls back to the top.

The blocker also had to be made fast enough to stand in front of every
request a page makes. Walking every rule costs **17 ms per request** on
a 50,000-rule pair of lists; rules are indexed by the longest word they
must contain and an address is looked up by the words in it, which
brings that to **0.014 ms** with the same answers.

Twelve features are still skipped, each with the measurement that says
why: picture-in-picture is switched off in this engine build (re-measured
today), a user agent belongs to a cookie jar rather than a tab, Argos
Translate and LanguageTool would be new dependencies, the engine offers
no codec preference and no byte ranges on its own downloads, there is no
`clearHttpAuthenticationCache` on this build, the screen-share picker
never sees tabs, and the desktop portal has no GlobalShortcuts here.

## 2026-10-18 — the last of the list

- **What the browser itself sends**, written down: suggestions as he
  types, the update check, a favicon, a list refresh. One manager
  handles every connection the browser makes for itself and a page's
  own traffic never goes through it, so this is a complete answer to a
  question no browser answers. A switch, and the reason each
  connection was made.
- **Which userscripts ran on this page**, and what each one is really
  allowed to do — read out of its own header and matched with the same
  pattern function that decides whether it runs, so the audit cannot
  disagree with the browser.
- **A window through Tor**, if Tor is listening: its own process, its
  own data, its own door, everything in it through the SOCKS port.
  Honestly a window and not a tab, because Chromium reads its proxy
  from the flags it was launched with.
- **A page that takes the whole screen** can be asked about per site.
  The engine's request cannot wait for an answer, so the screen is
  given and a bar offers to take it back and remember that for the
  site; a site he said never to is refused outright. **The pointer**
  is a permission too now. And the permission card speaks German at
  last.
- **A copy of the page kept beside the bookmark** (MHTML), so a site
  that goes away can still be read.
- **How he got to a page**: every visit writes down the page the tab
  was on when it started, which gives both the chain that led here and
  **history as a tree** of what opened what.
- **A day of history in pictures**, off by default: a small local PNG
  per address, never for a private tab.
- **History out of Chrome or Firefox**, read with sqlite3 from a copy
  of the file, Chrome's 1601 epoch and all.
- **A bookmark whose page has moved** offers to update itself —
  measured from what the engine actually reports, which is not a
  status code: the tab was opened from that bookmark, he has not
  navigated it himself since, and it settled somewhere else.
- **The archive's copy** of a dead page, when he asks for it: the one
  thing here that sends an address off this machine, and it shows up
  in the browser's own connection log like everything else.
- **Bookmark reminders**, **Favourites docked beside the page**, and
  **the sites' own icons kept here** — written when he visits a site,
  never fetched for a list.
- **A history only his key opens**, under a key derived from the
  vault's rather than the vault's own. The file says what it is in its
  first bytes; with the vault locked it reads as empty and is never
  written over.
- **What the printer is doing**: state, file, per cent, time left,
  nozzle and bed, from Moonraker on his own network.
- **Both dictionaries at once**, where they are installed, and
  **the selection typed straight into the side panel**.
- **The recommendations he did not ask for**, hidden: the YouTube home
  grid, the Shorts shelves, Twitch's recommended channels — as a
  marked line in that site's own stylesheet, so switching it off takes
  out exactly that.
- **mailto: in his webmail** instead of a desktop mail program.
- **A price in a sentence, in euros** — selected, converted, shown
  where he selected it — and the units and time zones with it.
- **A piece of a page pinned on top** in a small always-on-top window.
- **Modes**: a whole setup in one click, and only the settings a mode
  is about.
- **From a terminal**: `browser --later <url>`, `--note "..."`,
  `--todo "..."` — handed to the running browser, answered, no window
  in his face.
- **This tab on his phone** over KDE Connect, **the words out of a
  picture** with tesseract, **a video's transcript as a note**, **a
  calendar file from a selected date**, **today's agenda** from a
  local .ics on the start page, and **a daily log** of what the day
  came to.
- **Captions for a video that has none**: ffmpeg pulls the sound out
  and the transcriber he named writes the WebVTT, which goes on the
  video as a real subtitle track. A player fed through Media Source
  has a blob: address nothing outside the page can open, and it says
  so.
- Fixed, and this one mattered: **`not reply.error()` is always false
  on PyQt6.** A Qt enum member is truthy whatever its value, `NoError`
  included — so every answer tested that way was thrown away. The
  http-to-https bookmark upgrade had been quietly upgrading nothing.
  All three places compare against `NoError` by name now.
- `BROWSER_HOME` moves everything of his at once, which is what a
  second browser on its own data needs.

## 2026-10-18 — two pages at once, and reading them

- **Two tabs side by side** in one window, with the divider he already
  has: the other tab's view is taken out of the strip and put in the
  other half of the splitter, and goes back where it was when the
  split closes. **Scrolled together** if he wants — read one half,
  write the other, four times a second, because there is no "the page
  scrolled" signal an embedder can hear.
- **The tab strip somewhere else**: down the left or the right (with a
  width he drags) or below the page. Qt's own tab positions, so it is
  the real strip with its own drag-and-drop in another place — and
  **more than one row** instead of scrolling, up to four.
- **The tabs of one site folded into one**, which is the group
  machinery doing what it is for: they go into a group named after the
  site and the group is collapsed.
- **Workspaces**: named sets of tabs in one window. The set he is
  leaving is saved before the new one opens, so switching back and
  forth keeps both sides as he left them.
- **A link from another program** can land in the virtual browser that
  site belongs to — his rules first, then the question if he asked for
  it — and **each virtual browser's window comes back** where it was,
  the size it was, with its own tabs.
- **A page in a language he does not read** says so in a plain bar:
  translate it once, always this language, never, or not now. Asked
  once per language per tab; his own language and English are never
  asked about.
- **Translated on this machine**, block by block, through the
  translator he named — the page's text never leaves the box, and
  `data-was` on every block means **undo** gives the page's own words
  back. Google Translate only when he has no translator of his own,
  and the entry says so plainly because it means the page is sent
  there. **Side by side** reuses the split.
- **PDFs**: the page he was on is remembered per file (the viewer puts
  it in the address, which is the one handle an embedder gets), and the
  keys it listens for are sent to it — next, previous, fit width,
  rotate.
- **The article printed without the furniture**: reader mode, then the
  PDF.
- **One word's worth of right-click**: spelling suggestions at the top
  (the engine checks and hands them over; Qt's standard menu does not
  carry them), "add to my words", **synonyms** from `dict` when a
  thesaurus is installed, and **what the word means in the other
  language** as a tooltip where he is reading.
- **A pasted address arrives clean**: the same 48 tracking parameters
  the address bar strips, stripped where he pastes, if he switches it
  on. Only a whole http(s) address is touched.
- **A book in the reader**: `.epub` opened with its chapters down the
  side in the reader's own type. zipfile and nothing installed.
- Fixed: a tab restored lazily kept its address as a `QUrl`, and the
  session save threw `TypeError: Object of type QUrl is not JSON
  serializable` the first time a workspace was opened. Addresses are
  text from the start now.
- Fixed: translating a page twice used to make the second pass's
  uppercase text the "original" that undo restored; a block that is
  already translated is left alone.
- Fixed: the translator call drew a caption overlay for every block of
  a page it translated. The program call is its own method now, and
  captions are one caller of it.

## 2026-10-18 — the agent bridge, part two

- **The page as a numbered list.** `tree` returns what can be aimed at
  — role, name, position — with a number on every row, and `click` and
  `type` take the number. An agent that has to invent CSS selectors
  gets them wrong; a numbered list it can.
- **Selectors reach into frames and shadow roots**: `#host >>> #button`
  steps through a shadow root or an iframe, in every op that takes a
  selector. A closed shadow root is honestly out of reach.
- **What a tab fetched**: address, kind, size and duration out of
  Navigation Timing — and the answer says plainly that there are no
  status codes, because the engine never hands one to an embedder.
- **A file through the browser's own session**: the page fetches it
  with its own cookies, so something behind a login really comes down,
  and the reply carries the size and the sha256.
- **An event stream.** The connection is the subscription: loads, title
  changes, tab switches and watches firing arrive as JSON lines. **And
  your own command can be run** when one happens — the event's name as
  an argument, the event as JSON on standard input.
- **Watching a page or an element**: a check on a schedule, with the
  old text and the new in the event. **And a tab can reload itself** on
  a timer — never while you are typing in it.
- **Macros**: what the page saw (the selector of what was clicked, what
  was typed) recorded and played back through the bridge's own click
  and type, so a macro is a list of ops you can read and edit. A
  password field is never recorded.
- **Auto-click rules**: a selector per site, clicked once when it
  appears — "Still watching?", "Continue", a wall that wants an answer.
- **The tabs the agent opened are its own**: marked, listable, closable
  in one go and swept after an idle time — never a tab you opened.
- **Permission levels**: off, read-only or full, plus an allow list of
  ops and of sites. Asking about the level is never refused, because a
  client that could not set it back would lock you out of your own
  browser. **Your history stays off** even at full permission until you
  say otherwise.
- **An audit log**: every op with the time and what it was aimed at,
  clearable — an answer to "what has been driving this browser" that
  does not depend on trusting whatever was driving it.
- **More ops**: open in a chosen virtual browser or a private tab, set
  a tab's viewport (or a phone's), list and move tab groups, search and
  get the results as a list, ask an assistant that is open in a tab,
  set the files for a page's file chooser, and real pointer input
  (hover, right-click, drag) as trusted events.
- **agent.py is a module too**: one function per op, a batch runner
  (`agent.py run steps.json`, stopping at the first failure) and
  `agent.stream()` yielding events as they arrive.
- **A local http mirror**, off by default: loopback only, a token
  required, and every op goes through the same socket every other
  client uses — so nothing touches a page from the http thread.
- **A browser with no window**: `browser.py --agent` starts the same
  browser — same jars, same scripts, same bridge — on its own sockets,
  for tests and background jobs.

## 2026-10-18 — the keys and the mouse

- **A site can keep its own keys**: Ctrl+K belongs to Discord's search
  and Ctrl+S to an editor in a tab, so those keys are stopped in the
  page before the browser's own shortcut can fire. **And one browser
  shortcut can be switched off on one site.**
- **Keys you never mean to press** (F1, Insert) can be ignored — not
  bound at all, which is the only way to be sure they do nothing.
- **Shortcuts follow the key, not the letter.** On a German keyboard
  Ctrl+Z sits where Ctrl+Y is and Ctrl+/ is Ctrl+Shift+7: both are
  bound, so whichever the layout produced works.
- **Two-step keys**: a leader key and then a letter, for the commands
  worth a key but not a key of their own — and the browser forgets
  after two seconds instead of waiting for ever. **"Do that again"**
  repeats whatever ran last.
- **Ctrl+Q asks twice.** It is next to Ctrl+W and it closes everything.
- **The address bar has a terminal's keys**: Ctrl+W kills the word
  behind, Ctrl+U the line, Ctrl+K to the end, Ctrl+A and Ctrl+E the
  ends, Alt+B and Alt+F a word at a time.
- **A text box can be edited in your own editor** (kitty + nvim by
  default): the text goes into a file, the editor opens on it, and what
  it wrote comes back into the box. **And text the page lost** when it
  reloaded can be brought back — kept in the page's own session
  storage, which dies with the tab and never touches the disk.
- **Vim keys on a page**, optional: j/k scroll, gg/G jump, H/L are
  history, gt/gT are tabs, / finds and gi goes to the first box — and a
  key typed in a text box is left alone.
- **Ctrl+Tab can go in most-recently-used order**, with the order kept
  as tabs rather than indices. **A virtual browser by number**, **the
  tabs of one group on their own**, and **hold a key to peek** at the
  tab you were on.
- **The mouse, as you want it**: drag a link to open it and drag text
  to search it, drag a box over links to open them all, two fingers
  sideways to go back and forward, middle-click-and-move to scroll (off
  by default, because middle-click pastes here), and hovering a tab
  while dragging switches to it so the drop lands where you meant.
- **What a click does is yours**: seven answers each for a double-click
  on a tab, a middle-click on a tab and a double-click on the empty
  strip — and a middle-click on the new-tab button opens the clipboard
  (an address) or searches it (words).
- **Wheel and arrow-key steps** can be set; 0 leaves the engine's own
  behaviour untouched.
- **Hold the right button for the gesture help** — what the mouse can
  do here, where the pointer is.
- **The window manager's keys**: eleven named commands over the
  single-instance socket (raise, new tab, play/pause, record, clip,
  shot, …) with the bind lines printed for your hyprland.conf rather
  than written into it.
- **A key can run one of your own scripts** — a file in the plugins
  folder or a javascript: bookmark.
- **Every context-menu thing has a key**: open the link under the
  pointer, copy it, save or copy or open the picture, search the
  selection. What is under the pointer is asked of the page, because
  that is the only thing that knows.
- **Fixed**: a server redirect on the way into a new tab (a 301 from
  the page you set as your new-tab page) could make the browser treat
  the tab as one you had navigated yourself, so an empty tab was saved
  into the session. A redirect hop while the load is still in flight is
  part of the arrival now; a hash router moving the address with no
  load at all still means the tab is yours.

## 2026-10-18 — recording and captures

- **A tab can be recorded** — frame by frame, because the engine hands
  an embedder pixels and not a stream. Part of a tab, with the
  microphone for a voice-over, or with the machine's own sound through
  the recorder you name (the engine taps no tab's audio either).
- **A replay buffer**: the last thirty to a hundred and twenty seconds
  kept in memory, savable with one action without stopping the
  recording — possible at all because a recording here is a list of
  frames and nothing cleverer. **The ends can be cut off** before it is
  written, for the same reason.
- **A GIF is written by the browser itself**, with its own LZW coder:
  Qt cannot write one and ffmpeg may not be installed. **WebM and MP4**
  go through ffmpeg when it is there, each frame handed over on its
  standard input. Without ffmpeg a recording is saved as a GIF rather
  than not at all.
- **Clicks and keys can be drawn into a recording** for a tutorial — on
  the frames the browser grabbed, never into the page, so none of it
  ends up in the page's own DOM, screenshots or printouts.
- **A clear mark while anything is recording**, on the tab and on the
  address bar.
- **An editor after the shutter**: crop, arrows, boxes, numbered
  markers, text and blur, with undo — and any picture on a page or on
  disk can be opened in it.
- **The captures you have taken**, as a list: open one, copy it as a
  picture, mark it up, delete it. **Drag one out** into Discord or a
  file manager (the file and the picture both go on the drag).
  **Copy one with the page's address** as Markdown or HTML, which is
  what a bug report wants.
- **A crisp capture at twice or three times the size**, rendered in a
  view of its own: Qt takes the device pixel ratio from the screen and
  an embedder cannot raise it.
- **The whole content of an inner scrolling area** — a chat log, a
  sidebar — stitched by scrolling the element itself; the tallest
  scroller is found for you.
- **The page at phone width**, **one-click PDF** straight into the
  downloads folder, and **the whole page as one tall PDF page** with no
  breaks through a paragraph.
- **A background tab can be captured without going to it**, **every tab
  at once** into one folder, and **a contact sheet** of all of them.
- **The selection as a picture** (the page's own typography, captured
  from the view) or **as Markdown with its source link**.
- **A timelapse**: this page captured every few minutes into a folder,
  for a printer webcam or a stats page. **A visual diff** against the
  last capture, pixel by pixel with a tolerance, because a page
  re-rendered is never identical.
- **Text out of a picture** with tesseract if it is installed, and it
  says plainly when it is not. **A QR code in a capture or a selected
  area** read here, by the decoder the wave before built.
- **A capture can be uploaded to a server of your own** — an https
  address it is PUT to, or user@host:/path handed to scp — opt-in, with
  the link coming back on the clipboard. **The address and the date**
  can be stamped under a capture, which is what turns a picture into a
  record.

## 2026-10-18 — what the browser is costing

- **"Free memory now"**: every background tab asleep except the ones
  that must keep running — playing sound, in a call, a game, pinned, or
  on a **keep-awake list** of your own (Amazon Music stops when its tab
  is discarded; Discord drops the call).
- **Freezing**, as the lighter step: a frozen tab keeps its page and its
  JavaScript and runs no timers, where a sleeping one gives the whole
  renderer back. Idle background tabs can be frozen after a set time.
- **A background tab that keeps the processor busy says so**, measured
  from /proc over a real interval — and only for tabs you are not
  looking at. Background renderers can be given **a lower claim on the
  processor**: only ever downwards, so nothing can be starved, and a
  process the front tab shares is left alone.
- **A page that has stopped answering** can have its renderer stopped
  and the tab reloaded, without restarting the browser. **A tab whose
  renderer crashed** comes back once, where you were reading, with the
  reason in a line.
- **Memory pressure, from the kernel itself**: /proc/pressure/memory,
  because "how much is free" means nothing on Linux and "how long
  something waited for memory" means exactly what it says. Above a
  **memory budget** the tabs you have not touched longest go to sleep.
- **A tab whose memory keeps climbing** is noticed — six readings, each
  higher than the last, which is a climb rather than a page that got
  busy.
- **What a page pulled down**: the bytes, the requests and where the
  bytes went, out of Navigation Timing — which knows every resource's
  transfer size, where the request interceptor is never told a size.
  Per tab as well, heaviest first, and as **a one-line badge** for the
  page in front.
- **Savings that live in the page**: off-screen pictures told to wait,
  animations paused in tabs nobody is looking at, silent video stopped
  in a tab you cannot see (sound is the exception — a podcast in a
  background tab is the point of a background tab), and **a floor under
  a site's timers** for a dashboard that polls too often.
- **A cap on video quality**: YouTube through its own player, Twitch
  through the setting it reads.
- **A soft reload** that gives the memory back and keeps your place:
  the scroll position and what you have typed into the page's fields
  come back; what the page kept in JavaScript is the memory this is
  here to give back.
- **What the graphics card is actually doing**, read off chrome://gpu —
  and the switch for hardware video decoding, with the three launch
  flags set for you. **Ten Chromium flags worth having**, each with
  what it does. **The cache size** per virtual browser, or memory-only.
- **Where the start-up time went**, broken down by step, with everything
  before the first step reported honestly as "python+qt". **What each
  userscript cost**, timed in the page.
- **A link the mouse rests on can be fetched early** — never from a
  private tab, because a prefetch is a visit as far as the server is
  concerned. **Connections opened early** to the sites your own history
  says you use most, opt-in and said plainly.
- **Tidying up while you are not using it**: history past its keep-days
  trimmed and the cache told to clear, only while the browser is idle.
- **Tabs you have not looked at for days** can be bookmarked and
  closed, and a big session can come back **in stages** or not load
  anything at all until each tab is opened.
- **A site that cost a lot of memory last time** gets a word before it
  does it again, and a small **log of start-up time and memory by day**
  makes a regression visible.

## 2026-10-18 — getting around a page

- **One popup for getting around** (Ctrl+Alt+Shift+G), with the
  switches settable for a single site: middle-click-and-move to scroll,
  Alt-drag a box over links, plain-text addresses made clickable, the
  site's scroll hijacking stopped, the site's key grabbing stopped, and
  the site's own timed refresh disarmed — with "allow it this once",
  because the tag is disarmed rather than deleted.
- **What a page is made of**, in one list: its links, its pictures,
  its meta data and its frames. **The picture gallery** has every image
  with its real size and alt text, each one openable, copyable and
  savable. **A frame the site refused to draw** is still a page, and it
  can be opened in a tab of its own; a frame can also be reloaded on
  its own.
- **The shape of the page** as a clickable outline of its landmarks,
  headings and forms, to jump through it from the keyboard.
- **The selection is useful**: every link in it listed, all of them
  opened at once as background tabs, and "go to the address I
  selected" for text that is not a link.
- **Find, with the extras**: whole-word and regular-expression modes,
  every match marked on a rail beside the scrollbar, a quick find that
  only looks at link text and follows what it finds, and **find in
  every open tab** — each tab answering for itself, so one slow page
  does not hold up the list.
- **Addresses rewritten before they load**: a rule like
  `reddit.com -> old.reddit.com`, applied in the navigation hook, so
  the page you did not want is never fetched at all.
- **A note stuck to a page** that comes back whenever you visit it,
  kept against the address without its query.
- **The mobile version in one switch**: the viewport a phone has and
  the user agent a phone sends, together, then a reload — because a
  site decides which version to send from the agent it is given.
- **A page that did not load says what failed** (DNS, refused,
  timeout, certificate, or plainly that the engine said nothing), with
  the archived copy offered as a link and a note when a proxy is on.
  **It can try again by itself** once the network answers.
- **The archived copy** of a dead page, with the address built here and
  never fetched: going there asks first and says plainly that it tells
  archive.org you looked.
- **Read the QR code in a picture**, decoded on this machine — `qr.py`
  gained a reader to go with its writer, the same tables run backwards,
  with the Reed-Solomon parity checked rather than guessed.
- **Shift and hover shows the linked page** in a small window, in a jar
  that writes nothing down, promotable to a tab. **A link can be opened
  in the side pane.** **A video can be handed to mpv.** **This page can
  be opened in the other browser.** **Only the selection can be
  printed.**
- **An address another program owns** (`discord://`, `steam://`,
  `mailto:`, `ts3server://`, …) asks once which program should open it
  and then remembers, per scheme and per site. What could open it is
  measured on this machine, and an unknown scheme goes to the desktop's
  own opener.
- **This site's cache and service workers** can be dropped and the page
  reloaded, without touching its cookies or logins.
- **A page that finished in a tab you are not looking at** gets a tick,
  cleared when you go there. **Back and Forward in a sleeping tab** use
  its saved history without loading everything in between.

## 2026-10-18 — accessibility

- **One popup with every reading help in it** (Ctrl+Alt+Shift+A), and
  every one of them can be set for a single site instead of everywhere.
- **What is done to a page**: always underline links, bigger things to
  click, darken text that is too faint (measured against the colour
  really behind it, and only where it fails), alt text on hover with
  pictures that have none marked, bold the start of each word, bigger
  scrollbars, hyphenate long words, wrap text to the window instead of
  scrolling sideways, unstick headers and footers, stop a page
  reloading itself on a timer, open up the line, word and letter
  spacing, zoom the text without the pictures, and a reading font —
  offered only when the machine really has one.
- **Colour-blindness filters**: two corrections (red-green,
  blue-yellow) and three simulations for checking a design, each one
  matrix applied to the page's own root, so the browser's chrome is
  untouched.
- **The keys that move through a page**: the next and previous heading,
  the landmarks, the form fields, skip to the content, into the first
  text field, and the arrow keys between links and buttons. **Caret
  browsing on F7** — a text cursor the arrows move and Shift extends.
  **Esc closes a dialog the site will not.** Tooltips on keyboard
  focus, the focused thing kept in the middle, and Alt-drag to select a
  link's words instead of dragging it.
- **Find my cursor**: Ctrl on its own flashes a ring round the pointer
  — and only when nothing else is pressed with it. **A magnifying lens**
  that follows the pointer, drawn from the window's own pixels.
- **The keyboard reaches the furniture**: the tab strip with its arrow
  keys and that tab's own menu, and Shift+F10 opens the page menu at
  whatever has the focus.
- **A page's own faults, listed**: fields with no label, pictures with
  no alt text, text that fails contrast, and headings that skip a
  level.
- **The browser's own buttons, fields and panels are named** for an
  AT-SPI screen reader, read from the words they already carry.
- **Live captions for what a tab is playing** — honestly what it is:
  the engine gives the embedder no tap on a tab's audio, so the browser
  records the machine's own output a few seconds at a time with the
  recorder you name and hands each chunk to the transcriber you name
  (parec and whisper-cli, say). Opt-in, nothing bundled, nothing
  downloaded, and no sound leaves the machine. **A video's own captions
  can be translated** line by line by a translator on this machine.
- **Mono and balance** for a page's sound, through Web Audio, because
  the engine has no mixer an embedder can reach.
- **Short sound cues** when a page or a download finishes — two tones
  the browser writes itself as .wav files beside the config.

## 2026-10-18 — appearance and themes

- **Themes of your own.** A theme is eight colours; the other fifteen
  are derived from them, the same way the hundred and fourteen that
  came with the browser are. Save one under a name, star the ones you
  keep coming back to and step through them, replace a theme's accent
  without leaving the theme, write one out as a small JSON file and
  read one back.
- **A kitty.conf, a base16 YAML or a VS Code theme becomes a browser
  theme**, read by one reader, because all three are names and hex
  strings. And the browser can **follow a colour file**: point it at
  the rice switcher's current theme and it re-themes when that file is
  saved. Nothing is fetched; it is a file on your own disk.
- **It can follow the desktop.** The XDG portal's light/dark setting,
  through Qt's own signal, switching between the two themes you pick.
- **The theme editor says what cannot be read**: measured contrast, not
  a judgement — text on background wants 4.5:1 and an accent 3:1.
- **A sixth look, Flat mono**: square corners, no shadows, no cards,
  lettered like a terminal.
- **The chrome is yours to size**: compact, normal or big; its own font
  and font size (monospace families first); how round the corners are,
  from square upwards, in any look; how see-through Glass is; the
  widest a tab may get; how tall the toolbar is; plain menus with
  bigger rows; words on the toolbar instead of glyphs; how loudly
  keyboard focus is drawn; and no animation in the browser's own pages.
- **The tabs and the toolbar can hide** until the mouse reaches the top
  edge — or Ctrl+L, which is asking for the address bar. The same in
  F11 fullscreen.
- **Which account is in use is never a guess**: a colour per virtual
  browser on the strip and the address bar, a colour of their own for
  private tabs, and — if you want it — the site's own theme-color on
  the toolbar, with the virtual browser's colour winning over it.
- **Favicons in one colour**, for a calm strip: the shapes are kept and
  the brand colours thrown away. Bookmarks keep theirs.
- **The hovered link** can be said bottom left, over the address bar or
  nowhere, at a size you choose — and never over an address you are
  typing. **The window title** can be the page, the site, or with the
  virtual browser in it, for Hyprland rules and the task switcher.
- **How websites are shown**: dim them in the evening between two times
  you set (the page only — the browser keeps its brightness), warmer
  colours in the same hours, grey everywhere or per site, thin or
  themed or hidden scrollbars with sites excused, the selection in your
  accent colour, a background for pages that bring none, and a text
  size for one site without touching its zoom.
- **The fonts websites fall back to** — standard, serif, sans and
  monospace — and **the colour emoji family**, which is Chromium's
  pictograph font: the one it reaches for when a page asks for an emoji.
- **Plain files on your background**: a .txt, a .json or an image
  opened on its own, with a checkerboard behind a transparent PNG.
  **Dark PDF pages**, by inverting the plugin and turning the hue back.
  **DevTools** opens in the browser's colours.
- **Sites to leave alone**, editable in Settings instead of living in
  the source, and "leave this site alone" from the appearance menu.
- **A page that did not load** can be shown in the browser's own plain
  style, in your palette, with Enter to try again. Off by default, and
  never shown for the trust channel's own re-issued navigation.
- **The start page** can show or hide the clock, the seconds and the
  date, run on a twelve- or twenty-four-hour clock, put the search box
  where you want it and size the quick links — and **rotate through a
  folder of wallpapers**, on every new tab or every N minutes. Nothing
  is copied and nothing is fetched.
- **"Put appearance back as it came"**, with one backup kept — your own
  themes included — and an undo.

## 2026-10-18 — the developer tools

- **A ruler, element outlines, hidden form fields and a no-CSS view**,
  each a switch that remembers whether it is on. The ruler measures in
  pixels, the hidden fields come out with a note saying where the form
  posts, and the no-CSS view is the page's own structure with nothing
  on top of it.
- **What a page is made of, read out of the page**: the fonts it
  renders in, the colours it uses with the heaviest first, a picture's
  real size against the size it is drawn at, and the Open Graph tags
  as a link preview would see them.
- **A performance overlay** with frames a second, long tasks and the
  layout shift, and **a mockup laid over the page** at any strength —
  the picture is read here and handed over as data, so nothing you are
  comparing against leaves the machine.
- **Local and session storage** read, written and emptied; IndexedDB
  listed by name. **The cookies of a site** listed, added, deleted and
  written out as a Netscape cookies.txt, with a line at the top saying
  plainly what that file is.
- **A tab can pretend**: a phone or tablet width, dark or light, print
  media, another place, another time zone, another language, and a
  slow connection — which is honestly a measured hold before each
  navigation, because the engine offers no rate control.
- **A tab can pretend to be another browser**: a user agent per site,
  sub-domains included, sent as the real request header and matched by
  what the page's own JavaScript reads.
- **The requests a page makes**, written down with the address, the
  host, the method, the kind and whether it is first-party, filterable
  by word and exportable as a HAR file. Off until you ask for it.
- **Addresses can be blocked or sent somewhere else** — a rule like
  `/ads.js → block`, or one pointing at a file of your own, to try a
  fix on a live site. **Headers of your own** can be added per site or
  everywhere.
- **"Do not sell or share" is now the real header.** Sec-GPC goes out
  with every request, with the same per-site excuse the page guards
  have, measured leaving the browser rather than assumed.
- **The server's answer**: the response headers of the page, with the
  security headers it does not send called out. **A request of your
  own**: method, address, headers, body and what came back, with how
  long it took. **The clock**: time to first byte, the DOM, the load,
  and what the page weighed.
- **The workbench**: a regular-expression tester, a text diff, a patch
  viewer, Markdown, MiniMessage and Minecraft JSON components drawn as
  they appear in chat, and JavaScript snippets you can save and run on
  the page.
- **The page looked over**: a small honest audit (no score out of a
  hundred), a link checker that is opt-in because it goes online, the
  JavaScript errors of a page counted for a badge, the service workers
  listed and unregisterable, and the certificate in words.
- **A folder can be watched** and the tab reloads when a file in it
  changes — a userscript saved in the plugins folder is re-read and
  reaches the tabs it runs on.
- **The engine's own switches**: the chrome:// pages that work, the
  Chromium flags, a domain pointed at an IP for this browser only, the
  remote debugging port (off by default, localhost only) and accepting
  a self-signed certificate on localhost and the home network alone.
- **Fixed, found by the tests**: six things in the browser were defined
  twice, and in Python the second one silently wins. Two `resizeEvent`
  methods, so the toasts and popovers had stopped following the window;
  two tables of developer tools, so every tool written before this wave
  answered nothing at all; two `storage_menu`, two `page_links` with
  different answer shapes, two certificate menus and two `hard_reload`.
  All merged or renamed, and an invariant check now fails if anything
  in browser.py is ever defined twice again.

## 2026-10-18 — the address bar

- **The domain is bright and the rest of the address is dim**, so
  `paypal.com.evil.ru/login` reads as what it is. Only while you are not
  editing, and it can be switched off.
- **A name dressed up as another one is called out**: a Cyrillic *а* in
  apple.com, a capital I standing in for an l in paypal.com, two scripts
  in one label.
- **A plain http page says "Not secure"**, and the lock opens a panel
  with the connection, the cookie rule for the site, what it is allowed
  to do, and what it is using the camera or microphone for. The
  certificate is one press away — it is fetched when you ask, not to
  fill a panel.
- **Addresses are shown as readable text** (%20, umlauts, punycode) and
  `https://` and `www.` can be left off — while copying still gives the
  real address.
- **The loading progress runs along the bottom of the bar.**
- **What you type is understood better**: `YOUTUBE.COM`, `you tube.com`,
  a link with the chat's punctuation stuck to it, `~/Downloads`, and
  `localhost:8080` all go where you meant. A sentence with a site in it
  is still a search.
- **"Did you mean youtube.com?"** when a domain is one letter off a site
  you actually visit — from your own history, never a list somebody else
  wrote.
- **Nothing that is not a search is sent to the search engine**: an
  address, a path, an e-mail address, a token or a card-shaped number
  never leaves the machine as a suggestion query.
- **Typing a domain completes it** from the sites you really visit, with
  the rest selected — and a site can be told never to be suggested
  again.
- **@tabs, @bookmarks, @history, @settings, @downloads, @notes** limit
  the drop-down to one source; **Settings entries** turn up in it
  ("dark mode", "proxy"); **tabs in your other windows** are offered and
  the window is raised.
- **Tab searches the site in the bar** — its own search, from its
  OpenSearch offer where it has one — and a site that offers one can be
  added with a press.
- **More answers in the bar**: `0x1f`, `1010b`, `255 in hex`,
  `ip 192.168.2.0/24`, and `20 usd in eur` from a rate table you switch
  on (the European Central Bank's daily file, once a day). Enter on any
  answer copies it and says so.
- **Shift+Enter** opens the result in a background tab, **middle-click**
  pastes the selection and goes, **Ctrl+L twice** selects just the path,
  **Up and Down** step through what you typed in that tab, and
  **Alt+click** on a link saves it.
- **Buttons in the bar**: copy, clear, and a QR code of the page for your
  phone — each one switchable.
- **The whole toolbar can go under the page**, and the bar's text can be
  made bigger on its own.
- **Your own search engines** (name, address, keyword), a **different
  engine for private tabs**, and **German searches to one engine,
  English to another** — decided by the letters, not by asking anybody.
- **Bookmark keywords**: `k` and Enter opens it, the way Firefox does.
- **A page listing every search you made from the bar**, searchable and
  clearable, never written from a private tab.

Fixed along the way:

- **notes.html, player.html and mictest.html were never on the list of
  the browser's own pages**, so each was handed the password channel
  instead of the settings bridge — the notes drawer, the local player
  and the microphone test have been calling a bridge that was not there
  since the waves that added them. There is one list now (`OWN_PAGES`),
  the invariant check reads it rather than repeating it, and the test
  asks the page itself whether its bridge arrived.
- The test harness left its scratch directory behind on every run. A few
  hundred runs filled /tmp, and what that looks like is not "no space
  left" but the last few tests of a suite segfaulting and timing out.

## 2026-10-18 — downloads and files

- **The downloads list is a list you can use**: search it by name,
  address or site, filter by kind or by how long ago, export it as CSV,
  copy a download's address, fetch one again whose file is gone, and
  drop finished rows after a number of days you choose — the files are
  never touched by that.
- **Each download remembers the page it came from**, not only the file's
  own address, with a button to open that page again.
- **A checksum for any download** (or for every one, if you switch that
  on), and a warning when a file with the same name — or the same
  bytes — is already in your downloads.
- **Delete a download's file**, not just its row, with a question first.
- **Files can be named the way you want them**: `{name} {ext} {site}
  {title} {date} {time} {n}`.
- **Ask where to save only the kinds you say**, refuse kinds you never
  want arriving on their own, and ask before anything bigger than a size
  you set — or bigger than the free space left.
- **Private tabs can download into a folder of their own**, emptied when
  the last one closes if you ask. Each virtual browser can have its own
  folder too.
- **Where a file came from can be written into the file** (the
  `xdg.origin.url` attribute every file manager reads).
- **A queue**: how many downloads run at once, with the rest waiting and
  reorderable — and a **speed cap**, which the hint explains honestly as
  a cap on average, because the engine offers no rate limit.
- **A download at a time you choose.**
- **Archives**: look inside one before unpacking it, unpack it into a
  folder of its own name, pull one file out of it — and an archive that
  tries to write outside its folder is refused outright.
- **A downloaded mod says what it is**: Fabric, Forge or NeoForge, its
  version and which Minecraft it wants, read out of the jar — and it can
  go straight into an instance's `mods` folder.
- **Pictures**: save the ones on a page with a size filter, fetch the
  full-size version where the site's own addresses say how, convert a
  WebP or AVIF to PNG or JPEG, and take the camera and GPS data out of a
  picture before uploading it.
- **Paste a picture from the clipboard into an upload box**, or pick one
  of your recent downloads for it — the page never reads your clipboard;
  the browser hands over the bytes.
- **Save a page as one file** (MHTML, or a single HTML with its styles
  and pictures inside) **or as Markdown**, through the same converter the
  agent bridge uses.
- **A quick look at a download** — a picture, a text file, a PDF or an
  archive listing — without opening another program.
- **A list of addresses downloaded in one go**, and **Alt+click on a
  link saves it** instead of going there.
- **Handoffs to the programs you have**: magnet links and `.torrent`
  files to the torrent client, a video to yt-dlp, a finished file to
  ClamAV, a `.gcode` to the 3D printer over Moonraker. Each one says
  which program it wanted when that program is not installed — "no
  scanner" and "clean" are never shown as the same thing.
- **A finished download can be dragged out of the bar** into Discord, a
  file manager or an upload box.
- **A word when a download finishes** while you are in another window.

## 2026-10-18 — passwords and forms

- **Addresses and cards fill themselves** into sign-up forms and
  checkouts, by what each box is actually called rather than by
  guesswork. The card's security number is asked for every time — it is
  the number that is supposed to prove somebody is holding the card —
  and a checkout inside the payment company's own frame says so instead
  of looking broken.
- **A password made here**, filled into both boxes of a sign-up form and
  saved in the same breath, obeying the site's own length limit and
  `passwordrules`. Or **a passphrase of words**, from two word lists
  beside the browser, which tells you how many bits that is.
- **Two-factor codes** go into the code box (or the clipboard when there
  is no box), and the **setup secret can be taken off the page** — the
  `otpauth://` link or the printed secret beside the QR code.
- **Copied passwords leave the clipboard again** after half a minute,
  unless you have copied something else since.
- **One key fills the login** (Ctrl+Shift+Q), with **sites that are one
  account** — amazon.de and amazon.com, and your own groups — treated as
  one. Per site, you can have the form **sent off after filling** or
  **filled as the page loads**, and a login can be **tied to one virtual
  browser**.
- **An eye in every password box**, **pasting unblocked** where a site
  refuses it, **"do not save this" ignored** where you say so, and **any
  text box opened in a big window** to write in peace.
- **What you type in forms is kept** and put back after a crash or a
  misclick — never a password, never a private tab — and **what you type
  in boxes can be remembered** per site and offered again.
- **It says something about the form in front of you**: a password box
  on an unencrypted page, and a sign-up form on a site you already have
  a login for. And when a saved password is typed into a site it does
  not belong to, it says that too.
- **Logins sent by scripts are offered for saving.** Sites that sign in
  without submitting a form — most of them now — were never offered at
  all before.
- **An http login box at last.** The engine's own signal had nothing
  connected to it, so a server panel or a router asking for a password
  simply failed to load. A saved login fills it once; after that you are
  asked, rather than the same refused password going back for ever.
- **Security keys and passkeys** get the dialogs the engine waits for.
  That signal was unconnected too, so every passkey login quietly did
  nothing.
- **The leak check** (opt-in): the first five characters of each
  password's SHA-1 go out, the comparison happens here, and the service
  never learns which password was asked about.
- **The vault learned more shapes**: API keys with an expiry, recovery
  codes with the used ones struck off, extra fields of your own (a PIN, a
  customer number), earlier passwords kept when one changes, and a
  username saved without a password.
- **Lists worth acting on**: logins saved twice (and folded together),
  not used for a year, sites that could have two-factor and have not,
  keys and cards running out, and a log of what was revealed, copied or
  filled.
- **The vault as one encrypted file**, with **dated backups** into a
  folder of your choosing, and **imports** from Bitwarden, Chrome and
  Firefox.
- **A QR code of a password**, to point a phone at — and the QR code is
  now drawn by the browser itself (new `qr.py`, standard library only).
  The older "show as QR" needed `qrencode` and was dead on any machine
  without it.
- Searching the vault from one small box, locking it on the spot, and
  opening a site's own change-password page (including "open the weak
  ones, one tab each").

Fixed along the way:

- The form helpers were plain function declarations in the injected
  snippet, which made them globals in the page's own world. They live
  inside their wrapper now; `test_acctpick` is what caught it.

## 2026-10-18 — games, streaming, and the rest of video and sound

- **The desktop's media keys reach the browser.** It registers as an
  MPRIS player over D-Bus (`mpris.py`), so the play key on the keyboard,
  waybar and `playerctl` all talk to whichever tab is playing. Nothing
  is sent anywhere; on a machine with no session bus it says so and
  stays out of the way.
- **A video can fill the window** instead of the whole screen, for a
  wide monitor where a full-screen video is too much — and full screen
  can be told **which monitor** to use.
- **The screen stays awake while something is playing**, through
  systemd-inhibit, only while it really is playing, and only if you
  switch it on.
- **A player for files on disk** (`player.html`): a playlist, the speed
  and loop controls, and the subtitle file beside the video picked up
  without being asked for. Nothing is converted and nothing is uploaded.
- **A microphone and camera test page** (`mictest.html`) with a live
  level meter, for the minute before a call.
- **Watch later**: a queue of videos from any site, played in order.
- **Moments**: mark a place in a video with a word about why, and jump
  back to it later.
- **Pause when you lock the browser** or have been away.
- **Skip the sponsor** (SponsorBlock, off unless you ask: only the first
  four characters of the video's hashed id are ever sent) and **fetch
  lyrics** (lrclib, off unless you ask).
- **Stream-safe mode**: addresses, IPs and words of your choosing
  blurred on the page, notifications held back, no suggestions out of
  your history — and everything put back the way you had it when you
  switch it off.
- **A key overlay and a frame counter**, for recording and for cloud
  gaming.
- **OBS**, driven over its own websocket on this machine: start and stop
  recording, start and stop streaming, switch scene. Off unless you give
  it an address; the password is answered as a challenge, never sent.
- **Mods**: one search box for Modrinth, and a download written straight
  into an instance's `mods` folder — that folder and no other.
- **Minecraft server addresses** read off a page and copied with their
  port, the server's own page in the side panel, **NameMC** and the
  **wiki** in the panel.
- **Twitch**: several streams in one grid, channel points claimed as
  they appear, ads muted and dimmed until they are over, chat filters
  (hide a word, hide a chatter, light up your own name), theater mode by
  default, go-live alerts that only ask while they are switched on, and
  the live chat in the side panel.
- **A stream delay timer**, **clip markers** with a timestamp, and
  **clean clip links** with the sharing parameters taken off.
- **Discord** links open in the Discord tab you already have, and its
  own unread count appears on that tab.
- **`ts3server://` links** are handed to TeamSpeak, and say so plainly
  when it is not installed.
- **A game tab can be protected**: never discarded, never slept, asks
  before it closes — and it **holds Esc and the browser's own shortcuts**
  while it has the screen (the Keyboard Lock API, which this engine does
  have).
- **One switch for cloud gaming** per site, **a gamepad** that scrolls,
  changes tab and works the player, a **stream preview** in a small
  window, a **pre-stream checklist**, and **game mode by itself** when
  the window manager says a game is in front.

Fixed along the way:

- Two different timers shared one name (`self._media_timer`): the
  two-second "what is playing" poll was dropped on the floor, and
  leaving the macOS look stopped the microphone-and-camera watch and the
  lock timer it feeds.
- A tool run from a timer took the whole browser down if its tab had
  closed in the meantime (an exception in a Qt slot aborts the process).
  All three tool runners and the per-page settle hooks now answer "no"
  instead.

## 2026-10-17 — video and sound, part two

- **The picture**: brightness, contrast and colour for a dark or washed
  out video; a quarter turn for one shot sideways, and a mirror; zoom,
  pan and crop the black bars away so it fills its box; and the mouse
  pointer out of the way after two seconds over a playing video.
- **What the video actually is**: size, speed, dropped frames and how
  much is buffered, read off the element rather than guessed — and
  **when it will end**, at the speed it is playing.
- **Videos resume where you left them**, per video, on this computer,
  with a list of what you have watched and how far you got.
- **Captions**: on or off on any video, a language to start in, your own
  size, colour, background and height, **subtitles from a .srt or .vtt
  file** (turned into WebVTT on the way in, with an offset), the
  **transcript** as a list you can click to seek, copy, or **save as an
  .srt**.
- **Chapters** out of the timestamps in a video's own description.
- **The sound**: a limiter that evens out quiet and loud videos, a
  ten-band equaliser with six presets, balance, a mono downmix,
  crossfeed for headphones, and **running through the quiet parts** of a
  lecture, measured in the page.
- **Which output a tab plays through**, and **which microphone a site
  gets** — the device and your own answers about automatic gain, noise
  suppression and echo cancellation are put into the request before it
  is made, because the engine offers no way to say it afterwards.
- **Per site**: autoplay (play, play muted, or not at all), always
  muted, and a quality cap where the site has a control worth touching.
- **The other tabs quieten** when the front one starts playing, and
  **the music pauses during a call** — when a tab starts using the
  microphone — and plays again afterwards.
- **Embedded players load on a click** instead of on sight, and an embed
  can be opened on its own site.
- **Sound only**, hiding the video and asking the site for its lowest
  quality; **Shorts in the normal player**; **the videos and sounds
  linked on a page** as a list; **play it in mpv** where mpv is
  installed.
- **A line when the track changes**, with title and artist, off by
  default.
- **Video lengths and progress hidden** on the sites where that gives
  the ending away.

## 2026-10-17 — reading and text, part two

- **The reader has switches**: pictures off, proper hyphenation with
  justified text, a sans font instead of the serif one, and three
  widths. **Save the article** as Markdown or put it straight **into a
  note**. **Reader mode for a selection** when the page is too odd to
  parse, and **add the next page** so a split article reads as one.
- **Long pages open where you stopped** (the last fifty, on this
  machine), with **a thin progress line** at the top.
- **A comfortable column** per site for pages that run the whole screen,
  without full reader mode.
- **What a page hides** — fades, clamped boxes, closed details — opened
  in one go. **Footnotes shown where the mark is.** **The words a page
  explains** get a dotted underline and a tooltip.
- **Plain code blocks coloured** in the theme's own colours, and
  **copying code drops the line numbers** that logs and pastebins put
  in the text.
- **A selection can become**: its metric value (`5 in` → 127 mm,
  `350 F` → 176 °C), a time in your own zone (`8 PM EST` → 02:00 here),
  a list of its code points (for the invisible and the lookalike
  characters), or a diff against the clipboard.
- **Translate the selection** and **look a word up** — the two that
  leave the machine, and both say so in their own names: the
  translation goes to Google Translate in the side panel, and the
  dictionary uses `dict` when it is installed and the site you chose
  when it is not.
- **Text fields**: find and replace, a big mono font while you write,
  words and reading time, **your own editor** (kate, gedit, nvim — the
  text goes out to a file and comes back when you save), **drafts kept
  and put back** after a reload or a crash, and **Ctrl+Shift+V** pasting
  without formatting.
- **A small bar over selected text** with copy, search, translate,
  define and highlight.
- **Files that are only text, shown properly**: a `.md` rendered, a
  `.log` with line numbers, an RSS or Atom file as a list of entries,
  and the raw text one click away.
- **Everything you have highlighted** in one list, with an export to
  Markdown.
- **Spell check in two languages at once**, so a German post with
  English mod names in it is not underlined from end to end.
- **Per site**: which language it is asked for, and which text encoding
  its pages are read as — for the old ones that show Ã¼ where they mean
  ü.

## 2026-10-17 — the desk drawer

- **A notes panel** beside the page: Markdown notes with a preview, a
  search, checklists, tags and a note for today. They are **plain .md
  files in a folder you pick**, so any editor, any grep and your backup
  can read them — and the to-do list is a `todo.md` of `- [ ]` lines.
- **A to-do list** with checkboxes, reordering, a done section, due
  times with a notification, "make a to-do of this tab", and "turn a
  list on this page into to-dos".
- **Clip the selection into today's note** with the page it came from
  under it, **make a note of this page**, and **a quick note** over any
  tab with one key.
- **Collections**: links gathered under a name, which are Markdown
  files and therefore already the export.
- **A clipboard history** — in memory only, off by default, never fed by
  a private tab — with pinning and search.
- **Text snippets**: type `;ip` in any field and it becomes what you
  said it should.
- **Focus mode**: chosen sites blocked for a while, with a plain page
  saying how long is left. **A daily limit per site**, counted only
  while the site is actually in front, warning before it runs out.
- **Timers and a pomodoro**, with a desktop notification when they are
  up, and a **break reminder** counted off actual use.
- **The web's notifications now arrive at all** — the browser had no
  presenter, so they went nowhere. They are written down, held while
  **Do not disturb** is on, and said afterwards.
- **Snooze a tab** until this evening or tomorrow morning, and **open a
  page at a time every day**.
- **Zen mode** (Ctrl+Shift+Z): the page and nothing else.
- **Search everything** (Ctrl+Shift+H): open tabs, bookmarks, history,
  notes, to-dos and clips in one list, all of it from this machine.
- **Copy things properly**: the selection as Markdown, the page as clean
  text, a link that highlights the selection, any table as Markdown, CSV
  or tab-separated, and every link and email address on the page.
- **Text tools** in any field: upper, lower, Title Case, sort the lines,
  drop the duplicates, trim the spaces, join with commas — plus a
  character picker with umlauts, signs, arrows and Minecraft's § colour
  codes, a live character counter (with Discord's 2000 marked), smart
  paste that turns a pasted link over selected text into a Markdown
  link, and **a big editor** for any text box.
- **Add up the numbers in a selection**, reading 1.234,50 and 1,234.50
  alike.
- **Open with**: the page or a link in mpv, an editor or the file
  manager — only what is actually installed is offered.
- **As a QR code** for the phone, drawn by qrencode when it is there and
  saying so plainly when it is not.
- **Countdowns on the start page**, counted here and shown here.

## 2026-10-17 — what is kept, and what the connection is

- **Cookies per site**: keep them, keep them until the browser closes,
  or do not keep them at all. Blocking is what this engine allows it to
  be — the cookie is deleted in the moment it arrives, and the count of
  refused ones is in the address bar if you want it.
- **What sites may do**: every permission ever allowed in one list, with
  when it was last used, a way to take any of them back, a dated log of
  when the microphone, camera, location or screen was actually used, and
  an expiry for the ones you never use.
- **"This time"** beside Allow and Deny: granted once, written down
  nowhere, asked again next time.
- **A mark when a device is on**: which tab is using the microphone, the
  camera or the screen, with a stop button per tab. Read from the pages
  themselves, because the engine only reports the asking.
- **A throwaway virtual browser** — a fresh session with nowhere to
  write, gone when it closes — and **a clean room** for chosen sites: a
  bank opens in a browser of its own every time.
- **The certificate**: what the site is actually serving, who issued it,
  how long it is good for, the TLS version, the address it resolved to
  and its fingerprint. A warning when a site you watch changes its
  certificate, and a "trust this one" for your own printer or server
  that stores the exact certificate and asks again if it changes.
- **Insecure parts on a secure page**, listed.
- **What each site has stored**, with a delete button each; **the sites
  that keep you logged in**, with a sign-out; **service workers**,
  listed and unregisterable; **the sites you only ever passed through**,
  cleared in one go; and **clear only the cache**.
- **Sites that want to handle mailto: links** are refused unless you say
  yes, and listed either way.
- **The window locks** — by hotkey or after a while idle — behind a word
  kept as a hash, with nothing readable until it is typed.
- **Every privacy rule as one file**, exported and imported, and nothing
  else of the settings with it.
- **What each virtual browser wipes when the browser closes**: cookies,
  cache, history or the downloads list, per browser.

## 2026-10-17 — what a page may do in its own window

- **The page guards** (page menu → Privacy → "What this page may do"),
  each off until you switch it on and each switchable off for one site:
  blur what a site can tell about this computer (canvas, WebGL, audio,
  cores, memory), never let a page read the clipboard, copy only what is
  selected, ignore "Leave site?" boxes, tell sites not to sell or share,
  block frames from other sites, use local fonts instead of the site's,
  note the live connections a page opens, switch WebRTC off, answer
  cookie banners with "reject", and write down the windows a page tried
  to open.
- **Hide an element for good**: right-click the thing you want gone and
  pick "Hide this element". Kept as a selector of yours, per site, and
  applied to the page you are on at once.
- **What a site may not use**, per site: 3D graphics, WebAssembly, USB,
  Bluetooth, serial, HID, MIDI, motion sensors, idle detection, NFC, the
  battery and speech recognition.
- **A place of your choosing** for a site, instead of the real one. Two
  numbers you type in — nothing is looked up anywhere.
- **Blocked windows**, with "open this one" and "always allow here".
- **Only load sites over https**, with the question asked before
  anything falls back to http, and a permanent exception per site.
- **Stop pages redirecting a tab you are not on.**
- **Work offline**: nothing new is loaded. Said plainly — a page that is
  already open keeps what it has, and a restart makes it total.
- **A download from a different site than the page says so.**
- **Tabs of chosen sites are never saved** for the next start.
- **Private tabs** are not captured by the screenshot tools and never
  appear in the media list (both switchable).
- **Alt over a link** says where it really goes, with the redirect
  wrappers unwrapped; short links can be resolved on hover (opt-in,
  because it tells the shortener you saw the link).
- **Only one language** in Accept-Language, when you want it.
- **What the engine can only be told at launch**, with a restart notice:
  no link pings, no referrer at all, no connections before you click,
  every site in its own process, WebRTC kept off the home network,
  encrypted DNS with your own provider, session recorders blocked by
  name, your own phishing list (`phishing-hosts.txt`, nothing is
  downloaded), and your own list of domains to refuse.
- **A line at startup** when a privacy setting changed since the last
  one, or when a list you asked for would not load.

## 2026-10-17 — bookmarks and history, part two

- **The history page rebuilt**: pages, most visited, your searches and a
  week of statistics; a date range, a site box and a virtual-browser
  filter; group by site; show or hide the login bounces and link
  wrappers; pick rows to open, bookmark, copy or delete; delete a whole
  range; and an Undo for a few seconds after any of it.
- **Keep history for N days** (0 = for ever), **forget one site**, and
  **pause history for one tab** without making it private.
- **Never record a site** in this virtual browser.
- **Visit counts, first and last visit** on a bookmark, and **how many
  days in a row** you have been to a site.
- **Carry on where you left off** and **the bookmarks you added last**,
  as optional rows on the start page.
- **Export the history** as CSV or JSON; **open a day of browsing
  again** as tabs or a group.
- **Tidy up page titles** (off by default): the "(3)" and the
  "- YouTube" come off what is written down.
- **Bookmarks**: tags, a note of your own, a nickname that opens one
  from the address bar, a ranked Favourites search (tag:, site:, and
  the ones you actually open first), smart folders that are saved
  searches, duplicates found and merged, the ones you never open listed
  for cleanup, folder colours, folder locks, separator lines, sorting a
  folder by name, date, last opened or how often, opening a whole folder
  as tabs or as a group, bookmarking a link without opening it, and
  where you had read to on the page.
- **Bookmarklets**, kept as a script and never as an address, run in the
  page's own world on a click of yours and never on a page of the
  browser's own.
- **Import** from Chrome, Firefox or an exported HTML file, keeping the
  folders and never replacing what is there; **export** as HTML, JSON or
  a Markdown list.
- **A dated copy every day**, with any of the last fourteen restorable,
  and **a copy in a folder of yours** (a share, a stick) that can be
  merged back — no account and no cloud.
- **Two jobs that go online, and only when asked**: check every bookmark
  for dead links and permanent redirects, and move the old http://
  bookmarks to https where the site actually answers.
- **Copy bookmarks between virtual browsers.**

## 2026-10-17 — tabs, part two

- **Several tabs at once**: ctrl-click and shift-click to pick them,
  then close, mute, reload, pin, bookmark, set aside or group them in
  one step.
- **Several windows**: Ctrl+N, a window list, "move this tab to a new
  window", "move this group to a new window", "gather every window
  here", a private window, and the window title says which virtual
  browser it is. A second window shares the first one's cookies,
  bookmarks, passwords and settings — one browser, two views of it.
- **A tab as a small window** for a chat beside a game, and **a site as
  an app**: its own window with no strip and no address bar, with a
  desktop entry so it starts from the application menu.
- **What the strip says**: the unread count a page puts in its own title,
  a dot on a background tab whose title or icon changed, a thin loading
  line, a dim mark on a sleeping tab, each site's own faint colour, and
  the close cross where you want it.
- **The strip itself**: fixed, shrinking or favicon-only tabs with a
  floor you set, hide it when only one tab is open, fold the other
  groups away, and your own answers for double-click and middle-click.
- **Saved sets of tabs** under a name, **tabs set aside**, **snapshots
  every few minutes**, **export and import the open tabs**, and a
  **crash list** with a box beside each tab rather than all of them or
  none.
- **A reopened tab keeps its Back button**: the trail is walked back,
  which is the only way this engine allows.
- **A tab opened from a link** lands beside the tab that opened it, and
  Back on one with nowhere to go closes it and returns you there.
- **All tabs as pictures** (Ctrl+Shift+X), a list of every tab including
  the folded ones, and **the tab search finds what you closed** too.
- **Close tabs you have not looked at for N days**, keep a group instead
  of losing it, ask before closing a window with many tabs, and a rule
  that always opens a site in a chosen virtual browser.

## 2026-10-14 — what the tabs cost, and a look of your own

- **What the tabs are costing** (Ctrl+Shift+Esc): one row per tab with
  the memory and processor time of its renderer, heaviest first, each
  row able to jump to the tab, put it to sleep or close it. Tabs that
  share a process say so instead of being counted twice. The numbers
  come from `/proc` on this machine; nothing is estimated.
- **The hover card over a tab** now says the address, the virtual
  browser, what the tab is using, and whether it is asleep.
- **Put a tab to sleep after N minutes** without looking at it (off by
  default; never the tab in front, never one making a sound, never a
  pinned one).
- **Lite mode**: no images, nothing playing by itself — for a tethered
  phone or a hotel's wifi.
- **Clear the cache** in every virtual browser, and **how long the
  browser took to start** in Settings.
- **Your own CSS for a site** (Ctrl+Alt+U): put on the page last, so it
  wins over the site and over the theme, and kept per host.
- **The zoom is remembered per site**: a site opens at the level you
  last read it at (on by default, switchable).
- **A theme that follows the clock**: a day theme and a night theme with
  the times between them.

## 2026-10-14 — downloads, history and a read-later list

- **Sort downloads into folders** (off by default): Pictures, Video,
  Music, Documents, Archives, Programs and Mods, beside the downloads
  folder. A `.jar` or an `.mrpack` lands in Mods.
- **Open the folder when a download finishes**, as a setting.
- **Download from this page** in the page menu: every picture (including
  the ones that are only a CSS background), every video and sound, or
  every linked file — fetched through the browser's own session, so a
  site that only serves its pictures to someone logged in still hands
  them over. More than five asks first.
- **What a file really is**: the SHA-256 of a finished download, and a
  warning before opening the kinds that run when you open them (.exe,
  .jar, .sh, .AppImage …).
- **Search the history by what was on the page** (off by default): a few
  hundred words of each page you visit, kept on this computer, so a page
  can be found by its contents when its title says nothing. Never from a
  private tab, and never for a site on the never-remember list.
- **Read later** (Ctrl+Alt+D) puts the page on a list and
  **Ctrl+Alt+Shift+D** opens it; choosing one opens it and takes it off.

## 2026-10-14 — a panel beside the page, and game mode

- **A side panel** (Ctrl+Shift+Y) that holds any site next to the page —
  Discord, Amazon Music, Claude, ChatGPT, Modrinth, this page, or
  anything you type. It is a real web view on the same cookie jar, not
  an iframe, so the sites that refuse to be framed are exactly the ones
  it works with, and they are already logged in. The divider is yours
  and the width is remembered; one button sends what is in the panel to
  a tab of its own.
- **Twitch chat** (Ctrl+Alt+W) opens the chat of the stream you are
  watching in that panel, beside the stream.
- **Game mode** (Ctrl+Alt+G): every other tab asleep (its renderer
  handed back, its place kept), everything muted, notification requests
  refused without a card, and the browser itself stepped back a little.
  Pressing it again wakes exactly the tabs it put to sleep.
- **Put the other tabs to sleep** (Ctrl+Alt+Z) on its own, without game
  mode. A tab that is playing something, or that is pinned, is left
  alone.
- **Minecraft servers** (Ctrl+Alt+J): your servers from
  `config["mcServers"]` ("Practice=host:port"), each asked the same
  question the game's own server list asks — online, players, version,
  MOTD and latency. Opt-in watching says so in the corner when one stops
  answering or comes back. It is thirty bytes of the Minecraft protocol
  and no library, and it runs only for servers you listed.
- **Discord: mute** (Ctrl+Alt+Q) and **deafen** (Ctrl+Alt+Y) press the
  buttons in the Discord tab from anywhere in the browser, with the
  Discord tab in the background.

## 2026-10-14 — reading

- **Reader mode** (Ctrl+Alt+R): everything that is not the article is
  taken off the page — the menus, the sidebar, the footer — and what is
  left is set in one column in the theme's own colours. It keeps the
  page's own DOM, so the images, the code blocks and the links all still
  work, and one more press puts the page back exactly as it was.
- **Headings** (Ctrl+Alt+O) lists the page's headings and jumps to them;
  **Word count** says how many words there are and how long they will
  take, for the page or just the selection.
- **Link hints** (Ctrl+Alt+K): a letter on every link and button, type it
  to follow it — Vimium's `f`, without taking a key from any site until
  you ask for it.
- **Read aloud** (Ctrl+Alt+V) reads the selection, or the article, with
  the machine's own voice through speech-dispatcher. Nothing is sent
  anywhere, and it says so plainly when there is no speech program.
- **Highlight the selection** (Ctrl+Alt+B) marks it, keeps it for that
  address, and puts it back on the next visit.
- **The reading switches**, per page: high contrast, a readable font,
  wider text spacing, stop animations, stop animated images, a big
  cursor, and a focus ring that is always visible — plus a smallest text
  size for one site.

## 2026-10-14 — the agent bridge learns fourteen things

New ops (and the same names in `agent.py`), all of them working on tabs
that are not in front and without raising the window:

- **markdown** — the readable part of a page as Markdown, links kept and
  the furniture dropped. What a model should be handed instead of two
  megabytes of HTML.
- **box** — where an element is, whether it can actually be seen, and
  what it looks like; **find** — elements by the words on them, each with
  a selector that works. Together they are "click the Save button"
  without guessing a selector.
- **fill** — a whole form from one selector-to-value map, with the input
  and change events a page listens for.
- **idle** — waits until the page has gone quiet for a while, which on a
  modern site is the only honest "it has finished loading".
- **links**, **tables** — every link (filterable) and every table as rows.
- **console** — what the page logged and what it threw. Errors now reach
  the log at all: the page is asked to turn `window.onerror` and an
  unhandled rejection into a console line, because the engine keeps
  uncaught exceptions to itself.
- **dialog** — what the page's next `alert`, `confirm` or `prompt` gets
  told, and what the last ones asked. Without it a script driving a page
  stops dead at the first `confirm()`.
- **pdf** — the page printed to a file.
- **cookies** — the names, domains and expiry dates of a site's cookies,
  never their values.
- **bookmarks** — search them, or add a page; **downloads** — what has
  been downloaded; **notify** — a line in the corner of the browser, for
  a script to say it has finished without stealing the screen.

## 2026-10-14 — one list of actions, and the mouse

- **A command palette** (Ctrl+Shift+K): every action the browser has, by
  name, filtered as you type, with its key beside it. (Not Ctrl+Shift+P
  — that has opened the password manager here for years.)
- **A cheat sheet** (Ctrl+/): every key there is, on one page.
- **Every shortcut can be changed** in Settings > Keyboard shortcuts,
  with a check that two actions never want the same key, and one button
  back to the usual set.
- Behind all three: the keys are now built from one list of actions
  rather than two dictionaries, so an action added once turns up in the
  keys, the palette, the cheat sheet and Settings together.
- Mouse gestures were built and taken out again: they need a Python
  event filter on the widget the engine draws into, and that crashes
  this PyQt build when the interpreter shuts down (two crashes in six
  runs with it, none in eight without). The same filter is the only way
  to see Alt+click on a link, so that went with it. What is written down
  in FEATURES.md is what was measured.
- **Ctrl+Alt+C** copies "title — address", **Ctrl+Alt+Shift+C** a
  Markdown link, **Ctrl+Alt+F** searches for the selected words, and
  **F6** moves the focus between the address bar, the page and the tabs.

## 2026-10-14 — the small developer tools

- **JSON as a tree** — a JSON response folds, instead of being one long
  line of text; click to open and close.
- **Show as a table** — a CSV or TSV file becomes a real table, quoted
  commas and all.
- **Format this file** — a minified `.js` or `.css` gets its line breaks
  back, and gives them up again on a second press.
- **Page source** in a tab of its own, with numbered lines, taken from
  the document the renderer actually has.
- **Copy this element as** a CSS selector, an XPath or its HTML, for
  whatever is under the cursor; **Pick the colour here** reads the pixel
  under the cursor and copies it as hex, with rgb and hsl alongside.
- **Copy buttons on code blocks**, on any site.
- **Copy as curl** — the page's address with its user agent and language.
- **Servers on this machine** — what is listening on the ports a
  developer uses (3000, 5173, 8000, 8080, 8123 …), each one a click away.
  It connects and disconnects; nothing is requested and nothing leaves.
- **The address bar converts things**: `b64 hello`, `b64d aGVsbG8=`,
  `url Hallo Welt`, `urld …`, `hex AB`, `html <b>`, `ts 1700000000` and
  `jwt <token>` (the header and the payload, not a verification).

## 2026-10-14 — privacy, per site

- **Websites cannot reach the home network.** A page on the internet
  that navigates — itself or one of its frames — to `192.168.x.x`,
  `localhost` or a `.local` name is refused: the router, the printer,
  Home Assistant and the Minecraft servers are not part of the web. On
  by default; one local page may still reach another.
- **Strip tracking from addresses** (off by default): `utm_*`, `fbclid`,
  `gclid` and the rest come off the address before the page is asked
  for. It works on what the browser navigates to, not on every request a
  page makes: blocking at that level needs the engine's request
  interceptor, and a Python interceptor crashes this PyQt build when the
  interpreter shuts down (measured, five times in six). Blocking tracker
  hosts and third-party cookies wait for the same reason.
- **Per site, from the page menu:** no JavaScript, no images, no
  blocking, always open privately, never remember it (nothing in the
  history and nothing in the address bar), clear what it has stored, or
  forget it entirely — cookies, cache, storage, history, permissions and
  its place in the address bar's memory.
- **A privacy report** on the page menu: how many requests were turned
  away and which hosts kept asking.
- **Ctrl+Alt+P — panic.** Everything muted, every tab on a blank page,
  every panel shut, the vault locked.
- **Ctrl+Alt+H — streamer mode**: the address bar's text is hidden while
  you are sharing the screen.
- The work is in `privacy.py`, loaded the safe way: without the file the
  browser starts exactly as before.

## 2026-10-14 — screenshots

- **Ctrl+Shift+S** captures what is on screen, **Ctrl+Alt+Shift+S** the
  whole scrolling page — taken a screen at a time and stitched, with
  everything fixed to the window pinned into the page first so a header
  is not repeated down the picture.
- **This element** captures exactly the thing under the cursor, and an
  area capture takes a rectangle.
- **Password fields are blurred** before the shutter, so a screenshot of
  a login page is safe to paste (Settings > Browsing).
- **Small enough for Discord**: the same picture fitted under the upload
  limit, quality first and size only if it has to.
- **Keep it on top** puts a capture in a small window above everything;
  double-click or Ctrl+C copies it.
- **In a moment** waits 3 or 10 seconds, for a menu or a hover state that
  a click would close.
- Folder, file-name pattern (strftime, `{title}`, `{site}`) and format
  (PNG, JPEG, WebP) are in Settings. The work lives in `capture.py`,
  loaded the safe way: without the file the browser starts as before and
  simply has no capture entries.

## 2026-10-14 — page tools, and the video on it

**On any page** (right-click > Page tools): allow copying and right-click
on a site that blocks them, unpin fixed bars so the window shows the
page, stop everything that moves, expand every "show more" and
`<details>`, make the page editable, mark visited links, a scroll-to-top
button, show a password field as text, freeze the page, and the feeds
the page offers.

- **Links:** open where a redirect wrapper really goes (`google.com/url?q=`,
  YouTube's, Discord's), open a link in a private tab or in another
  virtual browser, copy the link clean, copy its text, or copy both as a
  Markdown link. **Alt+click saves a link** instead of opening it.
- **Copy a link to the selected words** — a text fragment, so opening it
  scrolls there and marks them.
- **Right-click Back or Forward** for the tab's own history several steps
  at a time; **middle-click** does that step in a new tab. Reload's menu
  has "reload without the cache" (also **Ctrl+Shift+R**) and "back to this
  site's first page".
- **Alt+Up** goes one level up the address; **Alt+Shift+Left/Right** follow
  the page's own previous/next link (or count the number in the address);
  **Alt+[** and **Alt+]** jump between headings.
- **The link under the mouse** is shown at the bottom left, with redirect
  wrappers unwrapped, so you see where it really goes (Settings > Browsing).

**Video and sound** (right-click > Video and sound, and the keys):

- **Ctrl+Alt+Space** play/pause, **Ctrl+Alt+Left/Right** seek ten seconds,
  **Ctrl+Alt+Up/Down** change the speed from 0.25x to 16x with the pitch
  kept, on any site's player.
- **Volume above 100%** — up to 400% through a gain node, per tab.
- **Loop a section** (Ctrl+Alt+L: A, then B, then off), **frame by frame**,
  **copy this frame** as a PNG (Ctrl+Alt+S), **copy the link at this
  moment** (Ctrl+Alt+T, YouTube and Twitch style), **jump to live**, and
  **do not start the next video**.
- **Speed and volume are remembered per site**, so a podcast stays at 1.5x
  and one loud site stays turned down.
- **Ctrl+Shift+Space** pauses everything playing anywhere and puts exactly
  those back; **Ctrl+Alt+M** jumps to the tab making the noise;
  **Ctrl+Alt+A** opens a list of every tab that is playing, with
  play/pause, mute and volume for each. **A sleep timer** stops everything
  after 15 to 90 minutes.
- An option for **the mouse wheel over a video to set the volume**.

## 2026-10-14 — the address bar answers back

- **Search keywords.** `yt cats`, `mr sodium`, `gh qtwebengine`, `amz ssd`,
  `w dampfmaschine`, `so segfault`, `cf create`, `mc anvil`, `tw`, `map`,
  `dict`, `aur` — fourteen to start with, and your own in
  `searchKeywords` (any URL with a `%s` in it) over the top of them.
- **The bar works things out itself**, offline, and never sends what you
  typed anywhere to do it: `12*64+3`, `2^10`, `5 in to mm`, `200 c to f`,
  `4 gib to mb`, `time in tokyo`, `kw`, `days until 24.12.`,
  `today + 30 days`, `#ff8800` and `rgb(255,136,0)`. Enter on the answer
  copies it.
- **Suggestions from your own browser first**: a tab that is already open
  on what you typed (Enter switches to it instead of loading it twice),
  your bookmarks, and your history matched on words in any order, not
  only on the beginning of an address.
- **An empty address bar** offers a link you have just copied, then the
  last things you searched for. **Shift+Delete** takes a suggestion out
  of the history for good.
- **`?` or Ctrl+K** makes a search of what follows even when it looks like
  an address. **Alt+Enter** opens it in a new tab. **Ctrl+Enter** finishes
  a bare name with `www.` and `.com`, **Ctrl+Shift+Enter** with `.de`.
- **Paste and go** and **Copy clean address** in the address bar's own
  right-click menu, with **Copy page as** → Markdown link, HTML link, or
  "Title — address". A clean address has `utm_*`, `fbclid`, `gclid`, `si`,
  `ref_src` and thirty other tracking parameters taken off, and keeps the
  ones the page itself needs.
- **On a page:** "Search for …" on the selection, with a submenu for every
  keyword; "Search this site" (`site:` on your engine); and "Search for
  this image", which asks first, because it is the one search that sends
  something you did not type.
- **A results page shows what you searched for** in the bar instead of the
  engine's long address, ready to edit (Settings > Browsing).
- **The zoom level** appears in the address bar when a tab is not at the
  level Settings holds; a click puts it back.

## 2026-10-14 — what you can do to a tab

- **Pin a tab.** It shrinks to its icon, moves to the front of the strip,
  is not closed by Ctrl+W, comes back at the next start, and (as a
  setting) keeps links to other sites out: they open in a new tab
  instead of taking the pinned tab away.
- **Mute a tab** from its own menu or with Ctrl+M, with a mark on the
  tab while it is silent, and **"Play sound only here"**, which mutes
  every other tab.
- **Lock a tab** so it asks before it closes — for a long form or a
  stream you do not want to lose to a stray Ctrl+W.
- **Rename a tab.** The name you give it stays whatever the page calls
  itself afterwards, and across restarts.
- **Duplicate tab** (Ctrl+Shift+D), **close other tabs**, **close tabs
  to the right / to the left**, **close duplicate tabs**, **close every
  tab of this site**, and **group every tab of this site** in one step.
- **Sort the tabs** by site or by title; **copy the addresses** of this
  tab or of every tab, as plain text or as Markdown; **open every
  address in the clipboard** as tabs; **bookmark every tab** into one
  new folder; **reload every tab**, or every tab in a group.
- **Open this page in another virtual browser**, or in a private tab,
  straight from the tab menu — the quick way to see a site logged in and
  logged out side by side.
- **Recently closed**: a list of the last 25 closed tabs in the tab
  menu, not only the last one Ctrl+Shift+T brings back.
- **Ctrl+1 … Ctrl+8** jump to a tab, **Ctrl+9** to the last one, and
  **Ctrl+Shift+PgUp / PgDn** move the current tab along the strip.
- **After closing a tab, go to** (Settings > Browsing): the tab to the
  right, to the left, or the one you were on before.
- **A count of open tabs** after the + , and a setting for what the
  **mouse wheel over the tab strip** does: nothing, scroll a strip that
  is too long, or switch tabs.

## 2026-10-14 — websites look like websites again

- **Pictures keep their own colours.** Every dark theme put a
  `brightness(.94)` filter on every `<img>` and `<video>` on the web;
  that is gone. Sepia and Newspaper still tint and grey their photos —
  that is what those two are — but mildly, and no other theme touches a
  picture at all.
- **Text is checked before it is recoloured.** The site theming used to
  decide a colour from a selector ("every heading gold") or from
  brightness alone, which is how gold headlines ended up on the blue
  tagesschau panel and how Amazon's own light text ended up on a white
  one. Now every colour it writes is measured against what is really
  behind the text: under 4.5:1 it tries another, and text sitting on a
  photo or a gradient it leaves exactly as the site drew it.
- **Coloured buttons keep their colour.** "Add to cart" orange, a red
  error strip, a brand header: a fill with real colour in it is the
  site saying something and is no longer repainted in the palette.
  Cards, panels, table stripes and form fields — the greys and whites —
  still take the theme.
- **Icon fonts are left alone.** The theme's own face is now forced
  only on running text (body, paragraphs, headings, quotes). It used to
  be forced on links, buttons, list items, table cells and form fields
  as well, which took the icon font off anything wearing one — Material
  Icons and Font Awesome glyphs came out as the word "delete" or as an
  empty box — and changed text widths inside boxes that were measured
  for another face, so nav bars and buttons overflowed.
- **A page that paints itself late is noticed.** The pass used to look
  at an element once and keep that first look for ever, so a stylesheet
  that arrived after it (Wikipedia's table of contents), a single-page
  app re-rendering a row or a class landing on scroll stayed in the
  site's own colours — dark text on the dark page. It now tells its own
  work from the site's and reads an element again when the site has
  moved it.
- **Big pages are themed to the end.** It gave up after 8000 elements;
  the GNU bash manual has 19431 and the bottom half of it was raw.
- **The theme's texture stays under the page.** Scanlines, the Game Boy
  bezel, the steampunk brass grid and the vignettes were drawn above
  everything a site can position, dialogs and menus included. They now
  sit above the page and below anything the site puts on top, and the
  vignettes are about half as heavy, so photos near the edge of a page
  are not darkened.
- **No theme changes a site's layout.** Letter-spacing on the whole
  page (C64), padding on headlines (Newspaper) and a button that moved
  under the cursor (Game Boy) are gone; a check in the test suite now
  fails if any theme sets position, z-index, display, overflow, margin,
  padding, transform, line-height or a size on a site element.
- **Auto-darkening is decided in one place.** `page_darkening()` answers
  "nothing, the theme, or Chromium's inversion" for a page, and exactly
  one of the three is ever on, so a page can never be darkened twice.
- Google in light colours no longer turns pictures loaded as CSS
  backgrounds into negatives.
- The theming pass is faster where it matters: an element is queued
  once however often the page mentions it, the page is only re-read in
  full a few times, and it comes back for the next slice through a
  MessageChannel instead of a timer — a tab he has not looked at yet
  used to be themed at 600 elements a second, because Chromium throttles
  timers in a background tab to one a second.


## 2026-10-04 — websites in your theme

- **Websites take on the browser's theme.** Every site is recoloured in
  the palette of the theme you picked, and the character themes bring
  their own face (Terminal glows, Newspaper prints in serif). It is on
  by default and switched in Settings > Appearance > "Theme websites".
- **Right-click a page > "Don't theme this site"** for a site it gets
  wrong; "Theme this site" brings it back. Sites that are dark by design
  and Google (which has its own switch) are left alone.
- On a themed site auto-darken steps aside, so pages are not darkened
  twice; on everything else it works as before.
- Switching it off takes the theme off open tabs at once, without a
  reload. Pages no longer fade in from white as they load.
- Works on sites with a strict security policy, keeps cookie-banner
  backdrops see-through, and keeps up with pages that restyle themselves.
- The engine pane (Ctrl+Shift+E) says so instead of crashing on a page
  nested deeper than it can draw, and is no longer squashed to a strip
  on themed pages.
- The "page stopped responding" message is readable again.

## 2026-10-04 — Update never throws work away

- **Update no longer wipes uncommitted changes in a git copy.** When a
  pull could not fast-forward, it ran `git reset --hard origin/HEAD`:
  uncommitted edits were gone, unpushed commits dropped out of sight, and
  a feature branch was moved onto main - and it said "Updated!". Now it
  stops and says why when there are uncommitted changes, resets only onto
  the branch's own upstream, and keeps the old version as a branch
  `update-backup-<time>` first.
- The agent bridge socket is owner-only (0700) whatever the umask, and
  its `wait` answers no-such-tab instead of hanging when the tab closes.
- Widevine: WIDEVINE_PATH and Chrome's own updated copies are used again
  instead of being dropped when the proxy flags were installed.

## 2026-10-04 — the bug sweep (from the Windows edition)

- **Logins survive closing the browser.** It used to end itself before
  Chromium had written its cookies to disk (it does that only every
  thirty seconds or so), so whatever you had just signed in to was
  forgotten at the next start. The cookie jars are now closed properly
  first.
- **No more see-through window.** Every look made the window
  translucent, and Windows does not blur what is behind one: the
  desktop showed straight through, with a strip under the tabs that
  filled with leftover junk. The window is solid on Windows now, Liquid
  Glass included — it keeps its shapes on the theme's own base.
- **Themes are readable again.** Most of the "unreadable" was text
  drawn over the desktop through that hole. The browser also uses one
  style of its own on Windows now, instead of Windows 11's, which mixed
  light system colours into dark themes.
- **Search suggestions no longer run into each other.** The highlighted
  row stands out, the scroll bar is dark, and the last row is no longer
  cut off.
- **Update works.** A fresh install did not know which version it was,
  so it always said "Update available" and "Updated!" changed nothing;
  it now checks its own files. The check no longer uses GitHub's API,
  which stopped answering after sixty checks an hour from one network.
  An update is written beside the old files and swapped in, so an
  interrupted one cannot leave a broken browser behind.
- **Saved passwords are no longer destroyed on Windows.** Windows
  quietly turned every line-feed byte in the password files into two
  bytes, so after a restart the vault read as empty or the master
  password was refused. Fixed — and a vault damaged that way is
  repaired the next time it is opened, so passwords that "vanished"
  come back, as long as no password was saved since.
- **A lost password key no longer costs the vault.** The vault it
  belonged to is put aside as passwords.json.unreadable-… instead of
  being written over, so restoring the key from a backup still opens it.
- **No more crash when a site joins a call** (Meet, Discord): a
  Linux-only option ended the browser on the spot.
- **A website can no longer install a plugin without asking.** A
  download named *.user.js went straight into the plugins folder and ran
  on every site from then on. You are asked first now, and No saves it
  as an ordinary download.
- **Your data files are written safely.** Settings, history, bookmarks,
  downloads and known sites are written beside the old file and swapped
  in, so a crash or power cut mid-save leaves the old file rather than
  half of one; a file that cannot be read is put aside
  (name.corrupt-…), not silently replaced with nothing.
- **Open tabs survive a crash.** They are saved every thirty seconds,
  not only when the browser closes normally.
- **An unexpected error no longer makes the window vanish.** The
  browser keeps going and writes what happened to crash.log in its data
  folder.
- 1Password: names and passwords with umlauts are no longer garbled, and
  no console window flashes up on every call.
- A second Windows user on the same PC can open the browser while the
  first has it open.
- Downloads go to your real Downloads folder, even when it was moved to
  another drive.
- install.bat makes the shortcut start the same Python it installed
  into; with two Pythons on the PC the shortcut used to do nothing.
- "Open in player" finds VLC where Windows installs it.
- Crash detection works on Windows.
- **Esc leaves video fullscreen.** It reached the video and the window
  stayed fullscreen; closing or leaving that tab stranded the window
  with no tabs and no address bar.
- **Shift+Tab moves back through a form again.** It was taken for
  switching virtual browsers, which also closed Settings mid-form. That
  is Ctrl+Alt+PgDown / Ctrl+Alt+PgUp now.
- **Pop-ups need a click.** Any page could open tabs on its own.
- The address bar understands localhost:3000, 127.0.0.1:8000, router
  addresses, http://… and file:///… typed out, and a Windows path
  pasted from Explorer — instead of searching Google for them.
- Opening a new tab and closing it at once no longer crashes the
  browser.
- A link opened from a tab in another virtual browser lands in that
  browser instead of as an empty tab.
- Renaming a group keeps it in its own virtual browser; "Add tab to
  group" only offers the tab's own browser's groups.
- Closing the last private tab no longer kills its downloads, and
  closing a virtual browser with private tabs forgets their cookies.
- A permission question goes away with the tab that asked it.
- Picking a suggestion with Enter loads the page once, not twice.
- **A proxy profile with a bad port can no longer stop the browser
  starting**, and picking a proxy profile in Settings selects it
  instead of deleting it.
- Frutiger Aero: the bottom of the Settings sidebar and footer are
  readable again.
- One broken address in the history no longer hides every older entry;
  the time column no longer wraps in 12-hour locales.

## 2026-09-18 — Save any image

- **Right-click → *Save image* on anything drawn under the cursor.** The
  engine's own entry only appears on a bare `<img>`; this one looks at the
  whole stack under the pointer (`IMAGE_AT_POINT_JS`) and takes the first
  picture in it: an image under a transparent overlay, a `<picture>`, a
  video poster, a CSS background, an inline SVG, a canvas. Things with an
  address download through the engine as usual; a canvas or inline SVG has
  none and is written straight into the download folder, listed like a
  printed PDF. A spot with no picture says so in a tooltip.
- **`Shift` + right-click always opens the browser's menu**, even on sites
  that swallow the gesture to keep their pictures (`FORCE_MENU_JS`, capture
  phase on the window, every frame). A plain right-click is still the
  site's.
- `test_saveimage.py` covers all of it and is in `tools/runall.sh`.

## 2026-09-11 — An agent bridge: scripts can drive the tabs

- **A second local socket, `browser-agent`, lets a script on this
  machine drive the browser** (`agent_bridge.py`, client `agent.py`).
  One JSON request per line; open/close/select/nav a tab, run JS, read
  text or HTML, wait for a selector, click, type (native-setter inputs
  and contenteditable editors both react), press a key, scroll,
  screenshot, or ask for the browser's own restart. Everything works on
  background tabs and never raises the window: the point is that an
  assistant can use the web without taking the screen away from whoever
  is at the PC. `agent.py chatgpt "..."` is the one composite command —
  it keeps a hidden chatgpt.com tab and returns the finished answer.
- Off switch: `"agentBridge": false` in the config, or `BROWSER_NO_AGENT=1`.
  The socket is user-owned; it is not reachable from the network.
- `test_agent.py` (offscreen, scratch data, its own socket name) covers
  the whole protocol and is part of `tools/runall.sh`.

## 2026-08-14 — The browser says when a tab is on a call

- **A call in a tab is now announced to the rest of the machine.** While
  at least one tab holds a live microphone track, the browser keeps a
  file at `$XDG_RUNTIME_DIR/browser-call.on` (the temporary directory if
  there is no runtime one) and refreshes its timestamp every five
  seconds; it is removed when the last capture ends, when the capturing
  tab closes, and on the way out. Nothing is written *into* it — not the
  site, not the tab, not the number of tracks. Its existence is the
  whole message, and the timestamp is there so that a browser killed
  outright cannot leave a lie behind: anything reading it treats a file
  older than fifteen seconds as over.
  - Why: a desktop that mixes browser audio into a virtual microphone
    (to share a song into a call) feeds the call's own audio back into
    the microphone when the call is in the browser, and echo
    cancellation then eats the speaker's voice. The audio side can stop
    sharing while a call is up — it only needed to be told.
  - How: the engine has no per-page "is it capturing" to ask, so
    `getUserMedia` is wrapped in the page's own world — both the modern
    one and the callback-shaped one the engine still carries — and every
    audio track it hands out is counted as live until it ends, is
    stopped, or is replaced by a clone of itself. The wrapper is
    additive and nothing else: the original runs, with the original
    arguments, and its promise comes back with the same stream or the
    same error; the page's own `stop()` still runs, and runs first. Each
    wrapped function is a proxy of the one it replaces, so it carries
    the same name, the same arity and the same own properties a native
    method has — the one visible difference is that a proxied function
    prints without the method's name inside its `[native code]` string.
    Everything the wrapper uses after the page is allowed to run — the
    dispatcher, the listener, the promise's `then`, the `readyState`
    and `kind` accessors — is taken at document creation, before a line
    of the page's own script has run, so a site cannot hand itself the
    wrapper's internals or lie to it about its own microphone: a page
    holding the microphone cannot make this browser believe it is not.
    The count crosses to the browser in an isolated world, on a DOM
    event whose name is a fresh random token each run.
  - What this deliberately does not promise: a page can create an
    iframe of its own, replace that frame's dispatcher before the
    wrapper reaches it, and read the token out of the frame as soon as
    the frame captures anything — and with the token it can claim a
    call it is not on, or drop the count on one it is. Only for its own
    tab, and only for the flag: no other tab is reachable and nothing
    about the person using the browser is in the file at all. It is not
    fixable inside this design (the two worlds meet on the page's own
    DOM, so any rendezvous the wrapper can use, a page that owns the
    frame can eventually listen for), and the fix that would work —
    refusing to count in frames the embedder can reach into — would
    trade a nuisance for a real call going unnoticed, which is the echo
    this exists to stop. So it is written down instead.
  - Every cookie jar carries it, including a private tab's — a
    microphone held there is still a microphone held — and every frame,
    because a meeting is very often in an iframe.

## 2026-08-13 — A denied permission is not a life sentence

- **Reloading a page lets it ask again.** A "no" to a microphone, camera
  or notification card used to hold for the whole run of the browser —
  one mis-click and only a restart could take it back. Now the answer
  lasts until you reload: the toolbar button, Ctrl+R, F5 or the context
  menu all hand the site its questions back. Only your reloads count — a
  page reloading itself gets nothing — and only denials are forgotten;
  an "always allow" you granted stays granted.
- **Screen sharing actually shares.** The engine ships with screen
  capture switched off, and the way it says no is cruel: the picker and
  the compositor's dialogs all appear and work, and only after the last
  of them is answered does the stream die ("AbortError: Invalid
  state"). The capture switch is now on; the picker and the site's own
  controls still decide what is shared, this only stops the engine
  vetoing everyone at the finish line.

## 2026-08-11 — Looks: the browser in four shapes

- **A look is what shape the browser is, the way a theme is what colour it
  is.** There are four, in Settings → Look, and the setting is orthogonal
  to the theme: every look works with every one of the palettes, because a
  look owns geometry and never a colour. Switching one lands the way
  switching a theme lands — the window, the furniture, the cookie jars and
  every one of the browser's own pages that is already open, all at once,
  with nothing restarted.
  - **Classic** is the default and is the browser exactly as it was. It
    builds no widget and adds nothing at all to the stylesheet, so
    "unchanged" is enforced rather than promised — a test asserts the
    sheet is byte for byte the theme's own.
  - **Taskbar** puts a strip along the bottom of the window: a start
    button, your pinned sites, a `+` that pins the page you are on, and a
    clock. A pin whose site is already open is underlined, and clicking it
    brings that tab forward instead of opening the site twice. The start
    button opens a search box over a grid of the pins, which is the shape
    Windows 11 uses.
  - **Dock** floats a rounded island over the page with the same pins on
    it, magnifying under the cursor, and rounds and loosens the rest of
    the chrome to match. It also carries a now-playing widget: when a tab
    is making a sound, its title appears there and the three transport
    buttons work the site's own play, pause and skip.
  - **Circle** turns the start page into a ring — the search box in the
    middle, the quick links orbiting it, the mouse wheel turning them and
    the labels staying upright as they go. The caret still lands in the
    search box, as it always did.
- **Pinned sites are the start page's quick links.** One list, not two:
  pin from any page's right-click menu, from the `+` on the taskbar, or by
  adding a quick link on the start page, and the other places show it
  immediately — an open start page redraws without a reload. Only http(s)
  addresses are ever pinned, and never from a private tab.
- **A 115th theme: Frutiger Aero.** Deep sky, aqua glass and a white
  highlight down every panel — the y2k look, on the With character shelf.
  It is an ordinary palette in every other respect, so it works in all
  four looks like the rest of them.

## 2026-07-30 — Update says what is wrong

- **The Update button on a copy unpacked from a zip now says so**, instead
  of showing you a sentence about filesystem boundaries. A zip has no link
  back to GitHub, so there is nothing for the button to pull; it tells you
  that, and tells you the two ways to fix it — take the newest zip, or
  replace the folder with a clone.
- It no longer starts git at all in a folder that is not a working copy.
  That mattered for more than the message: git run inside such a folder
  hunts *upwards* for a repository, so a copy unpacked inside one — a
  Downloads folder that happens to sit under a checkout, say — could have
  had the wrong repository pulled underneath it.

## 2026-07-29 — The Favourites panel keeps its bottom row

- **The buttons along the bottom of the Favourites panel are not cut in
  half any more.** In a window with less room under the folder button
  than the panel wanted, the panel was drawn at the height its list
  asked for and then simply ran off the bottom edge of the window,
  which cut whatever was down there — usually straight through the
  middle of the letters on **Remove bookmark**, so the word was there
  but the lower half of it was not. The panel now measures the room it
  actually has and never asks for more than that, and it measures again
  every time the list under it changes rather than only when it opens.
  That last part is what made it turn up when it did: bookmarking the
  page you are on from the panel adds a row *and* changes that button
  to say Remove, so the panel grew past the edge at the very moment the
  new wording appeared on the button being cut.
- **A panel that has to be shorter than its list stops at a whole row.**
  It never ends halfway down one, because a row sliced through the
  middle looks exactly like text with its bottom cut off, which is the
  thing being fixed and not a thing to move somewhere else.
- **A row of the list grows with the writing in it.** Its height had
  been nailed to thirty pixels, which is right for the font it was
  drawn against and wrong for any larger one — a fixed height does not
  grow, it cuts. It is now a floor rather than a ceiling: the same
  thirty pixels at the size everyone sees, and taller when the writing
  is taller. Nothing looks different today; a bigger font later will
  not lose the tails of its g's and its ß's.
- There is a suite behind all of this now. Every text row of the panel
  — the title, the hint, the search box, the three buttons and the rows
  of the list — and every entry of a row's ⋯ menu is measured against
  the line its font actually draws, at three font sizes, in German
  where the words are longest and the umlauts sit highest; and the
  pixels are read back to check that nothing is drawn against the
  bottom edge of its own box. The card is measured against the window
  at five window heights and four collection sizes.

## 2026-07-29 — a master password

- **The passwords can be locked with a passphrase of your own, and
  until now they could not.** What was there before is worth saying
  plainly: the saved passwords were scrambled with a key kept in a file
  lying next to them, so anything running under your computer account
  could read both and therefore read the lot. Switch a master password
  on and the key stops being a file. It is worked out from the
  passphrase you type, every time, and there is nothing on this
  computer that can produce it while the vault is shut.
- **If you forget it, your passwords are gone.** There is no reset, no
  recovery key, no back way in, and nobody — not you, not the browser,
  not whoever wrote it — can get past it. That is not an oversight to
  be fixed later: a recovery key kept on this computer would be a
  second key to the same lock, sitting next to it, which is exactly the
  thing this feature exists to get rid of. The box that switches it on
  says so before you can switch it on, asks for the passphrase twice,
  and offers to export your passwords first so that a way back is
  something you chose knowingly.
- **Nothing changes until you ask for it.** It is off, and an install
  without a master password behaves in every respect the way it does
  today. It is under **Settings → Passwords** at any time, and **setup
  now asks about it on a page of its own** — the seventh of nine.
  It gets a page rather than a switch in a list because it is the only
  choice in setup you cannot take back afterwards, and that is worth
  stopping for. Setup only offers it on an install that has not got one
  already: changing the passphrase needs the old one, and that question
  belongs in Settings.
- **If the password manager is switched off, that page asks nothing.**
  It says there is nothing to lock, points you one step back if you
  want it, and lets you carry on.
- **Set in setup, it is in force the moment you finish.** Your saved
  passwords are sealed with it from then on and the key file is gone.
  The browser stays unlocked for that session, so the first login you
  make can still be offered for saving, and locks itself after fifteen
  minutes of not using your passwords.
- **Locked, the browser fills nothing and says nothing about it.** No
  sign-in form is filled, no account is listed, the chooser lists
  nothing, nothing is offered to be saved, and nothing at all is put
  into any page — so a website cannot tell a locked vault from an empty
  one. It does not nag either: no page ever raises the box, because a
  browser that asked on every login form would be asking six times a
  morning, and that is how people learn to click things away without
  reading them. You unlock when you want it: **Ctrl+Shift+L**, opening
  the password manager, the **@** account chooser, or Settings.
- **The passphrase is typed into a window of the browser’s own**, never
  into a page. A page that asked for your master password is a page a
  website could one day draw a convincing copy of.
- **It locks itself again after fifteen minutes** of the vault not
  being used, which you can set to anything from a minute to an hour,
  or to never. Ctrl+Shift+L shuts it there and then.
- **You can change the passphrase** without re-entering a single
  password, and switch the whole thing off again with everything still
  in it. Both directions survive being interrupted: the vault file is
  only ever replaced whole, in one step the filesystem either does or
  does not do, so a power cut in the middle leaves the file it started
  with rather than half of each.
- **With 1Password as the store,** a master password guards this
  computer’s way in rather than 1Password itself — nothing here could
  lock that. The service-account token is encrypted along with the
  vault, so a locked browser cannot speak to 1Password at all, and the
  token file on its own is unreadable.

## 2026-07-29 — Favourites, and folders inside folders

- **There is a folder in the toolbar now, and everything you have
  bookmarked is behind it.** Click it and a panel drops down: a title,
  a search box, and one list of everything you have kept. It is the
  button Edge calls Favourites, in the place Edge keeps it — just to
  the right of the address bar — because that is the browser some of us
  learned bookmarks in and there is no reason to make anybody learn
  them twice. `Ctrl+Shift+F` opens the same panel.
- **A folder opens where it is.** Click one and the list grows
  downwards to show what is inside it; click it again and it folds
  away. Nothing flies out sideways. A menu whose folders open sideways
  makes you hold the pointer inside a narrow corridor the whole way
  across, and one slip shuts the lot and you start again — which is a
  fiddly game at the best of times and an unkind one if your hands are
  not steady. This one stays where you put it, and a missed click costs
  nothing.
- **Type in the box at the top** and the list narrows to what matches,
  by name or by address, opening the folders that hold a hit so you can
  see where they were. Empty the box and everything goes back exactly
  as you had it.
- **Folders can go inside folders now**, as deep as you care to file.
  Before this they could not: every folder sat at the top level, and
  the browser quietly put one back there if you ever tried. Travel →
  Hotels → Vienna works, and so does whatever shape your own life is.
- **Renaming happens in the row itself.** No box in the middle of the
  screen to understand — the name turns into something you can type
  over, and Enter is the end of it. A new folder arrives that way too,
  already waiting for its name rather than sitting there called "New
  folder" for you to work out how to change later.
- **Every row has its own ⋯ at the right-hand end**, and it is always
  there rather than appearing when you happen to hover over it. It
  opens everything that can be done to that row: open it, put this page
  in it, make a folder in it, rename it, move it somewhere else, throw
  it away. A right-click on the row does the same, for anyone who has
  the habit — but nothing lives only there.
- **Drag things where you want them.** Pick a bookmark up and drop it
  into a folder, out of one, or between two rows to change the order.
  Folders can be dragged into folders too — never into themselves, and
  the browser will not draw a landing place for a move it is not going
  to allow. Dropping *into* a folder and dropping *between* two rows
  are different things, so they look different: a box around the folder
  for one, and for the other a line that starts where the rows it sits
  between start, so you can see which folder it is going into. The list
  scrolls itself if you drag near the top or the bottom of it, and
  letting go somewhere that means nothing does nothing.
- **You never have to drag.** Every row's ⋯ has **Move to folder** on
  it, with every folder listed and stepped in. Dragging is quicker if
  your hand is steady and the menu is there if it is not.
- **Bookmark this page, into the folder you choose.** The button along
  the bottom of the panel puts it at the top level, like the star and
  `Ctrl+D` always did; a folder's own ⋯ puts it in that folder. Either
  way, a page you had already bookmarked somewhere else is moved rather
  than copied, and the row it landed on is picked out so you can see
  where it went.
- Deleting a folder takes everything under it — folders inside it and
  their contents too — and says how many things that is before it does
  anything. Nothing is ever left pointing at a folder that has gone.
- **Nothing sits under the address bar any more.** The bookmarks bar
  used to appear by itself as soon as you had one bookmark. It does
  not: the folder button holds the whole collection, and a strip
  showing you the top level of the same thing is a second answer to a
  question that already has one, costing a row of the window for ever.
  `Ctrl+Shift+B` and the switch in **Settings → Toolbar** still bring
  it back, and if you had already switched it on it stays on — only
  the never-answered case changed.
- **The bookmarks bar itself is unchanged** for anyone who wants it.
  Its folders still drop their contents down as menus, which is what a
  bar wants, and they have grown New folder, Rename and Delete where
  you can see them. The bookmark manager now draws folders inside
  folders and has a **New folder** button beside every one of them.
- A `bookmarks.json` from before any of this loads exactly as it was.
  One edited by hand into a circle — a folder inside a folder inside
  the first one — no longer has to be right: the browser unties it on
  the way in, puts the tangle back at the top level and loses nothing,
  rather than walking round it for ever.
- The Favourites button ships switched on. **Settings → Toolbar** and a
  right-click on the toolbar can take it away again like any other
  button.

## 2026-07-29 — Zoom from the keyboard, and a tab that keeps nothing

- **Ctrl + and Ctrl − zoom the page, Ctrl 0 puts it back.** It steps
  the way browsers step — …67%, 80%, 90%, 100%, 110%, 125%… — fine
  where you are actually reading and coarse out at the ends, from 25%
  all the way to 500%. The level appears for a moment along the bottom
  of the window so you can see where you are, and see that Ctrl 0 did
  something.
- **Holding Ctrl and turning the wheel** climbs the same ladder. That
  one was already the engine's own doing, on that very ladder, and it
  is left to it — it lands where the wheel lands, which is more than
  this browser could promise, and a touchpad that reports the wheel in
  small pieces is its problem and it is good at it. What is new is that
  the browser notices: a tab you have wheeled keeps that size when you
  follow a link, Ctrl + carries on from there, and Ctrl 0 and the
  slider still reach it.
- **Zoom belongs to the tab.** Blowing up a comic strip does not blow up
  the mail tab next to it. Ctrl 0 goes back to the level **Settings →
  Appearance → Page zoom** is set to, and moving that slider still puts
  every tab there — so the number in Settings and the number a tab sits
  at can never drift apart.
- The zoom keys are about the page you can see. With Settings, history,
  downloads, bookmarks or the password manager open over the top of it,
  they do nothing at all: zooming the page behind a screen you cannot
  see past would look like the browser had ignored you. Ctrl+wheel
  inside one of those zooms the page you are pointing at and never the
  tab behind it, and it is back where the slider put it the next time
  you open it. The browser's own pages are not zoomed a tab at a time —
  they sit at whatever the Page zoom slider says, and move with it.
- **Ctrl+Shift+N opens a private tab**, and it is also in the menu you
  get by right-clicking a tab. It says **Private** next to the address
  bar — wherever you have moved the address bar to — wears a white line
  and a mark in the tab strip, and the window says it in its own name
  for as long as one is open.
- **A private tab leaves nothing behind.** No history. No entry in the
  address bar's suggestions, and nothing you type in it is sent off to
  be guessed at. No cookies or site storage once the last private tab
  closes — they were never written down in the first place, they only
  ever lived in memory. No saved password, and none offered: the
  password manager does not reach into a private tab at all, neither to
  fill nor to ask. The account chooser stays away too — the `@` in the
  address bar is gone, Ctrl+Shift+M does nothing, and no saved name is
  so much as read. A file you download still lands where files land,
  but it is not written into your downloads list — nor is a page you
  print to PDF out of one, and a userscript will not install itself out
  of one either. No favicon kept. It is never saved as a tab and never
  comes back at the next start, and Ctrl+Shift+T will not reopen it.
- Two private tabs are one place: a login in the first is still a login
  in the second, and a normal tab cannot see any of it. Close the last
  one and the whole thing is thrown away. A microphone or a camera you
  allowed in a private tab is forgotten with it, and one you allowed
  before cannot arm itself in one.
- Ctrl+D still saves a bookmark from a private tab. Asking for one is
  you saying "keep this", the same as asking for a download — what a
  private tab refuses to keep is the record it would have kept without
  being asked.

## 2026-07-29 — passwords a newer version saved

- **An older copy of the browser can no longer wipe your passwords.**
  If a newer version had saved them in a way this one does not
  understand, this one used to read the file as *no passwords at all*
  — and then the next time it saved anything, it wrote that nothing
  over the lot. Silently, with no error and nothing to undo. It now
  recognises a file it cannot read, refuses to touch it, and says so:
  nothing is shown and nothing is saved until you open it with the
  version that wrote it. Nothing is lost in the meantime.
- **Why this matters even though you only have one browser:** the
  Windows edition is rebuilt from the Linux one every so often, so for
  a while the two are not the same version — and going back to an
  earlier one, for any reason, used to carry the same risk.

## 2026-07-29 — a box to say which account

- **Two accounts on one site is no longer a coin toss.** With a work
  and a private Microsoft account saved, the browser filled whichever
  one you had used last and there was no way on the page to say you
  meant the other. Now, when more than one saved login matches the site
  you are on, the browser asks: a small panel listing the accounts by
  name, and the one you point at is the one that fills. One saved login
  is not a choice, so nothing about those sites changed — they fill on
  their own exactly as they always have.
- **Nothing goes into the form until you have chosen.** Not the
  password, and not the e-mail address either. While two accounts are
  saved for a site there is no answer to guess at, so the browser stops
  guessing: the sign-in form you are looking at is empty, and it stays
  empty if you dismiss the box without picking anything. Choosing is
  what fills it, both boxes at once.
- **The list is the browser's own window, not part of the page.** This
  is the whole reason it looks the way it does. A list of your accounts
  drawn into the page would be readable *by* the page, and then simply
  putting a sign-in form on screen would tell a site every account you
  keep there — before you had chosen, and whether or not you meant to
  sign in at all. The names never enter a web page: only the one
  account you point at crosses, and only to the site it was saved for.
- **Pointing at a name is the gesture that unlocks the password.** The
  rule that a saved password only reaches a page after you have really
  touched something is untouched — the touch is now a click on a panel
  of the browser's, which no website can reach, move, cover or fake.
  Nothing on the panel but the names: no password, no strength, no
  two-factor code, nothing worked out from a secret.
- **It also comes when you ask for it**, from the **@** in the left of
  the address bar or with **Ctrl+Shift+M** — after you have dismissed
  it, or to switch account later on the same page. The @ is only ever
  in the bar when that site really does have more than one account
  saved.
- **Two-step sign-ins work the way they read.** Microsoft asks for the
  e-mail on one screen and the password on the next, and swaps the form
  without ever reloading the page — the case that had been biting. The
  account you pick on the first screen is treated exactly as one you
  typed yourself, so the second screen, which has no e-mail box on it
  at all, still answers with that account and no other.

## 2026-07-28 — Settings, laid out

- **Settings looks designed now.** It was a column of outlined boxes
  all the same size, with headings floating above them in a type so
  small they read as captions rather than titles — everything one step
  apart from everything else, and nothing saying what belonged with
  what. Chrome's settings were the model for the fix, but only for the
  shape of it: settings that belong together are one raised card with a
  name on it, the hairlines run *between* the rows instead of drawing a
  box round every single one, the label and its plain-language line sit
  left with the control hard right down one axis your eye can run down,
  and the whole page was given room to breathe. Chrome's blue, its
  typeface, its rounded corners and its metrics were left where they
  were. This is his browser laid out properly, not Chrome in a
  Catppuccin coat.
- **There are four sizes of type doing four jobs.** The section title,
  the title of a card, the label of a row and the line of description
  under it. Before there were two sizes covering all four, which is
  most of why the page read as unfinished — a card heading was
  *smaller* than the row labels underneath it.
- **The search box moved out of the rail and across the top of the
  content**, where you are already looking, with "All settings" and the
  keyboard line beside it instead of stacked underneath. It sits just
  outside the pane it filters, on purpose: a search that matches
  nothing takes the pane away, and a search box that disappears the
  moment you mistype is one you cannot correct the typo in.
- **Not one new colour went in.** Every value on the page is still a
  palette token, so all 114 themes repaint the new cards exactly as
  they repainted the old boxes — a card is the same island colour the
  browser's own chrome uses, which on a light theme comes out as white
  cards on a grey page and on Mocha as his black-on-black. A colour
  written as a literal is the bug that made the Brave card a black box
  on light themes, and nothing here reintroduces it.
- **An empty "Not shown" list on the Toolbar page takes its card with
  it** rather than leaving an empty frame behind, now that the heading
  lives inside the card instead of floating above it.

## 2026-07-28 — Settings stops flashing

- **Settings no longer appears, vanishes and appears again.** Opening it
  a second time showed you the page for a moment, then your wallpaper
  through the gap where it had been, then the page once more. The pane
  was loading the whole document again on every open — and a load
  throws away what is on screen the instant it starts, so the page you
  had just been shown was taken down and rebuilt in front of you. The
  first open of a session was the only clean one, because that one had
  nothing to take down. It now keeps the page it already has and only
  loads again when something it shows has actually changed: a download
  that finished, a bookmark you added, a page you visited, a setting
  saved from somewhere else. Same for History, Downloads, Bookmarks and
  the password manager.
- **And the browser's own pages load once instead of twice.** Settings,
  the start page and the other four were asked for, refused, and asked
  for again — a whole extra trip through the engine, spent only so the
  page could be handed the right bridge on the way in. It is told which
  page it is opening before it opens it, so the first attempt is the
  one that arrives. Websites are unaffected: they are still refused the
  first time they try to reach across that line, and still never get
  the bridge.

## 2026-07-28 — a login that changes address is still your login

- **The other account's password could fill step two.** Sign-ins that
  ask for the e-mail on one screen and the password on the next often
  change host in between — signin.example.com hands you to
  account.example.com — and the browser was throwing away the account
  you had chosen at exactly that moment. Step two, which has no
  e-mail box on it and so nothing on screen to say whose box it is,
  was then read as a page asking for a password out of nowhere and
  filled with the newest password saved for the site. If you had
  cleared the box and typed a second account, that is somebody else's
  password, sent under the name you typed, into a session the site had
  just opened for it. It went out on the wire on one click.
- **The account you chose now reaches as far as the password does, and
  not one host further.** It carries to a subdomain, to a sibling that
  shares the same saved login, and from http to the site's https — the
  same steps the vault would have carried the password across anyway —
  and step two fills the account you chose, or nothing where you have
  nothing saved for it. An empty box is a nuisance; a stranger's
  password is not.
- **And nowhere else.** What the browser remembers is a name, and a
  name is only ever whatever some page wrote in a box. Off the site,
  it is not consulted at all: a page in the middle of a redirect chain
  cannot substitute one of your accounts for another and have the
  honest site's password step hand over the one it picked. Such a page
  is a fresh page, and fills from what is saved for it, exactly as
  before.
- **A password saved after a hop within the site is filed under the
  account you chose** instead of under a blank name, which is a row
  that could never have filled anything. After a hop off the site it
  is filed under no name at all, which is the honest answer.
- **Forty-three new checks** drive real sign-ins across sibling
  subdomains and through an open redirector, with real typing and real
  clicks, and watch both what reaches the page and what reaches the
  wire.

## 2026-07-28 — the toolbar tells everyone

- **A button on the toolbar can be switched off again.** Clicking a row
  in the Toolbar list moved the button up the bar instead of taking it
  off — and so did clicking dead centre of the switch itself, which is
  the one place aiming at it should have worked. The row is a `<label>`,
  and a `<label>` that is not told which control it belongs to takes the
  first one inside it. The up and down arrows sat ahead of the switch,
  and a `<button>` counts: the row belonged to the up arrow, so nothing
  you could hit with a mouse ever reached the switch. Every button
  already on the bar was stuck there unless you found it with the Tab
  key. The row names its switch now, and the arrows have moved to the
  far left of the row, the whole width of it away from the switch —
  reordering is a thing you aim at, not a thing you land on.
- **A row that cannot be switched off looks like one.** Back, forward,
  reload and the address bar had the same lit switch as everything else
  and simply ignored you. Their switch is dimmed, and clicking the row
  says what it will do instead: you can move it along the bar, but not
  take it away.
- **Settings no longer undoes a button you added from the right-click
  menu.** The Toolbar list read the row once, when the page opened, and
  wrote that whole list back every time you flipped a switch on it. So
  a button ticked on from the menu with Settings open was drawn
  unticked on the page — the switch said the opposite of the truth, and
  flipping anything else took the new button straight back off the bar
  and out of the config. The page is told when the row moves now, the
  same way the downloads and bookmarks pages are told, and a switch
  sends the one button it is about rather than its own copy of the
  whole order.
- **Switching Vault Password off takes the key button with it.** The
  button stayed on the bar with nothing behind it — it did nothing when
  clicked, and it had vanished from both the right-click menu and the
  Settings list, which are the only two places you could have taken it
  off from. There was no way to be rid of it short of a restart. It
  leaves the moment the vault does, and comes back the moment the vault
  does.
- **The star's tooltip changes language when you do.** Every other
  button was re-labelled on the spot; the star was left until the next
  time you went somewhere, because its tooltip says "Bookmark this
  page" or "Remove bookmark" and only the star itself knows which.
- **Setup tells you about a bad start-up address before it moves on.**
  Typing an address the browser cannot make sense of and pressing Next,
  rather than Save, walked you to the next step and put the complaint
  on the page you had just left, where nobody would ever see it. Next
  now waits for the browser to rule: a refused address keeps you on the
  step, under the box it is about. Pressing Next again goes — you are
  told once, not held there.

## 2026-07-28 — a light theme all the way down

- **A light theme no longer leaves the websites dark.** Auto-darkening
  is switched in two places — on the cookie jar, and on the page — and
  the page is the one that wins. Picking a light theme was switching it
  off on the jar and nowhere else, so every tab you had, every tab you
  opened and every tab after a restart came up with a darkened website
  inside a white browser. One question is asked in both places now.
- **And switching theme fixes the tabs you already have.** The page-side
  switch used to sit where it was until you navigated, so a browser you
  had just made light stayed dark until you went somewhere. Every tab
  and every pane is re-asked the moment the theme lands.
- **The quiet colours are a ladder again.** Making every one of them
  readable meant raising each until it cleared 4.5:1 — and a floor is
  where a colour stops, so five of them stopped on it together.
  Solarized Dark had its whole hierarchy inside four RGB units and a
  greyed-out menu entry 1.004:1 away from a live one; twenty themes had
  the hint under a field and the caption beside it as literally the
  same colour. Each rung now also has to stand a step clear of the one
  below it. Nothing got quieter to make room — the step only ever
  pushes a colour further from the background — and Catppuccin Mocha,
  which is the browser as it was drawn, comes out untouched.
- **The theme picker stopped arguing with itself.** Picking a theme
  wrote past the snapshot Settings redraws itself from, so the next
  redraw put the old theme's tick and the old theme's name back while
  the browser sat there in the new one. It goes through the same door
  every other setting goes through now.
- **A corrupted theme name no longer stops the browser starting.** The
  theme is read out of the config before there is any window to show an
  error in; a hand-edited file with a list where the name goes took the
  whole launch down. Anything that is not a name it knows falls back to
  the default.
- **Settings says so when a part of it will not draw.** The stages of
  the draw were each guarded, but the calls that start them were not —
  so one unreachable bridge call threw before the first guard and left
  no theme picker, no plugin list, no password summary and no red line
  to say why. The guard goes round the call now, and the page always
  ends up drawn.

## 2026-07-28 — the tab that was not there in the morning

- **A tab you opened and went straight to a page in is kept.** Press
  Ctrl+T, type an address, read the page, leave it there overnight —
  and in the morning the tab was gone, with no message and nothing to
  get it back with. A fresh tab is marked "opened, never taken
  anywhere" so that an empty tab is not written into the session and
  handed back at every launch, and the browser worked out where such a
  tab had come to rest from the first page that arrived in it. Type
  fast enough and the first page that arrives is the one *you* asked
  for: the browser filed your destination as "where an empty tab
  rests", and never counted the tab as yours again. It now reads that
  off the address the new tab was opened on and the navigations that
  follow from it, so a page you went to is a page you went to, whether
  or not the new-tab page had finished loading first.
- **What made it look random rather than like a rule.** Going
  somewhere a second time in that tab put it right, so the tab only
  vanished when you opened it, went to one page, and stayed — which is
  exactly what a tab left open for tomorrow looks like.
- **A new-tab page of your own that redirects, refreshes itself, or
  hops through a consent page is still an empty tab.** Only the
  plainest of those was recognised before; the other two quietly turned
  every untouched new tab into a real saved tab, which is the "it keeps
  opening itself" complaint one loading trick further along. The start
  page had the same thing happen to it and got away with it only
  because it is kept out of the session by name as well.
- **That name is now matched the way the rest of the browser matches
  it**, so the start page is still recognised when the cache-busting
  tail on its address is not the one this run generated.
- **And an address typed into the bar is written down as the tab's
  fallback** the way every other kind of load already wrote one down.

## 2026-07-28 — Esc asks first

- **Esc belongs to the page it is pressed on.** The five pages that
  live in a pane — settings, downloads, history, bookmarks, the
  password manager — never got to see it. One window-wide shortcut took
  every Esc and closed the pane, and nothing the page did could hold it
  back. So Esc over a half-typed password entry threw the whole pane
  away, the page was reloaded from scratch on the way back in, and the
  entry was gone; Esc in the settings search box, which was only ever
  meant to empty the box, closed settings instead. The pane now asks
  its page what Esc means there before it does anything: an open
  editor, a bookmark being renamed and a search box with something in
  it each take it and the pane stays. When the page has nothing to say
  — and for downloads and history it never does — Esc closes the pane
  exactly as it always did.
- **A password entry Esc closed is not lost.** Press Esc over one and
  the editor puts itself away, but what you had typed is kept: open the
  entry again and it is all still there. Cancel and Save are unchanged
  — those are you saying what should happen to it.
- **A page that stops answering cannot trap you.** The question the
  pane asks is on a quarter-second fuse. A wedged renderer, a page that
  threw on the way up, a document swapped out underneath — none of them
  can leave a pane on screen with no way out, and a second Esc while
  the first is still in the air closes it at once.
- **"Re-run setup" runs setup.** It used to hand the browser the word
  "nothing" where it meant "the start page", and the browser took that
  as "the page he set for new tabs" — so anyone who had set one got a
  new tab on that page, no wizard, and a setup flag left standing that
  would ambush them the next time a start page loaded. It asks for the
  start page by name now, and the wizard is up when it gets there.

## 2026-07-28 — setup catches up

- **Setup asks about the colours.** A new second step offers twelve of
  the 114 themes — four dark, four light, four with a character of
  their own — and picking one paints the browser while you are still
  standing in setup, because the page you are on is one of the
  browser's own. Twelve and not 114: that is a catalogue to browse, not
  a question to answer, and the line underneath points at Settings →
  Theme, which has all of them and a search box. Setup is eight steps
  now instead of seven.
- **Setup asks what the browser opens on.** "When the browser starts"
  has moved to the top of the start-page step: the start page, or an
  address you type. It is the same pair of cards Settings has, with the
  same address box and the same refusal — an address the browser cannot
  make sense of is turned down out loud and stays in the box, rather
  than quietly leaving you on the start page and wondering why.
- **Both are on the summary**, and both survive leaving setup with Esc
  and coming back — they are written the moment you pick them, the same
  as every other answer in there.
- **The wallpapers on that step go three to a row** instead of two, so
  the question above them does not push the rest off the bottom.

## 2026-07-28 — the buttons at the top are yours

- **Pick the buttons on the toolbar.** The row up there was whatever
  someone else had decided it should be. Now it is a list you own:
  right-click the toolbar for a menu of every button with a tick beside
  the ones that are there, or open Settings → Toolbar for the same list
  with switches, and arrows to push a button left or right along the
  row. Nothing moves on its own — the set you start with is exactly the
  set that was there before.
- **Eight buttons that were only ever shortcuts can come up.** New tab,
  find on page, history, downloads, bookmarks, the password manager,
  settings and full screen were all keys and nothing else. They are all
  switched off to begin with, and any of them can join the row.
- **Four of them stay.** Back, forward, reload and the address bar
  cannot be taken away. A browser with no way back is a broken browser,
  and there is no undoing it from a window you have just broken.
- **The star and the tab groups button can go too.** They do not live
  on the row — the star rides inside the address bar and the tab groups
  button sits in the corner of the tab strip — so they can be taken
  away but not moved, and Settings says so. With the star gone the
  address bar takes its margin back rather than leaving a gap.
- **A button you take away is gone, not hiding.** It comes off the row
  entirely instead of sitting there invisible. Its keyboard shortcut
  never knew about it and keeps working: Ctrl+P still prints with no
  print button, and the menu it used to drop from drops from the
  address bar instead, where you can see it.
- **A menu entry you cannot pick now looks like one.** The window's own
  stylesheet was setting the menu's text colour, which quietly overrode
  the greying-out, so an entry that did nothing looked exactly like one
  that did. Everywhere, not just here.

## 2026-07-28 — the themes, made readable

- **Every one of the 114 themes can now be read.** A palette used to be
  worked out by mixing: a hint, a placeholder or a disabled label sat a
  fixed fraction of the way from the background to the text. That keeps
  the proportion and throws the contrast away — on a pale background
  the same fraction is a far fainter colour, and on half the shelf the
  quiet text, the warning lines and the accent had faded into the page.
  The fraction is now only where the search starts: every colour is
  pushed out from there until it clears 4.5:1 against the page and
  against every island it can land on. The push is a straight walk
  towards white or black, so a pink stays a pink and only stops being
  pale.
- **Catppuccin Mocha is untouched.** It is written down in full and
  marked as such; the window's own stylesheet under it is identical to
  the byte.
- **A card under the mouse is no longer a black box.** One colour in
  Settings was written as a literal the theme engine had never heard
  of, so it survived into every theme: hover a search-engine card on a
  light theme and it turned near-black, with the theme's dark text
  still on it — 1.4:1 on Nord Snow Storm. That is the black Brave card
  in the photograph; it was Brave because that is where the mouse was.
  The same literal was on the search box in the rail. Both are palette
  colours now.
- **A texture is a background again.** Scanlines, hatch, drafting grid
  and brushed metal were painted on a sheet of glass over the whole
  page, so they ran through the start page's search box, through the
  quick links and through every button. They are painted on the page
  behind everything instead — Terminal Green, Amber CRT, Blueprint,
  Synthwave, Game Boy, Steampunk and Sepia Paper.
- **The start page over a photograph.** The wash behind the clock was
  black whatever the theme, so a light theme's dark text sat on a dark
  wash on a bright picture. The wash is the theme's own background now,
  and the clock and the date carry a halo of it, which reads on any
  photograph either way.
- **Colours a theme could never reach.** The password strength bar, the
  flags on a weak or reused password, the warning on a login whose site
  is not a host name, the vault line in Settings and the mark beside
  the virtual browser you are in were all written into the page's
  JavaScript as fixed Catppuccin colours. They read the palette now.
- **A selection and a keyboard focus** are painted out of the palette
  on every one of the browser's own pages, instead of whatever the
  engine felt like — which on a couple of themes could not be seen at
  all. The rail in Settings had a focus state with nothing to see; it
  has a ring.
- **A tab group's pill** takes a label that can be read on it. The
  colour of a group is yours and not the theme's, so the theme's
  background is used while it can be read on the pill and black or
  white when it cannot.
- All of it is measured rather than eyeballed: `test_contrast.py` puts
  6612 ratios on the table — every pair the pages and the window's own
  stylesheet produce, in every theme — and fails on any of them. Run
  against the palettes as they were it fails five ways over 88 of the
  114 themes; 70.3% of the pairs cleared WCAG outright before, 87.9%
  do now, and none is quieter than Mocha.

## 2026-07-28 — The e-mail box lets go

- **When you clear the sign-in box to type your other account, it
  stays clear.** The browser filled the saved address, and every time
  you emptied the box to put the second account in, the address came
  straight back — often landing in front of what you had just started
  typing, so the box ended up holding both addresses stuck together.
  Microsoft's sign-in rebuilds that box constantly, and a rebuilt box
  is an empty one, which the browser was reading as "nobody is signing
  in here yet, fill the saved account".
- The rule now is the one the password box already followed: **the
  browser fills the account once, and the moment you change or clear
  it, that is your choice for the rest of the page.** It does not
  matter how often the site redraws, whether the page finishes loading
  a second time, or whether the box is thrown away and built again.
- The first fill is untouched, and so is the two-step flow — the
  address you give on the first screen is still the one the password
  is filled for on the second. Going to a genuinely new page fills the
  saved address again, as it always did.

## 2026-07-28 — The browser's own pages stop being pages

- **Settings, Downloads, History, Bookmarks and the password manager
  now open over what you were looking at, and Esc puts it back.** They
  were pages you navigated to; four of them cost you a tab, an entry in
  your own history, and the address bar for as long as they were up.
  None of them does any of that now.
- **Esc is the way out of all five**, and it leaves you exactly where
  you were — the same tab, on the same page, scrolled where you left
  it. Previously, closing one of these could hand you a fresh start
  page instead of the page you came from, which is the thing that made
  them feel like somewhere you had gone rather than something you had
  opened.
- **The keys you know now work both ways.** Ctrl+, Ctrl+H, Ctrl+J,
  Ctrl+Shift+O and Ctrl+Shift+P open their page, and pressing the same
  keys again closes it.
- **They are not in the tab strip and not in the address bar.** There
  is nothing to navigate to, no `file://` address to see or copy, and
  no second copy to end up with — opening one twice brings up the one
  you already had.
- **They are never reopened as tabs when the browser starts.** If an
  older version left one saved in your session, it is quietly dropped
  rather than restored, so you no longer come back to a stale Downloads
  or Bookmarks tab that no longer works.
- Each is loaded fresh every time it comes up, so it shows what is true
  now — a download that finished while it was closed, a bookmark added
  from the bar, a password saved from another window.
- **The password manager was the last one still a page**, and it is a
  pane now too. If you have not installed Vault Password, Ctrl+Shift+P
  does nothing, exactly as before.
- Ctrl+Shift+G still copies a fresh password to the clipboard without
  opening anything.
- A link inside one of these pages that genuinely leads elsewhere —
  "View history", a bookmark, Greasy Fork — still opens as a normal
  tab, and closes the pane on its way out.

## 2026-07-28 — The page you start on, and the way back to it

- **"When the browser starts" is a setting of its own now.** It sits in
  **Settings → Browsing**, just above "What a new tab shows": the start
  page, or an address you type. Put YouTube there and the browser opens
  on YouTube — while a new tab still shows the start page. The two
  settings are separate and neither one writes the other.
- Tabs from last time still win. With "reopen tabs from last time" on
  and something to come back to, those come back, and no start-up page
  is pushed on top of them.
- **Alt+Home goes to the start page, and there is a ⌂ button next to
  reload.** Once you set a page of your own for new tabs there was no
  way back to the start page at all: it is a file on this computer with
  a name nobody could type, and the address bar keeps itself empty
  while it is up. Now there are two.
- **An empty tab is no longer remembered as a tab.** A new tab you
  opened and never went anywhere in is not written into the session, so
  it does not come back at the next start. With a page of your own set
  for new tabs, every empty tab used to become a real saved tab and the
  strip grew at every launch. Go somewhere in it and it is remembered
  again, exactly as before — including on the pages that move without
  loading anything, the way a webmail changes the address when you open
  a message.
- **The address boxes save themselves.** The page promises every change
  is saved the moment you make it, and these were the only controls
  that broke that promise — typing an address and closing Settings
  wrote nothing at all. They now save when you leave the box, as well
  as on Save and on Enter. Clearing one puts the choice back on "The
  start page" instead of leaving "A page you choose" ticked over an
  empty box.
- **An address the browser will not take says what is still in force.**
  The red line names the address that is still being used instead of
  only saying no.
- **"Right after this tab" stays inside the virtual browser you are
  in.** A tab opened for another one could be slid into the block of
  the one on screen; it goes to the end of its own now. The card also
  says out loud that from the last tab in the strip, "right after this
  tab" and "at the end" are the same place — which is why the setting
  looked dead when you tried it there.
- Every setting on the page is written through one place now. A setting
  you changed could be repainted a moment later from the page's own
  stale copy of how things were when it opened, which is what made
  "where a new tab opens" look like it did nothing.
- **Settings can no longer come up blank.** If any one part of the page
  failed to draw, the whole page used to stop there and say nothing —
  an empty pane over the tab, with no rail and nothing in it. Each part
  now stands on its own, whatever did not draw says which part it was
  in a line at the top, and the page always ends up with a rail and one
  section showing. A search that matches nothing still hides the
  content, and the "All settings" button in the rail still brings it
  back.
- `BROWSER_TIMING=1` prints one line per phase while Settings opens, for
  chasing the slow open on a machine it actually happens on. Silent
  unless you ask for it.

## 2026-07-28 — Two accounts on one sign-in

- **Picking the other account works.** Microsoft, Google and anyone
  else who shows you a row of account tiles swap the password screen in
  without ever reloading the page. The browser used to decide whose
  login this was the first time you touched the box and then stop
  listening, so choosing the second account off a tile changed nothing:
  it went on holding the first one, and at the password step it either
  filled the wrong password or, when the account you picked was one it
  had never saved, filled nothing at all and said nothing about why.
  It now follows the box.
- **The browser no longer reaches for a password it was not asked
  for.** If the page is showing an account, only that account's
  password is offered there. Where it used to fall back to "the most
  recent login on this site" beside a name it did not recognise, it now
  offers nothing — a wrong password submitted for you is worse than an
  empty box.
- **And a password already filled is taken back when the account
  changes under it.** This is the everyday version of the same bug, and
  it is the one you actually hit: the browser fills in the account it
  knows, your click into the e-mail box to change it is what puts that
  account's password in the box below, and then you type your second
  address over the first. The password stayed. It went out with the
  form, under the wrong name. Now it is removed as soon as the account
  stops matching — but only ever the browser's own value, never a
  character you typed or pasted yourself.
  <br>Not a promise that this can never happen: a page that rebuilds
  its password box from scratch, or adds a second one, or submits
  itself within the moment before the browser has looked again, can
  still carry off a value already filled. It is the same password, for
  the same account, on the same site it was saved for — but under
  another name on the form, and worth knowing about.
- **An account you typed stays yours.** Once you have typed an address
  into a sign-in, that login is hand-chosen for good: going Back,
  reloading, or the page writing a different address into the box
  cannot turn it back into something the browser feels free to guess
  around. And a sign-in that is halfway through gets that account's
  password or none — never the site's most recent login instead.
- **The Site box in the password manager takes a URL.** Paste
  `https://login.live.com/` into it and it is understood as
  `login.live.com`, with the port and the path and the `www.` taken
  off, and `http://` remembered as `http://`. It is the same reading
  the CSV import and 1Password already got.
- **Logins already saved with a URL in the Site box are repaired.** The
  browser tidies them as it loads them, so they start filling again on
  their own. A Site it cannot make a host name out of is left exactly
  as it was — nothing is thrown away on your behalf.
- **A login that can never fill now says so.** Open it in the password
  manager and a line under the Site says the Site is not a host name,
  so this login never fills anywhere. Nothing else in the browser would
  ever have mentioned it; the row simply did nothing, for ever.

## 2026-07-27 — 114 themes

- The browser is no longer one colour scheme. **Settings → Theme** has
  114 of them, on three shelves: Dark, Light and With character. Type
  in the box above the list to find one, or type its name into the
  search on the left — the whole catalogue is searchable either way.
- Each theme is its own card, painted in its own colours: the window,
  an island on it, a line of text and the accent. The list is the
  preview.
- Clicking one applies it **immediately** — the window, the tabs, the
  address bar, the menus, and every page the browser brings with it
  (start, settings, history, downloads, bookmarks, passwords). Nothing
  is reloaded and nothing has to be restarted.
- Most are well-known palettes, credited on the card: Catppuccin,
  Gruvbox, Nord, Dracula, Solarized, Tokyo Night, Everforest, Rosé
  Pine, Kanagawa, Monokai, One, Ayu, Material, Oxocarbon, Nightfox,
  GitHub, VS Code and more. The rest are drawn here — Steam, Autumn,
  Nautical, Deep Sea, Volcano, Cyberpunk and so on.
- Nine of them are more than a palette. **Steampunk** brings brass,
  oxblood and a slab serif with a rule under every heading;
  **Terminal Green** and **Amber CRT** bring scanlines and a phosphor
  glow; **Blueprint** brings drafting paper; **Newspaper** and **Sepia
  Paper** bring print; **Synthwave '84**, **Game Boy** and
  **Commodore 64** bring what their names say.
- **Nothing changes unless you change it.** The theme you already have
  is called Catppuccin Mocha and it is still the default, down to the
  last hex digit.
- **Light themes and websites.** Which version of itself a website
  serves — its light one or its dark one — is decided when the browser
  starts and cannot be changed while it runs. Pick a light theme and
  the browser is light straight away; a line under the list says
  websites are still being asked for their dark version and offers to
  restart. While a light theme is on, "auto-darken light websites" is
  held off, so a white browser is never full of black pages. Your
  setting is left exactly where you put it.
- Websites themselves are never repainted by a theme, and neither is
  anyone else's HTML file you happen to open. A theme is the browser,
  not the web.

## 2026-07-27 — Settings, cleaned up

- **The bar that crept along the top of Settings is gone.** It measured
  how far down the list of sections you were, which is not a thing
  anyone needed measured, and it re-drew itself every time you clicked.
- **Searching Settings now points at the setting, not just the
  section.** Type a word and the rail says how many settings in each
  section answer to it; inside the section the ones that match keep
  their colour and get a mark down the left, and the rest step back.
  The page scrolls to the first match instead of leaving you to find it.
- **The search box keeps the keyboard.** ↑ and ↓ walk the sections that
  matched, Enter drops you onto the first setting one of them found —
  ready to switch or type into — and Esc empties the box. Esc anywhere
  else still closes Settings, as before.
- **Switches can be reached with Tab now**, and flipped with Space.
- Settings moves a little: a section slides up a few pixels as it
  arrives, the rail lights up under the pointer, the switches slide
  rather than jump. All of it is off if your system asks for less
  motion.
- Settings that belong together share their hairlines instead of each
  drawing its own box, the title of the page sits above a rule of its
  own, and the spacing was tightened throughout.

## 2026-07-27 — Vault Password is yours to install

- The password manager is now called **Vault Password**, and it is
  optional. Setup asks whether you want it, and Settings → Plugins,
  under Built-in features, switches it on or off whenever you like.
- Off means off. The part that watches for logins is never put into a
  page at all, so no form is looked at, nothing is offered to save, and
  nothing is written to the vault. The Passwords section leaves Settings
  and Ctrl+Shift+P does nothing.
- Switching it off **deletes nothing**. Your saved logins stay on this
  computer exactly as they are, and they are all there again the moment
  you switch it back on. Settings says so, right under the switch.
- Switching it on or off takes effect on the next page you open — no
  restart.
- Nothing changes for anyone already using it: an install that has been
  through setup keeps the password manager switched on, as does one with
  saved logins on disk. Only a brand-new install starts without it and
  gets asked.

## 2026-07-27

- Saved passwords fill when you click the box you want filled. Clicking
  into the e-mail or password field was the one gesture that did
  nothing, so the commonest way to start a login was the way that never
  worked — you had to click the heading, or press Tab, to get your
  password. It still takes a real click or keystroke; it just counts
  the one you were already making.
- A click beside the form, or Tab with nothing focused, counts too. The
  filler was only listening inside the `<form>`, so those went unheard.
- Changing account no longer submits the previous account's password.
  Pressing Ctrl, Shift or an arrow key used to be read as "done here"
  and dropped the last-used account's password into the box, where
  nothing could replace it — so you signed in with one account's name
  and another's password. Only Enter and Tab mean "done" now, and if
  you pick a different account the password is corrected.
- Typing your own password over a filled one clears ours first, instead
  of leaving you typing onto the end of a value you cannot see.
- Exporting passwords to CSV no longer crashes on Windows.

## 2026-07-26 — the password manager

- A password manager of its own (Ctrl+Shift+P, or from Settings): every
  login, plus secure notes, payment cards and identities, with search
  across everything, tags, favourites and a detail panel
- Nothing on that page holds a secret. Passwords, card numbers, CVVs,
  note bodies and two-factor seeds stay in the browser and are handed
  over one field at a time, by name, after you ask for them
- A password generator (also Ctrl+Shift+G, straight to the clipboard),
  and the save prompt now says where to find it
- Two-factor codes: paste an `otpauth://` link or the base32 secret and
  the code is on the page with its countdown ring. "Copy code" copies
  the six digits — never the seed they are made from
- A health check that runs entirely on this computer, with no breach
  API and no network call of any kind: reused, weak and never-changed
  passwords, and a reason for each
- Import and export as Chrome/Firefox CSV. The export says out loud
  what it is about to write before it writes it, the file is
  owner-only from the moment it exists, and no cell in it can be
  turned into a spreadsheet formula. Only the vault on this computer
  can be exported — 1Password does not hand the passwords over, so
  that file would look like a backup without being one
- Secrets can live in 1Password instead, over the `op` command-line
  tool and a service-account token. The token is kept in its own
  owner-only file — never in config.json, never in an argument list,
  never shown again — and so are your passwords on their way to `op`
- Nothing is copied or moved when you switch stores: each keeps what
  it already had. If 1Password cannot be reached, the browser opens on
  the vault on this computer and says why, in plain words
- 1Password cannot show the browser your passwords, only that they
  exist — so the health check says it could not run rather than
  reporting a clean bill of health it has no basis for
- The window no longer waits for 1Password: startup, the store list
  and every save, delete and import happen off to one side, so a slow
  or hanging `op` costs a moment's "reaching for 1Password…" instead of
  twenty seconds of frozen browser
- Importing a full-sized Chrome export takes a moment rather than a
  minute
- Saved logins from earlier versions come across untouched, and an
  older build can still read what this one writes
- Settings keeps one line about the vault — where it is kept, what is
  in it, whether the health check could run — and a button to the
  manager. The list, the add-login form and the never-saved list that
  used to live there are on the manager page now

## 2026-07-26

- Logins that ask in two steps (Amazon, Google, Microsoft: e-mail
  first, password on the next screen) fill in properly now — the
  browser works out which of the two the page is asking for, and
  remembers the account from the first screen. Type a different
  e-mail than the one it filled and it uses that account's password
- Settings fills the whole window now — address bar and tabs included —
  instead of sitting below them; Esc or the ✕ closes it
- Settings is sorted into General / Privacy / Advanced / Browser, and the
  page says which section you are in
- The page-zoom and minimum-text-size sliders are actually visible on the
  black theme: a filled track and a square white handle
- Settings is no longer auto-darkened on top of its own dark theme
- Find in page (Ctrl+F): match count, Enter / Shift+Enter to step,
  match case, Esc to close; follows the tab you switch to
- Print and Save as PDF (Ctrl+P), also from the toolbar printer button;
  the PDF lands in your download folder and on the downloads page
- Reopen closed tab (Ctrl+Shift+T), back in its group and its
  virtual browser
- Tab search (Ctrl+Shift+A): every open tab across every virtual
  browser, filtered as you type
- Bookmarks: a star in the address bar (Ctrl+D), a bookmarks bar with
  favicons under the toolbar (Ctrl+Shift+B), folders, and a bookmark
  manager page (Ctrl+Shift+O) to search, rename, reorder and delete
- Microphone works: clicking Allow now actually reaches the engine,
  so a site that asks for the mic really records (camera too)
- Setup wizard rebuilt as a full-screen, seven-page walk-through:
  language, search engine, wallpaper and search-bar placement (with a
  live preview of the start page), how websites look, privacy, quick
  links, and a summary of everything picked
- Setup can be left with Esc without pretending to be finished, picks
  up where it left off, and shows your current choices when re-run
- New privacy switch: offer to save passwords
- Screen sharing asks at last: a black picker listing your screens and
  windows, where before every screen-share attempt failed instantly
- Permissions are remembered per site, not per host name: allowing the
  mic on one site no longer quietly allows the same name on another port
- A local HTML file gets its own answer instead of sharing one with
  every other file on the disk, and it is never remembered for good
- Settings now looks like the setup wizard: the same left rail with a
  marker on where you are, the same big title with a line under it, the
  same option cards and square switches, the same footer — and a filter
  box, because the list of settings keeps growing
- Offer to save passwords is in Settings too, not only in setup
- Search suggestions can be switched off: nothing you type in the
  address bar is sent to the search engine
- New switches: block videos from playing on their own, smooth
  scrolling, open PDFs in the browser instead of downloading them,
  check spelling as you type (with its own language)
- Pick your download folder, or keep ~/Downloads
- Clear history and/or cookies when the browser closes
- Choose where a new tab opens (at the end, or right after this tab)
  and what it shows (the start page, or an address you pick)
- "Right after this tab" no longer scrambles the tab strip when the
  browser reopens the tabs from last time
- The settings filter searches everything on the page, not just the
  words that were there before it loaded: search engines, spell-check
  languages, saved logins, proxy profiles, the option cards
- Filtering to nothing leaves no half-open section behind, and there is
  an "All settings" button to get back
- Clear history / cookies when the browser closes survives a crash: a
  wipe the last run did not get to do happens at the next start
- Changing the browser's language moves the spell checker with it
- The new-tab address says what it turned into, and says so when it is
  not an address at all instead of quietly falling back

## 2026-07-23

- Pitch-black theme with square corners; no blue accents in the chrome
- Google pages repainted true black
- Faster loading on natively dark sites (GitHub, YouTube, …)
- First-run setup wizard: drag the search bar anywhere, pick a wallpaper
- Update button in settings + update-available popup at startup
- Esc closes the history page back into the settings panel
- Light-colored settings switches; various start-page fixes

## 2026-07-22

- First release: tabs, smart address bar, downloads bar, history,
  start page with quick links and backgrounds, single instance,
  fullscreen video, default-browser support
