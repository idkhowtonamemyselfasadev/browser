#!/usr/bin/env python3
"""Screen sharing: getDisplayMedia() ends in a live video track.

Offscreen, scratch data. A real click on the page starts the share,
the browser's own SharePicker comes up, a screen is pressed in it, and
the page must get a stream back. Qt asks twice - desktopMediaRequested
for the source, then permissionRequested with DesktopVideoCapture - and
the second question used to go unanswered, so Discord and TeamSpeak
sat on the share forever. Cancel in the picker must still be a no."""
import json
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()
from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QToolButton  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGE = """<!doctype html><title>Share</title>
<button id=b style="width:300px;height:120px">share</button>
<script>
window.result = null;
document.getElementById('b').onclick = async function () {
  try {
    var s = await navigator.mediaDevices.getDisplayMedia({video: true});
    var t = s.getVideoTracks()[0];
    window.result = 'ok:' + t.readyState + ':' + t.getSettings().displaySurface;
    setTimeout(function () { t.stop(); }, 500);
  } catch (e) { window.result = 'err:' + e.name; }
};
</script>"""

app = H.app()
srv = H.Server({"/share": PAGE})
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(500)
view = win.new_tab(url=None)
H.load(view, srv.url("/share"))


def answer_picker(action):
    """Answer the picker from inside its nested loop, the way a press
    would: the first screen, or Cancel."""
    def go():
        picker = win._share_picker
        if picker is None:
            QTimer.singleShot(100, go)
            return
        if action == "cancel":
            picker.cancel()
            return
        items = picker.findChildren(QToolButton, "shareitem")
        H.press(items[0]) if items else picker.cancel()
    QTimer.singleShot(300, go)


def share(action):
    H.js(view, "window.result = null")
    answer_picker(action)
    H.click(view, "#b")
    H.wait_for(lambda: H.js(view, "window.result") is not None, 20000)
    return H.js(view, "window.result")


r = share("pick")
check("picking a screen gives the page a live track",
      isinstance(r, str) and r.startswith("ok:live"), r)
check("no permission card left waiting after the pick",
      not win._perm_queue, len(win._perm_queue))
H.spin(800)
r = share("cancel")
# Qt turns a cancelled pick into INVALID_STATE, which the page sees as
# AbortError; what matters is that it is an error and not a stream
check("Cancel in the picker is a refusal, not a stream",
      isinstance(r, str) and r.startswith("err:"), r)

srv.stop()
print("FAILED: " + json.dumps(fails) if fails else "all ok")
sys.exit(1 if fails else 0)
