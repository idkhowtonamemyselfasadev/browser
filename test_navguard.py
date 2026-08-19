#!/usr/bin/env python3
"""A group-header pill is a tab that is not a page.

Tab groups put a real QWidget into the QTabWidget as the group's header
pill. It has no back(), no forward(), no reload() and no load() - it is
chrome, not a browser view. go_home() has always known that and steps
aside when the tab in front is a header. The other navigation actions
did not: with a header selected, Back / Forward / Reload and the Ctrl+R
and F5 shortcuts reached straight for methods the header does not have
and crashed with AttributeError; the address bar's _navigate and a typed
line routed to the current tab (open_typed with new_tab=False) did the
same at view.load().

This drives each of those with a header as the current tab and asserts
it is a quiet no-op rather than a crash - and that a real page tab still
navigates as before. Offscreen, against scratch data; your own vault and
config are never opened.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtGui import QShortcut, QKeySequence  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


def no_raise(name, fn):
    """Runs fn(); passes only if it did not raise."""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - the whole point is "did it throw"
        check(name, False, "%s: %s" % (type(exc).__name__, exc))
        return
    check(name, True)


app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1300, 900)
# offscreen or not, a window nobody showed reports every widget invisible,
# and then the selection assertions below pass for the wrong reason
win.show()
app.processEvents()

print("(1) a header can be made the tab in front")
# A group registers its header pill as a real tab. The browser bounces
# selection off a header to the nearest real tab, so to pin the header in
# front we make it the only tab left: strip the page tabs directly (not
# close_tab, which would re-open a fresh one) and _nearest_tab then finds
# nowhere to bounce to, exactly as it does in the transient window the
# guard is really for.
win._register_group("G", "#ff0000")
app.processEvents()
hidx = win._header_index("G")
check("the group's header was added as a tab", hidx is not None, hidx)
for i in reversed(range(win.tabs.count())):
    if not win._is_header(win.tabs.widget(i)):
        win.tabs.removeTab(i)
app.processEvents()
check("the header is the only tab now",
      win.tabs.count() == 1 and win._is_header(win.tabs.widget(0)),
      win.tabs.count())
win.tabs.setCurrentIndex(0)
app.processEvents()
view = win.current()
check("the tab in front really is that header",
      view is not None and win._is_header(view), view)
check("and a header has no page navigation to call",
      not hasattr(view, "reload") and not hasattr(view, "load"), view)

print("\n(2) the toolbar actions step aside instead of crashing")
no_raise("Back is a no-op on a header", win._tb_back)
no_raise("Forward is a no-op on a header", win._tb_forward)
no_raise("Reload is a no-op on a header", win._tb_reload)

print("\n(3) the reload shortcuts step aside too")
shortcuts = {s.key().toString(): s for s in win.findChildren(QShortcut)}
check("Ctrl+R is bound", "Ctrl+R" in shortcuts)
check("F5 is bound", "F5" in shortcuts)
# Fire the real shortcut signal, header still in front. Before the guard
# these lambdas called self.current().reload() and threw.
for key in ("Ctrl+R", "F5"):
    if key in shortcuts:
        no_raise("%s fires without crashing on a header" % key,
                 shortcuts[key].activated.emit)

print("\n(4) the address bar and a typed line step aside as well")
win.urlbar.setText("example.com")
no_raise("the address bar's navigate is a no-op on a header", win._navigate)
no_raise("a line typed to the current tab is a no-op on a header",
         lambda: win.open_typed("example.com", new_tab=False))

print("\n(5) with no tab at all, the same actions are still safe")
# Strip every tab so current() is None - the other half of go_home's
# guard. removeTab directly, so nothing re-opens a fresh last tab.
while win.tabs.count():
    win.tabs.removeTab(0)
app.processEvents()
check("there is no tab in front now", win.current() is None, win.current())
no_raise("Back is safe with no tab", win._tb_back)
no_raise("Forward is safe with no tab", win._tb_forward)
no_raise("Reload is safe with no tab", win._tb_reload)
no_raise("navigate is safe with no tab",
         lambda: (win.urlbar.setText("example.com"), win._navigate()))

print("\n(6) a real page tab still navigates - the guard is a no-op only "
      "for headers")
view = win.new_tab(url=None)
app.processEvents()
check("a fresh tab is a real view, not a header",
      view is not None and not win._is_header(view), view)
check("and it can be reloaded", hasattr(view, "reload"))
no_raise("Reload runs on a real tab", win._tb_reload)
no_raise("Back runs on a real tab", win._tb_back)
no_raise("Forward runs on a real tab", win._tb_forward)
win.urlbar.setText("example.com")
no_raise("the address bar navigates a real tab", win._navigate)
check("and the navigation reached the view",
      getattr(view, "_requested", None) == win._resolve_typed("example.com"),
      getattr(view, "_requested", None))

print("\n%d checks failed" % len(fails))
if fails:
    for f in fails:
        print("  - " + f)
sys.exit(1 if fails else 0)
