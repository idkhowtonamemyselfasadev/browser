#!/usr/bin/env python3
"""The first-run setup wizard, driven for real.

The two questions setup grew today are the ones with the most to go
wrong, because neither is a switch: a theme has to reach the browser
AND repaint the page it was picked on, and a start-up address has to
survive a round trip through the browser's own idea of what an address
is. So this drives them by clicking, not by calling.

What is proved here:

  * a first run on an empty config reaches the summary, eight steps
  * the Colours page offers twelve themes on three shelves, with
    whatever is in use ticked
  * clicking one writes config["theme"], moves ACTIVE_THEME, and
    repaints the very page it was clicked on
  * "A page you choose" + an address writes config["startUrl"], and a
    typo writes nothing and says so
  * a typo and Next, rather than Save: the step is not left until the
    browser has ruled, so the refusal is read where the box is - and a
    second Next goes, so he is told once and not held there
  * the summary names both
  * Esc out of setup and open a new tab: the answers are still there

Offscreen, scratch data only. Your own config is never opened.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B, SCRATCH  # noqa: E402,F401
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  <" + str(detail) + ">") if detail != "" and not cond else ""))
    if not cond:
        fails.append(name)


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def js(page, code):
    box = {}
    loop = QEventLoop()
    page.runJavaScript("(function(){" + code + "})()", B.MAIN_WORLD_ID,
                       lambda r: (box.update({"v": r}), loop.quit()))
    QTimer.singleShot(8000, loop.quit)
    loop.exec()
    return box.get("v")


# an empty config: a first run, nothing chosen, no setupDone anywhere
B.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))

app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1360, 900)
win.show()
spin(3500)

view = win.tabs.widget(0)
page = view.page()
check("the first tab is the start page", "start.html" in view.url().toString(),
      view.url().toString())

# the wizard let itself in
state = js(page, """
  return JSON.stringify({
    open: document.getElementById("wizard").classList.contains("open"),
    steps: document.querySelectorAll("#wizsteps .railitem").length,
    stepno: document.getElementById("wizstepno").textContent,
    rail: [...document.querySelectorAll("#wizsteps .rname")].map(n => n.textContent),
  });
""")
S = json.loads(state or "{}")
check("setup opens by itself on a first run", S.get("open") is True)
# Nine since the master password got a page of its own. The count is
# spelled out rather than read from wizPages() on purpose: this check
# exists to notice when a page appears or disappears, and one that
# asked the wizard how many pages it has could never notice anything.
check("nine steps", S.get("steps") == 9, S.get("steps"))
check("the counter says so too", S.get("stepno") == "Step 1 of 9",
      S.get("stepno"))
check("Colours is the second rail entry",
      (S.get("rail") or [None, None])[1] == "Colours", S.get("rail"))

# ---------------------------------------------------------------- 1
print("\n-- the Colours page --")
js(page, "gotoWiz(1); return 1;")
spin(400)
shelf = js(page, """
  return JSON.stringify({
    title: document.getElementById("wiztitle").textContent,
    cards: [...document.querySelectorAll("#wizbody .tcard")]
             .map(c => c.dataset.theme),
    shelves: [...document.querySelectorAll("#wizbody .wsec")]
               .map(s => s.textContent),
    sel: [...document.querySelectorAll("#wizbody .tcard.sel")]
           .map(c => c.dataset.theme),
    more: document.querySelector("#wizbody .whint").textContent,
    swatch: getComputedStyle(
      document.querySelector('[data-theme="gruvbox"] .tsw')).backgroundColor,
  });
""")
T = json.loads(shelf or "{}")
check("twelve themes are offered", len(T.get("cards") or []) == 12,
      T.get("cards"))
check("three shelves, named", T.get("shelves") ==
      ["Dark", "Light", "With character"], T.get("shelves"))
check("the theme in use is the one ticked", T.get("sel") == ["mocha"],
      T.get("sel"))
check("and it says where the other hundred are",
      "Settings" in (T.get("more") or ""), T.get("more"))
check("a swatch is painted in its own theme's colours, not this one's",
      T.get("swatch") == "rgb(29, 32, 33)", T.get("swatch"))

# picking one: the browser, the config and this very page
js(page, """document.querySelector('[data-theme="gruvbox"]').click(); return 1;""")
spin(1200)
after = js(page, """
  return JSON.stringify({
    root: document.documentElement.getAttribute("data-theme"),
    sel: [...document.querySelectorAll("#wizbody .tcard.sel")]
           .map(c => c.dataset.theme),
  });
""")
A = json.loads(after or "{}")
check("picking a theme writes it to the config",
      win.config.get("theme") == "gruvbox", win.config.get("theme"))
check("and the browser is wearing it", B.ACTIVE_THEME == "gruvbox",
      B.ACTIVE_THEME)
check("and the page it was picked on repainted itself",
      A.get("root") == "gruvbox", A.get("root"))
check("and the tick moved", A.get("sel") == ["gruvbox"], A.get("sel"))

# ---------------------------------------------------------------- 2
print("\n-- when the browser starts --")
js(page, "gotoWiz(3); return 1;")
spin(500)
L = json.loads(js(page, """
  return JSON.stringify({
    nav: document.getElementById("wiztitle").textContent,
    cards: [...document.querySelectorAll("#wizstartcards .card")]
             .map(c => c.dataset.start),
    sel: [...document.querySelectorAll("#wizstartcards .card.sel")]
           .map(c => c.dataset.start),
    box: !!document.getElementById("wizstarturl"),
    wall: !!document.querySelector("#wizbody .wgrid"),
  });
""") or "{}")
check("the start-page page carries the question",
      L.get("cards") == ["start", "custom"], L.get("cards"))
check("the start page is what a fresh install answers",
      L.get("sel") == ["start"], L.get("sel"))
check("and no address box until it is asked for", L.get("box") is False)
check("the wallpaper picker is still on the page", L.get("wall") is True)

js(page, """document.querySelector('[data-start="custom"]').click(); return 1;""")
spin(400)
ask = json.loads(js(page, """
  return JSON.stringify({
    box: !!document.getElementById("wizstarturl"),
    msg: document.getElementById("wizstartmsg").textContent,
  });
""") or "{}")
check("asking for one shows the box", ask.get("box") is True)
check("and says nothing is in force until it is saved",
      "press Save" in (ask.get("msg") or ""), ask.get("msg"))

# a typo: nothing saved, and said out loud
js(page, """
  const i = document.getElementById("wizstarturl");
  i.value = "http://";
  i.dispatchEvent(new Event("input"));
  document.getElementById("wizstartsave").click();
  return 1;
""")
spin(900)
bad = json.loads(js(page, """
  const m = document.getElementById("wizstartmsg");
  return JSON.stringify({t: m.textContent, bad: m.classList.contains("bad"),
                         box: document.getElementById("wizstarturl").value});
""") or "{}")
check("a typo is refused out loud", bad.get("bad") is True, bad.get("t"))
check("and nothing was written", not win.config.get("startUrl"),
      win.config.get("startUrl"))
check("and the refused address is still the one in the box",
      bad.get("box") == "http://", bad.get("box"))

# a real one
js(page, """
  const i = document.getElementById("wizstarturl");
  i.value = "gmx.net";
  i.dispatchEvent(new Event("input"));
  document.getElementById("wizstartsave").click();
  return 1;
""")
spin(900)
ok = json.loads(js(page, """
  const m = document.getElementById("wizstartmsg");
  return JSON.stringify({t: m.textContent, bad: m.classList.contains("bad")});
""") or "{}")
check("an address is saved", win.config.get("startUrl") == "gmx.net",
      win.config.get("startUrl"))
check("and reported as what it resolves to",
      "https://gmx.net" in (ok.get("t") or "") and not ok.get("bad"),
      ok.get("t"))
check("and it is what the browser would open",
      win.start_target().toString() == "https://gmx.net",
      win.start_target().toString())

# a typo and Next, rather than a typo and Save. The browser rules on an
# address on its own time, and the ruling is a line under the box: the
# step used to move on without waiting for it, so the complaint landed
# on a page he was no longer looking at and he was never told.
print("\n-- a typo, and Next instead of Save --")
js(page, """
  const i = document.getElementById("wizstarturl");
  i.value = "http://";
  i.dispatchEvent(new Event("input"));
  document.getElementById("wiznext").click();
  return 1;
""")
spin(1200)
held = json.loads(js(page, """
  const m = document.getElementById("wizstartmsg");
  return JSON.stringify({
    step: document.getElementById("wizstepno").textContent,
    onStep: !!m,
    msg: m ? m.textContent : null,
    bad: m ? m.classList.contains("bad") : null,
    box: (document.getElementById("wizstarturl") || {}).value,
  });
""") or "{}")
check("Next does not carry him off the step it was refused on",
      held.get("step") == "Step 4 of 9", held.get("step"))
check("he is told, on the page the box is on",
      held.get("onStep") is True and held.get("bad") is True,
      held.get("msg"))
check("the refused address is still the one in the box",
      held.get("box") == "http://", held.get("box"))
check("and the address that already worked is untouched",
      win.config.get("startUrl") == "gmx.net", win.config.get("startUrl"))

# told once, not trapped: nothing is pending any more, so Next goes
js(page, 'document.getElementById("wiznext").click(); return 1;')
spin(900)
check("pressing Next again goes - he is held once, not stuck",
      js(page, 'return document.getElementById("wizstepno").textContent;')
      == "Step 5 of 9",
      js(page, 'return document.getElementById("wizstepno").textContent;'))

# and an address the browser accepts still leaves in one press
js(page, "gotoWiz(3); return 1;")
spin(700)
js(page, """
  const i = document.getElementById("wizstarturl");
  i.value = "posteo.de";
  i.dispatchEvent(new Event("input"));
  document.getElementById("wiznext").click();
  return 1;
""")
spin(1400)
check("an address it accepts does not hold him up at all",
      js(page, 'return document.getElementById("wizstepno").textContent;')
      == "Step 5 of 9",
      js(page, 'return document.getElementById("wizstepno").textContent;'))
check("and it was written on the way past",
      win.config.get("startUrl") == "posteo.de", win.config.get("startUrl"))

# put it back where the rest of this file expects it
js(page, "gotoWiz(3); return 1;")
spin(700)
js(page, """
  const i = document.getElementById("wizstarturl");
  i.value = "gmx.net";
  i.dispatchEvent(new Event("input"));
  document.getElementById("wizstartsave").click();
  return 1;
""")
spin(1200)
check("and back to the one the summary is about",
      win.config.get("startUrl") == "gmx.net", win.config.get("startUrl"))


# ---------------------------------------------------------------- 3
print("\n-- the summary --")
js(page, "gotoWiz(wizPages().length - 1); return 1;")
spin(600)
rows = json.loads(js(page, """
  const out = {};
  for (const r of document.querySelectorAll("#wizsummary .sumrow"))
    out[r.querySelector(".k").textContent] = r.querySelector(".v").textContent;
  return JSON.stringify(out);
""") or "{}")
check("the summary names the theme", rows.get("Theme") == "Gruvbox Dark",
      rows.get("Theme"))
check("and what the browser will open on",
      rows.get("When the browser starts") == "gmx.net",
      rows.get("When the browser starts"))
check("and still names everything it named before",
      rows.get("Language") == "English" and rows.get("Search engine")
      and rows.get("Wallpaper"), rows)

# ---------------------------------------------------------------- 4
print("\n-- Esc out, and come back --")
js(page, "leaveWiz(); return 1;")
spin(400)
check("setup did not mark itself finished",
      js(page, 'return localStorage.getItem("setupDone");') in (None, ""),
      js(page, 'return localStorage.getItem("setupDone");'))

second = win.new_tab(url=QUrl(B.START_PAGE).toString())
spin(3500)
p2 = second.page()
check("a new tab gets setup again",
      js(p2, 'return document.getElementById("wizard")'
             '.classList.contains("open");') is True)
js(p2, "gotoWiz(1); return 1;")
spin(500)
kept = json.loads(js(p2, """
  return JSON.stringify({
    theme: [...document.querySelectorAll("#wizbody .tcard.sel")]
             .map(c => c.dataset.theme),
  });
""") or "{}")
check("the theme he picked is still the one ticked",
      kept.get("theme") == ["gruvbox"], kept.get("theme"))
js(p2, "gotoWiz(3); return 1;")
spin(500)
kept2 = json.loads(js(p2, """
  return JSON.stringify({
    sel: [...document.querySelectorAll("#wizstartcards .card.sel")]
           .map(c => c.dataset.start),
    val: (document.getElementById("wizstarturl") || {}).value,
  });
""") or "{}")
check("and the start-up address came back with its card ticked",
      kept2.get("sel") == ["custom"] and kept2.get("val") == "gmx.net", kept2)

# ---------------------------------------------------------------- 5
print("\n-- a first run walked to the end --")
third = win.new_tab(url=QUrl(B.START_PAGE).toString())
spin(3000)
p3 = third.page()
walk = js(p3, """
  window.__errs = [];
  window.addEventListener("error", (e) => window.__errs.push(String(e.message)));
  const seen = [];
  const total = wizPages().length;
  for (let i = 0; i < total; i++) {
    seen.push(document.getElementById("wizbody").children.length);
    document.getElementById("wiznext").click();
  }
  return JSON.stringify({
    seen: seen,
    total: total,
    open: document.getElementById("wizard").classList.contains("open"),
    done: localStorage.getItem("setupDone"),
    errs: window.__errs,
  });
""")
W = json.loads(walk or "{}")
check("every one of the nine pages built something",
      all(n > 0 for n in (W.get("seen") or []))
      and len(W.get("seen") or []) == W.get("total") == 9,
      (W.get("seen"), W.get("total")))
check("Finish closes setup", W.get("open") is False)
check("and marks it done", W.get("done") == "1", W.get("done"))
check("and nothing threw on the way", not W.get("errs"), W.get("errs"))

print("\n%d checks failed" % len(fails))
for f in fails:
    print("  - " + f)
QTimer.singleShot(200, app.quit)
app.exec()
sys.exit(1 if fails else 0)
