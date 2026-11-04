#!/usr/bin/env python3
"""What the graphics turned out to be, written down on an ordinary start.

The 2026-11-03 black player was hunted for a day with the wrong
instrument: `/proc/<pid>/environ` of the running browser, which is the
exec-time block and says what the session handed IN, never what this
file did with it. The names were already gone from the engine when the
player was black, and nobody could see that, because his browser's
stderr goes to /dev/null and nothing wrote anything down.

So the browser writes it down itself: the variables the engine was
handed, the flags Qt and Chromium added on top (`Vulkan` and
`--disable-features=AcceleratedVideoDecoder` on his machine are neither
of them ours), which Vulkan drivers are installed at all, and what the
engine's own GPU process says about itself through WebGL. He opens a
page the way he always does; the file is there to read.
"""
import json
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


scratch = Path(os.environ.get(
    "BROWSER_TEST_SCRATCH", "/tmp")) / ("gpurep-%d" % os.getpid())
scratch.mkdir(parents=True, exist_ok=True)


def fake_proc(where, procs):
    """A /proc of our own: {pid: (ppid, "cmdline with NULs")}."""
    for pid, (ppid, line) in procs.items():
        folder = where / str(pid)
        folder.mkdir(parents=True, exist_ok=True)
        # the comm field can hold spaces and brackets both, which is
        # the trap a naive split on whitespace walks into
        (folder / "stat").write_text(
            "%s (Qt Web Engine (gpu)) S %s 1 1 0 -1 0\n" % (pid, ppid))
        (folder / "cmdline").write_bytes(
            ("\0".join(line.split(" ")) + "\0").encode("utf-8"))
    (where / "self").mkdir(parents=True, exist_ok=True)   # not a number
    (where / "uptime").write_text("1 1")                  # not a folder
    return where


RENDERER = ("/usr/lib64/qt6/libexec/QtWebEngineProcess --type=renderer "
            "--enable-features=PlatformHEVCDecoderSupport,Vulkan "
            "--disable-features=AcceleratedVideoDecoder,WebUSB "
            "--widevine-path=HOME/.config/google-chrome/widevinecdm.so "
            "--lang=en")
proc = fake_proc(scratch / "proc", {
    4000: (1, "python3 browser.py"),                      # us
    4001: (4000, "QtWebEngineProcess --type=zygote"),     # our zygote
    4002: (4001, RENDERER.replace("HOME", str(Path.home()))),
    4003: (4000, "QtWebEngineProcess --type=utility --utility-sub-type=x"),
    4100: (1, "QtWebEngineProcess --type=renderer --application-name=other"),
    4101: (1, "some-other-program"),
})


print("\n(1) which engine processes are ours")
kids = B._engine_children(pid=4000, root=str(proc))
check("the zygote, the renderer under it and the utility are found",
      [(c["pid"], c["kind"]) for c in kids]
      == [(4001, "zygote"), (4002, "renderer"), (4003, "utility")],
      [(c["pid"], c["kind"]) for c in kids])
check("...and another program's engine process is not ours to report",
      all(c["pid"] != 4100 for c in kids), [c["pid"] for c in kids])
check("a process with no --type is not an engine process",
      all(c["pid"] not in (4000, 4101) for c in kids))
check("nothing of his login is written into the line",
      all(str(Path.home()) not in c["cmdline"] for c in kids)
      and any("~/.config/google-chrome" in c["cmdline"] for c in kids),
      [c["cmdline"][-60:] for c in kids])
check("a /proc that is not there at all is no processes, not a crash",
      B._engine_children(pid=4000, root=str(scratch / "nope")) == [])


print("\n(2) what the engine was really told")
feats = B._engine_features(kids)
check("the features it was handed are read off its own line",
      feats.get("enable-features") == "PlatformHEVCDecoderSupport,Vulkan",
      feats)
check("...and the ones it was told to leave off",
      feats.get("disable-features") == "AcceleratedVideoDecoder,WebUSB",
      feats)
# this is the whole point of reading the child instead of asking
# ourselves: `Vulkan` and that disable are Qt's and Chromium's, and
# browser.py sets neither of them anywhere.
source = (HERE / "browser.py").read_text(encoding="utf-8")
builds = [line for line in source.splitlines()
          if ("QTWEBENGINE_CHROMIUM_FLAGS" in line or "feats" in line
              or "env +=" in line or "parts.append" in line)]
check("and no line of this file that builds that command line asks for "
      "either of them",
      not any("Vulkan" in line or "AcceleratedVideoDecoder" in line
              for line in builds),
      [line.strip()[:60] for line in builds
       if "Vulkan" in line or "AcceleratedVideoDecoder" in line])
check("...so reading the child is the only way to know they are there",
      "_engine_features(children)" in source)
check("a run with no renderer yet says nothing rather than guessing",
      B._engine_features([k for k in kids if k["kind"] != "renderer"]) == {})


print("\n(3) his login stays out of it")
check("the home folder becomes a tilde",
      B._no_home(str(Path.home()) + "/x") == "~/x")
check("...and text without it is untouched",
      B._no_home("--use-gl=egl") == "--use-gl=egl")
check("...and something that is not text at all survives the trip",
      B._no_home(None) is None and B._no_home(7) == 7)


print("\n(4) the record itself")
where = scratch / "gpu-report.json"
os.environ["LIBVA_DRIVER_NAME"] = "nvidia"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--widevine-path=" + str(Path.home()) + "/cdm.so")
data = B.gpu_report(web={"webgl": {"card": "ANGLE (NVIDIA, Vulkan 1.3)"}},
                    path=str(where), root=str(proc))
os.environ.pop("LIBVA_DRIVER_NAME", None)
os.environ.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)
check("it is written where it was asked for", where.is_file())
on_disk = json.loads(where.read_text())
check("...and it is the same answer that came back", on_disk == data)
check("the variables the engine was handed are in it",
      on_disk["env"].get("LIBVA_DRIVER_NAME") == "nvidia",
      on_disk["env"])
check("...with his login out of them here as well",
      str(Path.home()) not in json.dumps(on_disk),
      [v for v in on_disk["env"].values() if str(Path.home()) in str(v)])
check("the toggle and the card he chose are in it",
      set(on_disk["config"]) == {"vaapi", "gpuCard", "gpuAsk", "gpuReset"},
      on_disk["config"])
check("this machine's cards are in it, with what drives a screen",
      isinstance(on_disk["cards"], list)
      and all({"maker", "slot", "drives"} <= set(c)
              for c in on_disk["cards"]), on_disk["cards"])
check("which Vulkan drivers are installed is in it",
      isinstance(on_disk["vulkanDrivers"], list),
      on_disk["vulkanDrivers"])
check("...which is why this box cannot show his fault: no real one here",
      all("nvidia" not in name for name in on_disk["vulkanDrivers"]),
      on_disk["vulkanDrivers"])
check("what the page answered is kept as the page said it",
      on_disk["web"]["webgl"]["card"] == "ANGLE (NVIDIA, Vulkan 1.3)")
check("a page that could not answer is not a missing record",
      "web" in B.gpu_report(web=None, path=str(where), root=str(proc)))
check("a place it cannot write is not a crash either",
      isinstance(B.gpu_report(path=str(scratch / "no" / "x" / "y.json"),
                              root=str(proc)), dict))
# it lives in his browser folder and nowhere else -- asked of the
# source, because the suite redirects every data file this module has
# to a scratch one (harness.boot), this one included: a test that
# wrote a record into his real profile would be the second thing this
# week to put our own leavings on his machine.
check("the record goes in his browser folder and nowhere else",
      'GPU_REPORT_FILE = BROWSER_HOME / "gpu-report.json"' in source)
check("...and the suite's copy of it is redirected like the rest",
      "GPU_REPORT_FILE" in (HERE / "tests" / "harness.py").read_text(
          encoding="utf-8")
      and B.GPU_REPORT_FILE.parent != B.BROWSER_HOME, B.GPU_REPORT_FILE)


print("\n(5) and the page is asked, once, without being disturbed")
app = H.app()
srv = H.Server({"/": "<html><body><p>hi</p></body></html>"})
win = B.Browser()
win.show()
H.load(win.current(), srv.url("/"))
H.spin(400)
answer = {}
win.current().page().runJavaScript(
    B.GPU_PROBE_JS,
    B.QWebEngineScript.ScriptWorldId.ApplicationWorld.value,
    lambda got: answer.update(got if isinstance(got, dict) else {"bad": got}))
H.wait_for(lambda: bool(answer), 8000)
check("the page answers, even where there is no card to answer about",
      bool(answer), answer)
check("...saying what it can draw with", "webgl" in answer, answer)
check("...and which codecs the engine admits to",
      isinstance(answer.get("codecs"), dict), answer.get("codecs"))
check("asking leaves nothing behind in the page",
      H.js(win.current(), "document.querySelectorAll('canvas').length") == 0)
check("...and nothing of it is visible to the page's own scripts",
      H.js(win.current(), "typeof window.__gpuProbe") == "undefined")
check("it is asked once per start, after the engine has settled",
      "QTimer.singleShot(9000, self._gpu_record)" in source)
record = source[source.index("def _gpu_record"):
                source.index("def _check_updates")]
check("...and nothing waits for the answer: it is handed to a callback",
      "runJavaScript(" in record and "done)" in record
      and ".exec(" not in record and "QEventLoop" not in record)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
