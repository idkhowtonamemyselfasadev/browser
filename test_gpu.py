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
check("...and takes the five it set off again",
      len(off) == 5 and "DRI_PRIME" in off, off)
check("...but leaves the VA-API driver the machine chose alone",
      "LIBVA_DRIVER_NAME" not in off, off)
keep = {"LIBVA_DRIVER_NAME": "nvidia", "DRI_PRIME": "pci-0000_01_00_0"}
B.gpu_apply("auto", cards, keep)
check("...so hardware decoding is not taken from a machine that had it",
      keep == {"LIBVA_DRIVER_NAME": "nvidia"}, keep)
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
check("...and going back to automatic clears what it set",
      env == {"PATH": "/x", "LIBVA_DRIVER_NAME": "iHD"}, env)


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


print("\n(4b) and it is off until he asks for it")
cfg = {"gpuCard": "0000:01:00.0", "gpuAsk": True}
B._migrate_gpu_choice(cfg)
check("a card chosen before this update is not applied any more",
      cfg["gpuCard"] == "auto" and cfg["gpuAsk"] is False, cfg)
check("...but it is kept, so turning it back on costs one click",
      cfg.get("gpuCardWas") == "0000:01:00.0", cfg)
again = dict(cfg)
again["gpuCard"] = "0000:00:02.0"
B._migrate_gpu_choice(again)
check("...and a choice he makes afterwards is left alone",
      again["gpuCard"] == "0000:00:02.0", again)
fresh = {}
B._migrate_gpu_choice(fresh)
check("a fresh config starts with the environment untouched",
      fresh["gpuCard"] == "auto" and fresh["gpuAsk"] is False, fresh)

asked["n"] = 0
try:
    os.environ["BROWSER_DRM_ROOT"] = str(two)
    os.environ.pop("BROWSER_NO_GPU_ASK", None)
    B.CONFIG_FILE.write_text(json.dumps(
        {"translateLang": "en", "gpuReset": 1, "gpuCard": "auto",
         "gpuAsk": False}))
    real_ask2, B._gpu_ask_window = B._gpu_ask_window, never
    B._gpu_startup()
    check("two cards and the chooser off: no window, no variables",
          asked["n"] == 0 and not os.environ.get("DRI_PRIME"),
          os.environ.get("DRI_PRIME"))
finally:
    B._gpu_ask_window = real_ask2
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

print("\n(7) the same question on Windows, which answers it itself")
# There is no sysfs there and no DRI_PRIME either: the cards are what
# Windows lists, and WHICH card a program uses is kept in Windows' own
# Graphics settings, per executable. So this edition lists them and
# says where the choice lives, and sets nothing.
SAMPLE = """
NVIDIA GeForce RTX 5080|PCI\\VEN_10DE&DEV_2704&SUBSYS_123410DE&REV_A1\\4&2b8|0
Intel(R) UHD Graphics 770|PCI\\VEN_8086&DEV_4680&SUBSYS_00000000&REV_0C\\3&11|2560
Microsoft Basic Display Adapter||
rubbish
"""
cards = B._gpu_windows_cards(SAMPLE)
check("both real adapters are read, and the nameless one is not",
      len(cards) == 2, [c.get("name") for c in cards])
names = [c["name"] for c in cards]
check("they keep the names Windows gives them",
      names == ["NVIDIA GeForce RTX 5080", "Intel(R) UHD Graphics 770"],
      names)
check("the maker and the device come out of the device id",
      [(c["vendor"], c["device"], c["maker"]) for c in cards]
      == [("0x10de", "0x2704", "NVIDIA"), ("0x8086", "0x4680", "Intel")],
      [(c["vendor"], c["device"], c["maker"]) for c in cards])
check("the card that is driving a screen is marked, and only it",
      [c["boot"] for c in cards] == [False, True],
      [c["boot"] for c in cards])
check("each card's identity is the device id, which survives a restart",
      all(c["slot"] == c["card"] and "VEN_" in c["slot"] for c in cards),
      [c["slot"] for c in cards])
check("two cards never answer to one name",
      len({c["slot"] for c in cards}) == 2)
check("no output at all is no cards, not a crash",
      B._gpu_windows_cards("") == [])

real_sys = B.sys


class FakeSys:
    pass


fake = FakeSys()
fake.platform = "win32"
fake.executable = real_sys.executable
fake.argv = list(real_sys.argv)
try:
    B.sys = fake
    # the Linux reader must not be reached: it would answer with this
    # box's own Intel card on a machine that has no /sys at all
    looked = []
    real_list = os.listdir
    os.listdir = lambda path: (looked.append(path), real_list(path))[1]
    try:
        win_cards = B.gpu_cards()
    finally:
        os.listdir = real_list
    check("gpu_cards goes to Windows for its answer there",
          not any("drm" in str(path) for path in looked), looked)
    check("...and with no powershell to ask, that is no cards",
          win_cards == [], win_cards)

    on, off = B.gpu_env("PCI\\VEN_10DE&DEV_2704", cards)
    check("a choice sets nothing in the environment on Windows",
          (on, off) == ({}, []), (on, off))
    check("...DRI_PRIME above all, which means nothing there",
          "DRI_PRIME" not in on)
    env = {"DRI_PRIME": "pci-0000_01_00_0", "PATH": "/x"}
    B.gpu_apply("PCI\\VEN_10DE&DEV_2704", cards, env)
    check("and an environment it was handed is left exactly as it was",
          env == {"DRI_PRIME": "pci-0000_01_00_0", "PATH": "/x"}, env)
finally:
    B.sys = real_sys

src = (HERE / "browser.py").read_text(encoding="utf-8")
check("no window is ever put up on Windows",
      'if sys.platform == "win32":\n        # there is nothing this window'
      in src)
check("Settings is told whether choosing is on offer at all",
      '"gpuChoose": sys.platform != "win32"' in src)
page = (HERE / "settings.html").read_text(encoding="utf-8")
check("...and the page says where the choice lives instead",
      'id="gpuwindows"' in page and "s.gpuChoose !== false" in page)
check("the ask-at-every-start row is not offered there",
      'askrow.closest(".wrow").hidden = !choose' in page)
for key in ("gpuWindows",):
    check("the word %s is in both languages" % key,
          B.UI_STRINGS["en"].get(key) and B.UI_STRINGS["de"].get(key)
          and B.UI_STRINGS["en"][key] != B.UI_STRINGS["de"][key])

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
