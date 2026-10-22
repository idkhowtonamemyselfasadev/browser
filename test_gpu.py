#!/usr/bin/env python3
"""Which graphics card draws the pages, asked before the browser starts.

His machine has two: an RTX 5080 and the processor's own Intel
graphics. Which one the engine ends up on is decided by environment
variables read when the GPU process starts, so the question has to be
asked and answered before any of the browser exists -- a plain Qt
window, no engine behind it, and the answer carried into a fresh start
of the program.

This box has one Intel card and no second GPU, so what can be measured
here is the reading, the listing, the environment that comes out of a
choice, the window itself and the path that does not ask. That the
5080 really takes over is the one thing only his machine can say.
"""
import json
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
os.environ["BROWSER_NO_GPU_ASK"] = "1"      # never ask inside a test
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


def fake_machine(where, cards):
    """A /sys/class/drm of our own, so two cards can be measured on a
    machine that has one."""
    for name, (vendor, device, boot, slot) in cards.items():
        folder = where / name / "device"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "vendor").write_text(vendor)
        (folder / "device").write_text(device)
        (folder / "boot_vga").write_text("1" if boot else "0")
        (folder / "uevent").write_text("PCI_SLOT_NAME=%s\n" % slot)
    # an output is not a card, and must not be counted as one
    (where / "card1-DP-1").mkdir(parents=True, exist_ok=True)
    return where


scratch = Path(os.environ.get(
    "BROWSER_TEST_SCRATCH", "/tmp")) / ("gputest-%d" % os.getpid())
two = fake_machine(scratch / "drm-two", {
    "card0": ("0x10de", "0x2c02", False, "0000:01:00.0"),
    "card1": ("0x8086", "0x5912", True, "0000:00:02.0"),
})
one = fake_machine(scratch / "drm-one", {
    "card0": ("0x8086", "0x5912", True, "0000:00:02.0"),
})

app = H.app()


print("\n(1) the cards this machine has")
cards = B.gpu_cards(str(two))
check("both are found", len(cards) == 2, [c["slot"] for c in cards])
check("...and an output is not one of them",
      all(c["card"].startswith("card") and "-" not in c["card"]
          for c in cards), [c["card"] for c in cards])
check("the discrete one is offered first",
      cards[0]["vendor"] == "0x10de" and cards[1]["vendor"] == "0x8086",
      [c["maker"] for c in cards])
check("...and the one the system starts on says so",
      cards[1]["boot"] is True and cards[0]["boot"] is False)
check("each knows its PCI slot",
      [c["slot"] for c in cards] == ["0000:01:00.0", "0000:00:02.0"],
      [c["slot"] for c in cards])
check("each has a name to show him",
      all(c["name"] and c["maker"] in c["name"] for c in cards),
      [c["name"] for c in cards])
check("and this machine's own card is read the same way",
      len(B.gpu_cards()) >= 1 and B.gpu_cards()[0]["slot"].startswith("0000:"),
      [c["name"] for c in B.gpu_cards()])


print("\n(2) what choosing one does to the environment")
on, off = B.gpu_env(cards[0]["slot"], cards)
check("the NVIDIA card asks for PRIME offload",
      on.get("__NV_PRIME_RENDER_OFFLOAD") == "1"
      and on.get("__GLX_VENDOR_LIBRARY_NAME") == "nvidia"
      and on.get("__VK_LAYER_NV_optimus") == "NVIDIA_only", on)
check("...named by its slot", on.get("DRI_PRIME") == "pci-0000_01_00_0", on)
on, off = B.gpu_env(cards[1]["slot"], cards)
check("the Intel card asks for its own and nothing of NVIDIA's",
      on.get("DRI_PRIME") == "pci-0000_00_02_0"
      and on.get("MESA_VK_DEVICE_SELECT") == "8086:5912"
      and "__NV_PRIME_RENDER_OFFLOAD" not in on, on)
check("...and says the NVIDIA ones must come off",
      "__NV_PRIME_RENDER_OFFLOAD" in off, off)
on, off = B.gpu_env("auto", cards)
check("\"let the system decide\" sets nothing", on == {}, on)
check("...and takes every one of them off, the decoder included",
      len(off) == 6 and "LIBVA_DRIVER_NAME" in off, off)
# the decoder and the card that composites must be the same one: his
# own line further up browser.py forces LIBVA_DRIVER_NAME=nvidia
# whenever an NVIDIA driver is installed, and decoding on one card
# while another draws is a black video with the sound still playing
on, _off = B.gpu_env(cards[0]["slot"], cards)
check("choosing NVIDIA decodes on NVIDIA",
      on.get("LIBVA_DRIVER_NAME") == "nvidia", on)
on, _off = B.gpu_env(cards[1]["slot"], cards)
check("choosing Intel moves the decoder to Intel as well",
      on.get("LIBVA_DRIVER_NAME") == "iHD", on)
env = {"LIBVA_DRIVER_NAME": "nvidia"}
B.gpu_apply(cards[1]["slot"], cards, env)
check("...so a machine told \"nvidia\" earlier is corrected",
      env.get("LIBVA_DRIVER_NAME") == "iHD", env)

check("a slot that is not here any more decides nothing",
      B.gpu_env("0000:09:00.0", cards)[0] == {})

env = {"PATH": "/x", "DRI_PRIME": "stale",
       "__GLX_VENDOR_LIBRARY_NAME": "nvidia"}
B.gpu_apply(cards[1]["slot"], cards, env)
check("applying one card clears the other's leftovers",
      env.get("DRI_PRIME") == "pci-0000_00_02_0"
      and "__GLX_VENDOR_LIBRARY_NAME" not in env, env)
B.gpu_apply("auto", cards, env)
check("...and going back to automatic clears all of it",
      env == {"PATH": "/x"}, env)


print("\n(3) the window that asks")
box = B.gpu_dialog(cards, "", "en")
rows = [b for b in box._group.buttons()]
check("every card is on it, and \"let the system decide\" under them",
      len(rows) == 3 and rows[-1]._slot == "auto",
      [b.text() for b in rows])
check("the card the system starts on is marked",
      "starts on" in rows[1].text(), rows[1].text())
check("something is always chosen, so Start cannot mean nothing",
      any(b.isChecked() for b in rows))
check("it does not remember unless he says so",
      box._remember.isChecked() is False)
rows[0].setChecked(True)
check("pressing a card and reading it back gives that card",
      box._group.checkedButton()._slot == "0000:01:00.0")
again = B.gpu_dialog(cards, "0000:00:02.0", "en")
check("a card already chosen comes up chosen",
      again._group.checkedButton()._slot == "0000:00:02.0")
german = B.gpu_dialog(cards, "", "de")
check("and it speaks German when he does",
      "Grafikkarte" in german.windowTitle(), german.windowTitle())
en, de = B._GPU_WORDS["en"], B._GPU_WORDS["de"]
check("both languages have every word of it",
      set(en) == set(de) and all(en[k] != de[k] for k in en),
      [k for k in en if en[k] == de[k]])


print("\n(4) when it does not ask")
asked = {"n": 0}


def never(*a, **k):
    asked["n"] += 1
    return None


real_ask, real_exec = B._gpu_ask_window, os.execve
B._gpu_ask_window = never
os.execve = lambda *a, **k: (_ for _ in ()).throw(
    AssertionError("restarted when it should not"))
try:
    os.environ["BROWSER_DRM_ROOT"] = str(one)
    os.environ.pop("BROWSER_NO_GPU_ASK", None)
    B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
    B._gpu_startup()
    check("one card is not a question", asked["n"] == 0)

    os.environ["BROWSER_DRM_ROOT"] = str(two)
    B.CONFIG_FILE.write_text(json.dumps(
        {"translateLang": "en", "gpuAsk": False,
         "gpuCard": "0000:01:00.0"}))
    for key in ("DRI_PRIME", "__NV_PRIME_RENDER_OFFLOAD"):
        os.environ.pop(key, None)
    B._gpu_startup()
    check("an answer he has given is used without asking again",
          asked["n"] == 0
          and os.environ.get("DRI_PRIME") == "pci-0000_01_00_0",
          os.environ.get("DRI_PRIME"))
    check("...and the card's own switches are set with it",
          os.environ.get("__NV_PRIME_RENDER_OFFLOAD") == "1")

    os.environ[B._GPU_MARK] = "1"
    os.environ["BROWSER_GPU_CARD"] = "0000:00:02.0"
    B.CONFIG_FILE.write_text(json.dumps(
        {"translateLang": "en", "gpuAsk": True}))
    B._gpu_startup()
    check("the run started by an answer does not ask it again",
          asked["n"] == 0
          and os.environ.get("DRI_PRIME") == "pci-0000_00_02_0",
          os.environ.get("DRI_PRIME"))
finally:
    B._gpu_ask_window = real_ask
    os.execve = real_exec
    os.environ.pop(B._GPU_MARK, None)
    os.environ.pop("BROWSER_DRM_ROOT", None)
    os.environ["BROWSER_NO_GPU_ASK"] = "1"


print("\n(5) it is the browser that asks, not every launch")
source = (HERE / "browser.py").read_text(encoding="utf-8")
at_import = source.index("if not os.environ.get(\"BROWSER_NO_GPU_ASK\"):")
check("a saved answer is applied before Qt is imported",
      at_import < source.index("from PyQt6.QtCore import"),
      "import at %d" % at_import)
check("...and only the answer, never the question",
      "_gpu_quiet()" in source[at_import:at_import + 200])
asks_at = source.index("_gpu_startup(lambda")
check("the question waits until this process is the browser",
      source.index("server.listen(SINGLE_INSTANCE_SOCKET)") < asks_at,
      "asked at %d" % asks_at)
check("...and before the first window, so no profile exists yet",
      asks_at < source.index("win = Browser(initial_url=None if bg_launch"))
check("the socket is given up before it restarts itself",
      "release()" in source and "QLocalServer.removeServer" in
      source[asks_at:asks_at + 300])


print("\n(6) and Settings can change it afterwards")
page = (HERE / "settings.html").read_text(encoding="utf-8")
check("there is a row for the card", 'id="gpucards"' in page)
check("...and a switch for being asked every start",
      'id="gpuask"' in page and 'bindSwitch("gpuask", "gpuAsk")' in page)
check("the page is told what the cards are",
      '"gpuCards"' in (HERE / "browser.py").read_text(encoding="utf-8"))
for key in ("gpuPickName", "gpuPickHint", "gpuAskName", "gpuAskHint",
            "gpuAuto", "gpuBoot", "gpuRestart", "gpuNone"):
    check("the word %s is in both languages" % key,
          B.UI_STRINGS["en"].get(key) and B.UI_STRINGS["de"].get(key)
          and B.UI_STRINGS["en"][key] != B.UI_STRINGS["de"][key])

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
