# Themes that keep every website readable

2026-11-07. Fifty-four real sites, every one of the 116 themes, measured in the page
and looked at. Started from "Outlook is unreadable in some theme".

## What was wrong, in one paragraph

Not Outlook, and not a theme: the site theming pass fought itself. Every site element
eased between colours over .35 s, and the pass reads an element's colours back right
after it writes them, so what it recorded as "my own work" was the colour the element
was fading *from*. Every later look took the finished colour for the site's doing,
restored the element, judged a mid-fade grey, wrote again, and the observer saw the
write. On a page that keeps mutating (the Outlook landing page, office.com, the
Microsoft sign-in page) that loop never ended: the main thread stayed busy, text was
judged against colours that were never on screen, and a theme switched while the page
was open left the *last* theme's observer alive with the last theme's palette, repainting
the new theme's cards in the old theme's dark. The sign-in card in Latte after Mocha was
exactly that: a Mocha-dark card with Latte-dark text on it.

## Root causes fixed (theme_web.py)

| # | Cause | Fix |
|---|---|---|
| 1 | A live re-theme ran the script again in a page the last run was still watching; both runs saw each other's writes as "the site moved" and repainted each other for as long as the tab was open | One run at a time: a run switches the previous observer off and every leftover slice/timer of the old run checks it is still current |
| 2 | `.35s` colour transition on every site element: the read-back after a write recorded the *start* colour, so every later look thought the site had restyled the element | No transition on sites (the chrome switches in one frame too); the record of "what I wrote" is composed from the written values, and an element mid-way through the *site's own* fade is waited out, not judged |
| 3 | The staleness check compared an element's `color` even when it shows no text; the inherited colour changes when an ancestor is painted, so every card on a page "moved" at every look | Only what an element shows is compared: its fill, its text colour if it has text, its border colour if it has a border |
| 4 | On a re-theme every painted element was restored and then read back one by one: a full style recalculation per element, a minute of main thread on a 16000-element page | Restores are batched per chunk and read after one recalculation (1.7 s for 16000 elements in the test) |
| 5 | Full re-looks were capped at four per page; a stylesheet chunk landing later (office.com's cards, hydrated section by section) was never seen, and the text painted for a white card stayed theme-light on it | Looks are rate-limited (one per 1.5 s), not counted out; a look is also taken at 6 s, 15 s, 30 s, 60 s and on scroll (a marketing page hydrates for half a minute) |
| 6 | A headline over a *sibling* picture (Outlook's hero `<img>` positioned under the words) looked like text on the page background and was repainted in the theme's light text — invisible on the light photo | On screen the stack under the text is asked (`elementsFromPoint`): a picture beneath means "leave it", an opaque layer beneath is the real backdrop. Asked once per decision, not at every look |
| 7 | Links and headings were always given the accent, even when they already read; a wrong guess about the background then cost a headline that was fine | Text that already reads is kept, links and headings included; the accent comes only when the site's colour no longer reads on the fill the pass made |
| 8 | A placeholder was coloured `overlay` by a global rule (under 4.5:1 on a card on 115 of 116 palettes), and a field left transparent on a repainted card kept the site's placeholder (Microsoft's: black at 60 % on near-black) | The placeholder is measured against what is really behind the field like any text, and only when it fails the field gets one of four classes: `dim` (the quietest token that clears 4.5:1 on every surface of all 116 palettes), the text colour, white or black |
| 9 | An element measured while empty (Microsoft's "Sign in" heading is filled by a script) was recorded as "nothing moved" when its words arrived, so it stayed the site's dark on the dark card | The record says whether the element had words; one that gets them later is looked at again |
| 10 | A site script that rewrites an element's style attribute was answered on every frame | Capped at five restores per element; the pass gives an element up after six restore/repaint rounds (a theme switch does not count as a round) |
| 11 | **The one only the signed-in views showed.** Outlook's panels carry `transition: all .2s`. On a theme switch the pass restores a panel and waits for its fade, but the dates *inside* were judged at once, against the dark the panel was fading from, and painted white; the panel itself then needed no repaint, so nothing ever came back to them. Mini-calendar dates and the People headers invisible in 114 of 116 themes, worse with every switch; Gmail's lower rows the same | An element waiting out its fade is marked pending — after a restore, after the pass's own write to it, and while its fill is visibly between colours in a fade the *site* started — and anything that sits on it (ancestors or a layer underneath) is "unsure" and is judged after it settles. A re-theme also looks back over the page at 1.5 s and 4 s |
| 12 | When the pass gave an element up (six rounds of disagreeing with a script that restyles it every frame) it left it half-done: the pass's fill under the site's ink | Giving up restores the element to the site's colours entirely |
| 14 | **Found in the after-run's cells.** The Outlook landing page (a Microsoft marketing page) answers the dark theme's `prefers-color-scheme` late, after its scripts load: its sections turn from white to their dark-mode colours 15–30 s after load, with the footnotes' navy ink unchanged. The pass had judged that ink against white; the ground moved, and every re-look at it counted as one more "disagreement" with the site, so after six the footnotes were given up and left navy on the dark page (Aero: 43 % of the page's text) | Only the element's own colours moving (the site writing them back) counts as a disagreement; a change of what it sits on, or words arriving, is judged afresh without a cap. A full look is also taken at 30 s and 60 s, and when a class or style lands on `<html>` or `<body>` (the page switching its scheme). The landing page: 0 % in Aero with a 45 s window, 0.3 % elsewhere |
| 13 | **Found in the after-run's screenshots, not by the audit.** office.com's "Work smarter" headline is letters cut out of a gradient (`background-clip: text` over a transparent text fill, the gradient black on the site's white). To the pass a gradient was "a picture, leave it", so the headline stayed black on the hero the pass had just made dark; the audit skipped transparent fills, so every cell said 0 % | A gradient clipped to the letters is the ink, not a backdrop: the ground is what lies behind the element, every stop of the gradient is judged, and when the worst one fails the gradient goes and the letters get a fill in the text or accent colour (a pastel gradient that reads on dark is kept). The words inside such a headline (spans with an inherited transparent fill) get a fill of their own; a text fill the site set itself is rewritten too, since a write to `color` shows nowhere on it. The audit judges gradient letters the same way |

Counters for all of this live in `window.__stStats` (ApplicationWorld): slices, measured,
painted, full looks, observer callbacks, flips, waits, reputs, time per phase, and the first
24 reasons an element was looked at again. `_sitediag.py URL THEME SELECTOR` prints them
with the ancestor chain of any element.

## Per-site exceptions

None added. Every fix above is a general rule; `NATIVE_DARK_SITES` is unchanged.

## The chrome (browser.py `STYLE`, settings.html, start.html)

Calmer, flatter, rounder, after the two reference screenshots (a timetable app's white
cards on soft grey with one thin accent bar; a home screen's big rounded widgets on black):

- address bar: 12 px radius, no hairline until it has focus
- tabs: 10 px radius, more room; the selected tab is no longer boxed in a hairline — it
  carries one thin accent bar down its left edge instead (painted in `GroupTabBar._extras`,
  pair added to `test_paintcontrast.py`); the sidebar's current row is a flat pill
- menus 12 px with 8 px items; every floating panel (find, toast, permission card, account
  chooser, share picker, favourites, start menu, tab switcher) 14 px; their hairlines at
  about half the alpha; buttons and fields in them 8–10 px
- settings and start page: cards, rows, option cards, fields, buttons and the switches
  rounded (12/10 px), the switch a pill; grouped rows share one rounded outline
- palettes: colours unchanged. The 116 palettes are credited and the contrast ladder is
  measured; the calm comes from geometry and fewer lines, not from new colours.

| before | after |
|---|---|
| ![before, Mocha](theme-audit/chrome/before-mocha.png) | ![after, Mocha](theme-audit/chrome/after-mocha.png) |
| ![before, Latte](theme-audit/chrome/before-latte.png) | ![after, Latte](theme-audit/chrome/after-latte.png) |
| ![before, settings](theme-audit/chrome/before-settings-mocha.png) | ![after, settings](theme-audit/chrome/after-settings-mocha.png) |

Flat mono still squares everything (its own sheet wins), and the corner-radius setting
still overrides all of it.

## How it was measured

`_sitematrix.py` boots the real browser offscreen, loads a site once and applies every
theme to it live (the Settings > Theme path), or loads it afresh per theme (the first-visit
path); `_siteaudit.js` then measures, in the page, every element that shows text: the
colour it is really drawn in (text-fill colour, alpha, opacity up the tree) against what
is really behind it (opaque ancestors blended, the stack under the text on screen, a
photo or gradient = "cannot be judged"), weighted by characters. A cell is the share of
judged text under 3:1 — unreadable, not merely weak. `f` marks a form field or
placeholder that fails, `i` marks text whose box in the screenshot is a flat patch of
one colour (invisible whatever the styles say), `busy` a page whose main thread did not
answer in 9 s twice. `theme-audit/drive.sh <out> before|after` runs it one site per
memory-capped process (`theme-audit/capped.sh`), two at a time.

## Before and after, by the numbers

Fresh loads, 13 anchor themes: **141 cells with unreadable text before, 58 after** (of
about 578 themed cells). Live re-theme, all 116 themes: **2042 site×theme pairs with a problem
before, 503 after**, over 54 sites. What is left is listed under "Still broken" below, and
most of it is the site's own ink or the audit over-counting hidden text.

The before-run is the code of commit dc74e63 on the server; the after-run is this branch,
run on the desktop (RTX 5080, same software renderer offscreen) with office.com, unsplash and
the Outlook landing page re-measured on the server after the last fix. Cells read: `ok` under
0.5 % of the judged text below 3:1, `N%` the share below 3:1, `-` the site was not themed
(dark by design, or not themed within the settle window), `·` no measurement, `busy` the page
did not answer the audit, `f` a failing form field or placeholder, `i` text whose box in the
screenshot is one flat colour.

### Before

#### Fresh load, anchor themes (cell: share of text under 3:1; f = a form field, i = text invisible in the screenshot, - = not themed)

| site | mocha | gruvbox | nord | dracula | terminal | steampunk | aero | latte | gruvbox-light | solarized-light | newspaper | papercolor | high-contrast |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| accounts.google.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| amazon.de | 10% | 7%f | 10%f | 10% | 10% | 14%f | 14% | ok | ok | ok | ok | ok | ok |
| amazon.de/s?k=ssd | 1% | 6%fi | 1%i | 14%i | 1%f | · | · | ok | ok | ok | ok | ok | ok |
| apple.com/de/ | 2% | 2% | 2% | ok | 2% | 2% | 2% | 2% | 2% | 2% | 2% | 2% | 2% |
| bahn.de/ | ok | ok | ok | ok | 9%f | ok | ok | ok | ok | ok | ok | ok | ok |
| bbc.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| booking.com | 16% | ok | 38% | ok | 7% | 22% | 10% | ok | ok | ok | ok | ok | ok |
| chatgpt.com | 2% | 2% | 2% | 2% | 2% | 2% | ok | ok | 2% | ok | 2% | ok | 2% |
| deepl.com/translator | 1% | ok | 4% | ok | 16% | 16% | · | ok | ok | ok | ok | ok | ok |
| developer.mozilla.org/en-US/docs/W | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| discord.com | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- |
| docs.python.org/3/library/function | okf | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| duckduckgo.com/?q=browser+theme+te | - | - | - | - | - | - | - | - | - | - | - | - | - |
| ebay.de | ok | 1%f | 1%f | 1%f | 1%f | 1%f | 2%f | ok | ok | 4% | 4% | 4% | 1% |
| en.wikipedia.org/wiki/Germany | ok | 1%f | 1%f | 1%f | 1%f | okf | 1%f | ok | ok | ok | ok | ok | ok |
| facebook.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| getbootstrap.com/docs/5.3/forms/ov | okf | ok | ok | ok | ok | ok | ok | ok | 1% | 1% | ok | 1% | ok |
| github.com | 2%- | - | - | - | - | - | - | 6%- | - | - | - | - | - |
| gmx.net | ok | ok | 1% | 1% | ok | ok | 1% | ok | ok | ok | ok | ok | ok |
| gnu.org/software/bash/manual/bash. | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| google.com/search?q=browser+theme+ | - | - | - | - | - | - | - | - | - | - | - | - | - |
| heise.de | okfi | oki | oki | oki | ok | okf | oki | oki | oki | oki | ok | oki | oki |
| ikea.com/de/de/ | 4% | 12%f | 4%f | 8%f | 12%f | 4%f | 4%f | ok | ok | ok | ok | ok | ok |
| kleinanzeigen.de | ok | ok | oki | ok | 3% | 3% | oki | ok | ok | ok | ok | ok | ok |
| linear.app | 1% | 1% | 1% | 1% | 1% | 1% | 1% | ok | 7% | 10% | 9% | 1% | 6% |
| linkedin.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| login.live.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| login.microsoftonline.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| mail.google.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| microsoft.com/de-de | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| minecraft.net/de-de | ok | oki | oki | oki | oki | ok | ok | 5% | 5%i | 5%i | 5% | 5%i | 5%i |
| netflix.com/de/ | - | - | - | - | - | - | - | - | - | - | - | - | - |
| news.ycombinator.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| nytimes.com | 39%i | 1% | 4% | · | · | · | · | ok | ok | ok | ok | ok | ok |
| office.com | 35% | 35% | 35% | 35% | 35% | 28% | 39% | 1% | 1% | 1% | 1% | 1% | 1% |
| open.spotify.com | - | - | - | - | - | - | - | - | - | - | - | - | - |
| outlook.live.com | - | - | - | - | - | - | - | - | - | - | - | - | - |
| outlook.office.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| paypal.com/de/signin | ok | 8% | 8% | 8% | 8% | 8% | ok | ok | ok | ok | ok | ok | ok |
| reddit.com | - | - | - | - | - | - | - | - | - | - | - | - | - |
| shadertoy.com | ok | 6% | 6% | 6% | 6% | 6% | 6% | ok | ok | ok | ok | ok | ok |
| sparkasse.de | okf | ok | ok | ok | ok | okf | ok | ok | ok | ok | ok | ok | ok |
| spiegel.de | oki | ok | ok | oki | ok | ok | ok | oki | oki | oki | ok | ok | oki |
| stackoverflow.com/questions | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| tagesschau.de | oki | okfi | okfi | okfi | oki | okf | oki | oki | oki | oki | ok | oki | oki |
| theguardian.com/europe | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| twitch.tv | - | - | - | - | - | - | - | - | - | - | - | - | - |
| unsplash.com | 1%f | 2%f | 3%f | 1%f | 4%f | 1%f | 5%f | ok | ok | ok | ok | ok | ok |
| vimeo.com | 22%i | 4%i | 21%i | 2%i | 3% | 3% | 1% | oki | oki | oki | ok | oki | oki |
| w3schools.com/html/html_forms.asp | 1% | 1% | 1% | 1% | 1% | 1% | 1% | ok | ok | ok | ok | ok | ok |
| web.de | ok | ok | ok | okf | ok | 1%f | 1% | ok | ok | ok | ok | ok | ok |
| wikipedia.org | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| youtube.com | - | - | - | - | - | - | - | - | - | - | - | - | - |
| zeit.de | - | ok | ok | ok | ok | ok | ok | - | ok | ok | ok | ok | · |

#### Live re-theme, all 116 themes: problems per site

| site | themes with a problem | worst |
|---|---|---|
| apple.com/de/ | 66 / 66 | mocha 2%, macchiato 59%, frappe 38%, gruvbox 41% |
| discord.com | 116 / 116 | mocha 12%-, macchiato 12%-, frappe 12%-, gruvbox 12%- |
| linear.app | 46 / 46 | mocha 1%, macchiato 10%f, frappe 2%, gruvbox 11%f |
| minecraft.net/de-de | 114 / 116 | macchiato 13%, frappe 2%, gruvbox 12%, gruvbox-hard 13% |
| office.com | 113 / 116 | mocha 35%, macchiato 10%, frappe 10%, gruvbox 57% |
| w3schools.com/html/html_forms.asp | 113 / 116 | mocha 1%, macchiato 21%f, frappe 25%f, gruvbox 25%fi |
| ikea.com/de/de/ | 31 / 32 | mocha 5%f, macchiato 28%f, frappe 26%fi, gruvbox 49%f |
| amazon.de | 112 / 116 | mocha 6%, macchiato 43%, frappe 5%, gruvbox 42%f |
| microsoft.com/de-de | 66 / 69 | macchiato 45%f, frappe 33%f, gruvbox 33%f, gruvbox-hard 34% |
| outlook.live.com | 32 / 34 | mocha 3%, macchiato busy, frappe busy, gruvbox busy |
| amazon.de/s?k=ssd | 41 / 45 | mocha 1%, macchiato 65%i, frappe 66%fi, gruvbox 32%fi |
| nytimes.com | 82 / 92 | mocha 26%, nord 42%, dracula 61%, solarized-dark 31% |
| deepl.com/translator | 32 / 37 | mocha 15%, macchiato 51%, frappe 54%, gruvbox 50% |
| bbc.com | 93 / 110 | macchiato 53%, frappe 21%, gruvbox 72%, gruvbox-hard 23% |
| theguardian.com/europe | 30 / 38 | macchiato 39%, frappe 52%, gruvbox 33%, gruvbox-hard 57% |
| unsplash.com | 86 / 116 | macchiato 20%i, frappe 20%, gruvbox 20%, gruvbox-hard 100% |
| vimeo.com | 86 / 116 | mocha 1%i, macchiato 51%i, frappe 29%i, gruvbox 38%i |
| linkedin.com | 85 / 116 | macchiato 100%, frappe 100%, gruvbox 100%, gruvbox-hard 100% |
| shadertoy.com | 85 / 116 | mocha 6%, frappe 53%f, gruvbox 53%f, gruvbox-hard 56%f |
| chatgpt.com | 84 / 116 | macchiato 2%, frappe 2%, gruvbox 3%, gruvbox-hard 3% |
| gnu.org/software/bash/manual/bash. | 84 / 116 | mocha 12%-, macchiato 12%-, frappe 12%-, gruvbox 12%- |
| paypal.com/de/signin | 83 / 116 | macchiato 27%f, frappe 16%f, gruvbox 16%f, gruvbox-hard 20%f |
| stackoverflow.com/questions | 29 / 41 | macchiato 52%f, frappe 44%, gruvbox 14%, gruvbox-hard 15% |
| outlook.office.com | 78 / 116 | frappe 86%f, gruvbox 72%f, gruvbox-hard 72%f, dracula 72%f |
| login.microsoftonline.com | 74 / 116 | macchiato 57%f, frappe 82%f, gruvbox 39%, gruvbox-hard 82%f |
| bahn.de/ | 59 / 116 | macchiato 39%, frappe 2%fi, gruvbox 7%, gruvbox-hard 40%f |
| heise.de | 26 / 63 | latte 1%i, gruvbox-light 1%i, gruvbox-light-hard 1%i, nord-light 1%i |
| kleinanzeigen.de | 21 / 51 | mocha 3%, macchiato 33%i, frappe 36%fi, gruvbox 36%f |
| booking.com | 15 / 45 | mocha 2%, macchiato 59%f, frappe 42%fi, gruvbox 27%f |
| zeit.de | 2 / 6 | frappe busy, gruvbox-light-hard busy |
| en.wikipedia.org/wiki/Germany | 13 / 44 | macchiato 1%f, frappe 76%f, gruvbox 14%f, gruvbox-hard 44%f |
| spiegel.de | 10 / 41 | gruvbox-light 3%i, gruvbox-light-hard 1%i, nord-light 1%i, one-light 3%i |
| sparkasse.de | 19 / 95 | gruvbox-light 2%, gruvbox-light-hard 4%, one-light 2%, ayu-light 3% |
| getbootstrap.com/docs/5.3/forms/ov | 12 / 85 | gruvbox-light 1%, nord-light 1%, tokyonight-day 1%, kanagawa-lotus 1% |
| facebook.com | 4 / 33 | macchiato 92%, frappe 3%, gruvbox 7%f, solarized-dark 21%f |
| accounts.google.com | 0 / 116 |  |
| developer.mozilla.org/en-US/docs/W | 0 / 116 |  |
| docs.python.org/3/library/function | 0 / 116 |  |
| duckduckgo.com/?q=browser+theme+te | 0 / 116 |  |
| ebay.de | 0 / 116 |  |
| github.com | 0 / 116 |  |
| gmx.net | 0 / 116 |  |
| google.com/search?q=browser+theme+ | 0 / 116 |  |
| login.live.com | 0 / 116 |  |
| mail.google.com | 0 / 116 |  |
| netflix.com/de/ | 0 / 116 |  |
| news.ycombinator.com | 0 / 116 |  |
| open.spotify.com | 0 / 116 |  |
| reddit.com | 0 / 116 |  |
| tagesschau.de | 0 / 116 |  |
| twitch.tv | 0 / 116 |  |
| web.de | 0 / 116 |  |
| wikipedia.org | 0 / 79 |  |
| youtube.com | 0 / 116 |  |

Themes with the most problem sites: frappe (30/54), gruvbox (29/53), dracula (28/52), macchiato (27/54), gruvbox-hard (27/52), solarized-dark (27/52), tokyonight-storm (27/52), tokyonight-moon (27/51), nord (26/52), tokyonight (26/52), everforest-hard (25/50), everforest-soft (25/49)

<!-- matrix-after-start -->
### After

#### Fresh load, anchor themes (cell: share of text under 3:1; f = a form field, i = text invisible in the screenshot, - = not themed)

| site | mocha | gruvbox | nord | dracula | terminal | steampunk | aero | latte | gruvbox-light | solarized-light | newspaper | papercolor | high-contrast |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| accounts.google.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| amazon.de | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| amazon.de/s?k=ssd | ok | ok | ok | ok | ok | · | · | ok | ok | ok | ok | ok | ok |
| apple.com/de/ | 2% | 2% | 2% | ok | 2% | 2% | 2% | 2% | 2% | 2% | 2% | 2% | 2% |
| bahn.de/ | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| bbc.com | oki | oki | oki | oki | ok | oki | oki | oki | oki | oki | oki | oki | oki |
| booking.com | busy | busy | busy | busy | busy | busy | busy | busy | busy | busy | busy | busy | busy |
| chatgpt.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| deepl.com/translator | ok | ok | ok | ok | ok | · | · | ok | ok | ok | ok | ok | · |
| developer.mozilla.org/en-US/docs/W | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| discord.com | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- | 12%- |
| docs.python.org/3/library/function | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| duckduckgo.com/?q=browser+theme+te | - | - | - | - | - | - | - | - | - | - | - | - | - |
| ebay.de | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| en.wikipedia.org/wiki/Germany | ok | 1% | 1% | 1% | 1% | ok | 1% | ok | ok | ok | ok | ok | ok |
| facebook.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| getbootstrap.com/docs/5.3/forms/ov | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| github.com | - | - | - | - | - | - | - | - | - | - | - | - | - |
| gmx.net | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| gnu.org/software/bash/manual/bash. | ok | ok | ok | ok | ok | ok | ok | 28%- | ok | ok | ok | ok | ok |
| google.com/search?q=browser+theme+ | - | - | - | - | - | - | - | - | - | - | - | - | - |
| heise.de | oki | oki | oki | oki | oki | ok | oki | oki | oki | oki | ok | oki | oki |
| ikea.com/de/de/ | 2% | 2% | 2% | 2% | 2% | 2% | · | ok | ok | ok | ok | ok | ok |
| kleinanzeigen.de | ok | ok | oki | ok | ok | ok | ok | ok | ok | ok | oki | ok | ok |
| linear.app | 1% | 1% | 1% | 1% | 1% | 1% | 1% | ok | ok | ok | ok | ok | ok |
| linkedin.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| login.live.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| login.microsoftonline.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| mail.google.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| microsoft.com/de-de | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| minecraft.net/de-de | ok | oki | oki | oki | oki | ok | ok | 3% | 4%i | 4%i | 4% | 4%i | 4%i |
| netflix.com/de/ | - | - | - | - | - | - | - | - | - | - | - | - | - |
| news.ycombinator.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| nytimes.com | 4% | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| office.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| open.spotify.com | - | - | - | - | - | - | - | - | - | - | - | - | - |
| outlook.live.com | ok | ok | ok | ok | ok | ok | 42% | ok | ok | ok | ok | ok | ok |
| outlook.office.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| paypal.com/de/signin | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| reddit.com | - | - | - | - | - | - | - | - | - | - | - | - | - |
| shadertoy.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| sparkasse.de | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| spiegel.de | ok | ok | ok | ok | ok | ok | ok | oki | oki | oki | ok | oki | oki |
| stackoverflow.com/questions | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| tagesschau.de | oki | oki | oki | oki | oki | ok | oki | oki | oki | oki | ok | oki | oki |
| theguardian.com/europe | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| twitch.tv | - | - | - | - | - | - | - | - | - | - | - | - | - |
| unsplash.com | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| vimeo.com | oki | oki | oki | oki | ok | ok | ok | oki | oki | oki | ok | oki | oki |
| w3schools.com/html/html_forms.asp | 1% | 1% | 1% | 1% | 1% | 1% | 1% | ok | ok | ok | ok | ok | ok |
| web.de | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| wikipedia.org | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |
| youtube.com | - | - | - | - | - | - | - | - | - | - | - | - | - |
| zeit.de | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok | ok |

#### Live re-theme, all 116 themes: problems per site

| site | themes with a problem | worst |
|---|---|---|
| discord.com | 116 / 116 | mocha 12%-, macchiato 12%-, frappe 12%-, gruvbox 12%- |
| apple.com/de/ | 104 / 116 | mocha 2%, macchiato 2%, frappe 2%, gruvbox 2% |
| ikea.com/de/de/ | 86 / 116 | mocha 2%, macchiato 2%, frappe 2%, gruvbox 2% |
| w3schools.com/html/html_forms.asp | 86 / 116 | mocha 1%, macchiato 1%, frappe 1%, gruvbox 1% |
| en.wikipedia.org/wiki/Germany | 48 / 116 | macchiato 1%, frappe 1%, gruvbox 1%, nord 1% |
| minecraft.net/de-de | 30 / 116 | latte 3%, gruvbox-light 3%, gruvbox-light-hard 3%, nord-light 3% |
| gnu.org/software/bash/manual/bash. | 29 / 116 | mocha 12%-, macchiato 12%-, frappe 12%-, gruvbox 12%- |
| deepl.com/translator | 3 / 40 | macchiato 1%, gruvbox-hard 1%, tokyonight-storm 1% |
| microsoft.com/de-de | 1 / 116 | latte 3% |
| accounts.google.com | 0 / 116 |  |
| amazon.de | 0 / 116 |  |
| amazon.de/s?k=ssd | 0 / 116 |  |
| bahn.de/ | 0 / 116 |  |
| bbc.com | 0 / 116 |  |
| booking.com | 0 / 116 |  |
| chatgpt.com | 0 / 116 |  |
| developer.mozilla.org/en-US/docs/W | 0 / 116 |  |
| docs.python.org/3/library/function | 0 / 116 |  |
| duckduckgo.com/?q=browser+theme+te | 0 / 116 |  |
| ebay.de | 0 / 116 |  |
| facebook.com | 0 / 116 |  |
| getbootstrap.com/docs/5.3/forms/ov | 0 / 116 |  |
| github.com | 0 / 116 |  |
| gmx.net | 0 / 116 |  |
| google.com/search?q=browser+theme+ | 0 / 116 |  |
| heise.de | 0 / 116 |  |
| kleinanzeigen.de | 0 / 116 |  |
| linear.app | 0 / 81 |  |
| linkedin.com | 0 / 116 |  |
| login.live.com | 0 / 116 |  |
| login.microsoftonline.com | 0 / 116 |  |
| mail.google.com | 0 / 116 |  |
| netflix.com/de/ | 0 / 116 |  |
| news.ycombinator.com | 0 / 116 |  |
| nytimes.com | 0 / 116 |  |
| office.com | 0 / 116 |  |
| open.spotify.com | 0 / 116 |  |
| outlook.live.com | 0 / 3 |  |
| outlook.office.com | 0 / 116 |  |
| paypal.com/de/signin | 0 / 116 |  |
| reddit.com | 0 / 116 |  |
| shadertoy.com | 0 / 116 |  |
| sparkasse.de | 0 / 116 |  |
| spiegel.de | 0 / 116 |  |
| stackoverflow.com/questions | 0 / 116 |  |
| tagesschau.de | 0 / 116 |  |
| theguardian.com/europe | 0 / 116 |  |
| twitch.tv | 0 / 116 |  |
| unsplash.com | 0 / 116 |  |
| vimeo.com | 0 / 116 |  |
| web.de | 0 / 116 |  |
| wikipedia.org | 0 / 116 |  |
| youtube.com | 0 / 116 |  |
| zeit.de | 0 / 116 |  |

Themes with the most problem sites: macchiato (7/53), tokyonight-storm (7/53), frappe (6/53), gruvbox (6/53), gruvbox-hard (6/53), nord (6/53), solarized-dark (6/53), tokyonight-moon (6/53), everforest-hard (6/53), everforest-soft (6/53), rose-pine-moon (6/52), mocha (5/54)
<!-- matrix-after-end -->

## Signed in: Outlook mail, calendar, people, Gmail, YouTube, GMX

Measured on the desktop from a *copy* of the real profile (`_profileshots.py`, view only:
the pages were opened and themed, nothing was clicked, typed or changed; the copy and
its screenshots were deleted afterwards and none of them is in this report, since every
one shows the account). Each view in all 116 themes, applied live one after another —
the Settings > Theme path, which is the one that was broken.

| view | before: themes unreadable | worst | after | worst |
|---|---|---|---|---|
| Outlook mail (inbox) | 0 / 116 | — | 0 / 116 | 0.1 % |
| Outlook calendar (month) | 115 / 116 | 38 % of the text | 1 / 116 | 3.5 % (slate) |
| Outlook people | 114 / 116 | 31 % | 3 / 116 | 4.6 % (zenburn), 2 % (apprentice, slate) |
| Gmail inbox | 5 / 116 | 68 % | 1 / 116 | 0.2 % (the first theme after load, transient) |
| YouTube | not themed (dark by design) | — | not themed | — |
| GMX (consent page) | 0 / 116 | — | 0 / 116 | — |

"Before" is the code of this branch *without* causes 11 and 12; the original code was
measured on the public pages only. What the calendar and People looked like before: the
mini-calendar's dates, the "add calendar" links and the People toolbar in the *previous*
theme's text colour on the new theme's panel — invisible on every switch after the first,
and worse with each one. The residual few percent on People are the toolbar's disabled
icon glyphs in the site's own grey (2.3–3:1 by Outlook's choice, one character each).

Seen by eye and not by the audit: Gmail's "compose" pill keeps light text on its pastel
fill in dark themes, because the fill is painted by a pseudo-element, which neither the
ancestor walk nor the hit test can see. Listed under "still broken".

## Still broken, or left alone on purpose

What the after-run still shows, and why each is left as it is. Everything here was
looked at in the rows (element, colours, ratio, position) and most of it in the screenshot.

**Not a theme problem: the site's own ink**

- **Discord** (dark by design, not themed) — the 12 % in every cell is the cookie banner's
  light-blue links on white, Discord's own choice.
- **apple.com, 2 % in every theme, light ones included, before and after** — the media
  gallery's "Jetzt streamen" buttons: grey on near-black at 2.5–2.6:1, as Apple draws them,
  below the fold.
- **Linear, 1 %** — Linear's own decorative greys ("Fig 0.1", "Thinking…") on its own black
  page, 1.8–3:1 by design.
- **Wikipedia, 1 % in dark themes** — the ISBN numbers in the references (a `<bdi>` inside the
  link, 2.7:1 on the themed page; 17 characters each).
- **Outlook People, 3 of 116 themes, ≤ 4.6 %** (signed in) — the toolbar's disabled icon
  glyphs in Outlook's grey, one character each.

**Not a theme problem: the audit over-counts**

- **IKEA, Minecraft, NYTimes 2–4 %** — visually hidden `<legend>`s and labels (clipped to a
  pixel, off-screen, for screen readers) that still carry characters; nothing a reader sees.
- **w3schools, 1 %** — the text inside an SVG app-store badge; the pass does not touch SVG.
- **DeepL, 3 themes at 1 %** — the words of the typing animation, caught mid-fade.
- **microsoft.com, Latte, 3 %** — a store-assistant popup caught sliding in (1 of 116).
- **`i` marks on bbc, heise, tagesschau, spiegel, vimeo, minecraft** — a text box that is one
  flat colour in the screenshot: a lazy image or a consent overlay not yet painted at shot
  time. Same cells before and after; the cells themselves are `ok`.

**The rig, not the theme**

- **gnu.org's Bash manual** — one 1 MB page of 19 000 elements; its renderer ran out of memory
  under the rig's cap in 29 live themes and one fresh load, and the browser's recovery showed
  its own setup page, which the audit then measured (the greyed-out future steps are the
  "28 %"). The 87 themes that completed are `ok`.
- **booking.com, fresh loads** — the bot challenge page answered the audit with a timeout in
  every anchor theme (`busy`); the live run got the real page: 0 of 116.
- **LinkedIn, after-run** — the desktop was served a "you have been blocked" page, so its 0 %
  verifies nothing; the before-run had 85 of 116 live themes with a problem on the real page.
  Not re-verified.
- **Outlook landing page** (public; redirects to a Microsoft marketing page) — the heaviest
  page in the set: busy for 15–30 s after load, and under the rig's software renderer its
  memory grows even untouched (about 8 MB/s with site theming off, about 35 MB/s with it on),
  so the live-run process hit its cap after the first theme on both the old and the new code.
  The 6 s fresh cells caught it half-hydrated; the fresh row in the table above is a 45 s
  window, one load per process (the page switches to its own dark mode 15–30 s after load,
  cause 14). Aero is the one cell that would not settle: 0 % in one 45 s run, 42 % in
  another. Watched live, the page's own scripts keep mutating for a long time and the
  pass's queue sits at about 5 000 elements while they do, so an audit can land on a
  half-themed page; once the page rests the footnotes are repainted (seen in
  `_sitediag.py` with `DIAG_WATCH`). The fourfold memory growth with theming on is worth a
  look in the real browser on a GPU.

**Still broken**

- **Gmail's "compose" pill** (signed in) keeps light text on its pastel fill in dark themes:
  the fill is a pseudo-element, which neither the ancestor walk nor the hit test can see. A
  rule for `::before`/`::after` fills would need the pseudo-element's computed style per
  element, at a cost per element the pass does not pay today.
- **Outlook calendar, Slate, 3.5 %** (signed in) — one theme of 116; not chased down.
- **Unsplash dark runs on the desktop** lost their process; re-measured on the server: 0 of
  116 live, `ok` fresh.

## Tests

- `test_sitetheme_rules.py` (new): one page per root cause above, 45 checks in 11
  sections. Against the old module (`theme-audit/check/rules_on_head.py` runs the suite
  with the pre-fix `theme_web.py`) 23 of them are red, in 9 of the 11 sections; the
  placeholder and big-page sections pin rules whose real-page failures the synthetic
  page does not reproduce on the old code. `test_sitetheme_render.py`, `test_contrast.py`, `test_paintcontrast.py`,
  `test_theme.py`, `test_looks.py`, `test_look2.py`, `test_themefix.py`,
  `test_themetokens.py`, `test_offpalette.py`, `test_palette.py`: green.

## What to port to the Windows, macOS and Android editions

- **theme_web.py, all of it** (Windows and macOS carry the same module): every row in the
  table above is in `SITE_JS` and `_base_css`. The transition removal matters most; the
  rest comes with it. `test_sitetheme_rules.py` and `_siteaudit.js` go with it.
- **Android** has its own painter: the rules to carry over are 2 (never read back a
  colour during a transition; record what you wrote), 3 (compare only what the element
  shows), 6 (ask what is painted under the text, not only the ancestors), 7 (keep what
  reads), 8 (the placeholder measured like text, `dim` first), 9 (an element that gets
  text later is looked at again), 13 (a gradient clipped to the letters is ink: judge its
  stops, replace it with a fill when they fail), 14 (a changed ground is not a disagreement: no
  cap on re-judging an element whose own colours never moved), 1 (one run at a time).
- **STYLE / settings.html / start.html**: the rounded geometry is pure QSS/CSS and ports
  as-is; the accent bar is three lines in the tab painter. The pages are shared through
  `~/claude/browser-pages`; they call no new bridge method.
