#!/usr/bin/env python3
"""The history page must not tell anybody else where he has been.

history.html used to build every row's icon as

    https://www.google.com/s2/favicons?sz=32&domain=<host>

so opening the history sent Google one request per site in it: the whole
list of where he had been, to one company, from the one page that exists
to be private. The browser already keeps the icon of every site as it is
visited (cache_favicon), whose own docstring says a list that asks fifty
sites for their icons "tells each one of them that he is looking at his
bookmarks" -- the history page was doing worse, to a single party.

These checks pin both halves: the icons come out of the local store, and
no page the browser ships asks a third party for one.

Offscreen, scratch data; the real history and config are never opened.
"""
import os
import re
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


# A 1x1 PNG, which is all these checks need of a "kept icon".
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082")


class Store:
    """Just the icon store, which is all site_icon_data touches."""

    def __init__(self, where):
        self.where = Path(where)
        self.where.mkdir(parents=True, exist_ok=True)

    def icons_dir(self):
        return self.where

    def keep(self, host):
        (self.where / (re.sub(r"[^\w.-]", "_", host) + ".png")
         ).write_bytes(PNG)

    def cached_favicon(self, host_or_url=""):
        return B.Browser.cached_favicon(self, host_or_url)

    def site_icon_data(self, host_or_url=""):
        return B.Browser.site_icon_data(self, host_or_url)


print("(1) no page the browser ships fetches an icon from anybody")
PAGES = sorted(p for p in HERE.glob("*.html"))
check("there are pages to check", len(PAGES) > 3, len(PAGES))
offenders = []
for page in PAGES:
    text = page.read_text(errors="replace")
    for line in text.splitlines():
        # the comment explaining the old bug names the URL on purpose
        if line.lstrip().startswith(("//", "*", "/*")):
            continue
        if "s2/favicons" in line or re.search(
                r"""favicons?\?[^"']*domain=""", line):
            offenders.append("%s: %s" % (page.name, line.strip()[:70]))
check("no page builds a favicon URL at a third party",
      not offenders, offenders)
check("history.html in particular does not name the old endpoint "
      "outside a comment",
      not [o for o in offenders if o.startswith("history.html")], offenders)

print("\n(2) the icons come out of the local store")
store = Store(Path(os.environ["XDG_CONFIG_HOME"]) / "icontest")
check("a site with no kept icon gets nothing, not a URL",
      store.site_icon_data("never-visited.test") == "",
      store.site_icon_data("never-visited.test"))
store.keep("kept.test")
got = store.site_icon_data("kept.test")
check("a site with a kept icon gets it", got.startswith("data:image/png;"),
      got[:40])
check("...as data, so nothing is fetched to draw it",
      got.startswith("data:") and "http" not in got, got[:40])
check("a full URL works as well as a bare host",
      store.site_icon_data("https://kept.test/some/page") == got)
check("www. is the same site",
      store.site_icon_data("www.kept.test") == got)
check("an empty host asks for nothing", store.site_icon_data("") == "")

print("\n(3) the bridge hands the page a map it can draw from")
check("the browser has a siteIcons slot for the page",
      hasattr(B.Bridge, "siteIcons"))
check("...and Browser can answer it without a fetch",
      hasattr(B.Browser, "site_icon_data"))

print("\n(4) the page asks for every host it is about to draw")
page = (HERE / "history.html").read_text()
check("it keeps a map of icons rather than a URL per row",
      "let icons = {}" in page)
check("it asks the browser for them", "bridge.siteIcons(" in page)
check("the list view asks before it draws",
      re.search(r"withIcons\(.*renderList", page, re.S) is not None)
check("the sites view asks before it draws",
      re.search(r"withIcons\(.*renderSites", page, re.S) is not None)
check("the stats view asks before it draws",
      re.search(r"withIcons\(.*renderStats", page, re.S) is not None)
check("a site with no icon draws a placeholder instead of fetching",
      "noicon" in page)
check("...and the placeholder is styled, so the row does not jump",
      "img.noicon" in page)
check("a host that comes back without an icon is not asked for twice",
      'icons[host] = ""' in page)

print("\n%d checks failed" % len(fails))
for name in fails:
    print("  - " + name)
sys.exit(1 if fails else 0)
