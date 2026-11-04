#!/usr/bin/env python3
"""The script that runs on YouTube, which had no test in its life.

YOUTUBE_JS gates itself on the youtube.com hostname, so nothing served
from a test server could ever reach it, and all three of its parts went
unchecked: the codec gate (now removed), the ad scrub, and the
wall-remover. The suite gets past the gate by running the real source
with `location` shadowed -- the script reads the hostname once, through
that name, so handing it a different object is enough. Nothing pretends
to be YouTube on the network.

What is checked here is what the script is FOR: that it installs
nothing anywhere else, that the ad data goes out of player data in
place, that a wall that reaches the screen is taken off it, and that
what the engine can play is left to the engine to answer.
"""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
os.environ["BROWSER_NO_GPU_ASK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


app = H.app()
srv = H.Server({"/": "<html><body><p>a page</p></body></html>"})
win = B.Browser()
win.show()
view = win.current()


def as_host(host):
    """Run the real script in a fresh page, as if the page were `host`.

    The script is one self-contained expression that reads
    `location.hostname`, so wrapping it in a function that takes
    `location` as its parameter shadows the real one for the whole of
    it and nothing else."""
    H.load(view, srv.url("/"))
    H.spin(200)
    H.js(view, "(function (location) {\n%s\n})(%s)"
         % (B.YOUTUBE_JS, '{hostname: "%s"}' % host))
    H.spin(100)


def native(what):
    return H.js(view, "String(%s).indexOf('[native code]') >= 0" % what)


print("\n(1) anywhere that is not YouTube, it does nothing")
as_host("example.com")
check("JSON.parse is left alone", native("JSON.parse") is True)
check("...and so is the fetch path", native("Response.prototype.json") is True)
check("...and nothing is defined on window",
      H.js(view, "Object.getOwnPropertyDescriptor("
                 "window, 'ytInitialPlayerResponse') === undefined") is True)
check("a lookalike hostname is not YouTube either",
      (as_host("notyoutube.com.evil.test"),
       native("JSON.parse"))[1] is True)


print("\n(2) on YouTube, the ad data goes out of the player data")
as_host("www.youtube.com")
check("the parse path is armed", native("JSON.parse") is False)
check("...and the fetch path with it",
      native("Response.prototype.json") is False)
scrubbed = H.js(view, """JSON.stringify(JSON.parse(JSON.stringify({
    streamingData: {formats: [1, 2]}, adPlacements: [{a: 1}],
    playerAds: [{b: 2}], adSlots: [{c: 3}],
    adBreakHeartbeatParams: "x", videoDetails: {title: "t"}})))""")
check("every ad key is gone",
      all(key not in scrubbed for key in
          ("adPlacements", "playerAds", "adSlots",
           "adBreakHeartbeatParams")), scrubbed)
check("...and what the player needs is untouched",
      '"streamingData"' in scrubbed and '"formats"' in scrubbed
      and '"title":"t"' in scrubbed, scrubbed)
nested = H.js(view, """JSON.stringify(JSON.parse(JSON.stringify({
    playerResponse: {playabilityStatus: {status: "OK"},
                     adPlacements: [1], inner: {adSlots: [2]}}})))""")
check("ad keys deeper in are gone as well",
      "adPlacements" not in nested and "adSlots" not in nested, nested)
check("...and the status beside them is not",
      '"status":"OK"' in nested, nested)
plain = H.js(view, """JSON.stringify(JSON.parse(
    '{"title":"not player data","adSlots":"kept"}'))""")
check("an object that is not player-shaped is not even entered",
      "kept" in plain, plain)
# ...and one that is gets entered on the strength of an ad key alone,
# which is deliberate: adPlacements is never anything but YouTube's
# own ad list, so its presence is enough to call an object player data
alone = H.js(view, """JSON.stringify(JSON.parse(
    '{"title":"t","adPlacements":[1]}'))""")
check("...while an ad key by itself is enough to clean one out",
      "adPlacements" not in alone and '"t"' in alone, alone)
check("a parse that is not an object survives the hook",
      H.js(view, "JSON.parse('7') + 1") == 8)
check("...and so does a broken one, as the error it is",
      H.js(view, "(function () { try { JSON.parse('{'); return 'no throw'; }"
                 " catch (e) { return e.name; } })()") == "SyntaxError")


print("\n(3) a wall that reaches the screen is taken off it")
H.js(view, """(function () {
  var wall = document.createElement("ytd-enforcement-message-view-model");
  wall.id = "thewall";
  document.body.appendChild(wall);
  var back = document.createElement("tp-yt-iron-overlay-backdrop");
  back.id = "theback";
  document.body.appendChild(back);
})()""")
H.wait_for(lambda: H.js(view, "!document.getElementById('thewall')"), 4000)
check("the wall is gone", H.js(view, "!document.getElementById('thewall')"))
check("...and the grey over the page with it",
      H.js(view, "!document.getElementById('theback')"))


print("\n(4) what the engine can play is the engine's answer to give")
# The codec gate came out on 2026-11-04: it hid AV1 and VP8 from
# YouTube on a premise no machine here has ever shown, and measured
# false on two. A player that gets nothing at all is the wrong place
# to be taking choices away.
as_host("www.youtube.com")
check("MediaSource is not dressed up", native("MediaSource.isTypeSupported"))
check("...nor canPlayType",
      native("HTMLMediaElement.prototype.canPlayType"))
# the measurement that says it plainly: the page's own answer about
# AV1 and the engine's own answer have to agree now. They did not
# before -- that disagreement WAS the override.
ASK = ("(function () { var t = 'video/mp4; codecs=\"av01.0.08M.08\"';"
       " return String(MediaSource.isTypeSupported(t)); })()")
page_says = H.js(view, ASK, B.QWebEngineScript.ScriptWorldId.MainWorld.value)
engine_says = H.js(
    view, ASK, B.QWebEngineScript.ScriptWorldId.ApplicationWorld.value)
check("the page is told about AV1 exactly what the engine says",
      page_says == engine_says, (page_says, engine_says))

source = (HERE / "browser.py").read_text(encoding="utf-8")
yt = source[source.index("YOUTUBE_JS = r"):
            source.index("IMAGE_AT_POINT_JS")]
code = "\n".join(line for line in yt.splitlines()
                   if not line.strip().startswith("//"))
check("nothing in the script's own code names a codec any more",
      not any(word in code for word in
              ("av01", "isTypeSupported", "canPlayType")),
      [w for w in ("av01", "isTypeSupported", "canPlayType") if w in code])
check("...and it still says why it used to",
      "measured FALSE on two" in yt)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
