# Changelog

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
