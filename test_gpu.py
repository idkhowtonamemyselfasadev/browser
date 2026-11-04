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


def fake_machine(where, cards, outputs=None):
    """A /sys/class/drm of our own, so two cards can be measured on a
    machine that has one.

    `outputs` is {"card2-DP-4": "connected", ...}: which sockets have a
    cable in them, which is what says a card is driving a screen."""
    for name, (vendor, device, boot, slot) in cards.items():
        folder = where / name / "device"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "vendor").write_text(vendor)
        (folder / "device").write_text(device)
        (folder / "boot_vga").write_text("1" if boot else "0")
        (folder / "uevent").write_text("PCI_SLOT_NAME=%s\n" % slot)
    # an output is not a card, and must not be counted as one
    (where / "card1-DP-1").mkdir(parents=True, exist_ok=True)
    for out, state in (outputs or {}).items():
        folder = where / out
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "status").write_text(state + "\n")
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
# his own machine, as /sys/class/drm really reports it: the Intel has
# five sockets and nothing in any of them, and all three monitors hang
# off the discrete card -- which is the shape the chooser was never
# written for (see (2b))
his = fake_machine(scratch / "drm-his", {
    "card1": ("0x8086", "0x7d67", False, "0000:00:02.0"),
    "card2": ("0x10de", "0x2c02", True, "0000:02:00.0"),
}, {"card1-DP-1": "disconnected", "card1-DP-2": "disconnected",
    "card1-HDMI-A-1": "disconnected",
    # a writeback connector is memory, not a monitor, and some drivers
    # call it connected with nothing attached: it must not make the
    # Intel card look like it is driving a screen
    "card1-Writeback-1": "connected",
    "card2-DP-4": "connected", "card2-DP-5": "connected",
    "card2-DP-6": "connected", "card2-HDMI-A-3": "disconnected"})
# a VA-API driver directory of our own. LIBVA_DRIVERS_PATH replaces
# libva's search path rather than adding to it, so this decides what
# _va_driver_here can find whatever is installed on the box running
# the suite -- and the answer is the same on every box.
vadir = scratch / "dri"
vadir.mkdir(parents=True, exist_ok=True)
for _name in ("nvidia", "iHD"):
    (vadir / (_name + "_drv_video.so")).write_text("")
os.environ["LIBVA_DRIVERS_PATH"] = str(vadir)

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
B._GPU_PUT.clear()
B._GPU_PUT.add("DRI_PRIME")         # as if a pick in this run set it
B.gpu_apply("auto", cards, keep)
check("...so hardware decoding is not taken from a machine that had it",
      keep == {"LIBVA_DRIVER_NAME": "nvidia"}, keep)
# the decoder and the card that composites must be the same one:
# decoding on one card while another draws is a black video with the
# sound still playing. That pairing only arises where there is going
# to be hardware decoding at all, which is the "vaapi" toggle.
on, _off = B.gpu_env(cards[0]["slot"], cards, vaapi=True)
check("choosing NVIDIA decodes on NVIDIA",
      on.get("LIBVA_DRIVER_NAME") == "nvidia", on)
check("...through the backend that driver needs",
      on.get("NVD_BACKEND") == "direct", on)
on, _off = B.gpu_env(cards[1]["slot"], cards, vaapi=True)
check("choosing Intel moves the decoder to Intel as well",
      on.get("LIBVA_DRIVER_NAME") == "iHD", on)
check("...and leaves NVIDIA's backend behind",
      "NVD_BACKEND" not in on and "NVD_BACKEND" in _off, (on, _off))
env = {"LIBVA_DRIVER_NAME": "nvidia"}
B.gpu_apply(cards[1]["slot"], cards, env, vaapi=True)
check("...so a machine told \"nvidia\" earlier is corrected",
      env.get("LIBVA_DRIVER_NAME") == "iHD", env)

# ...and with the toggle off nothing decodes through VA-API, so naming
# a driver buys no speed and risks exactly the black frame above. This
# was set on every machine with an NVIDIA module loaded regardless of
# the toggle, which is the whole of the 2026-11-03 black-player report.
on, off = B.gpu_env(cards[0]["slot"], cards, vaapi=False)
check("with hardware decode off, no VA-API driver is named",
      "LIBVA_DRIVER_NAME" not in on and "NVD_BACKEND" not in on, on)
check("...and a stale one is taken off instead",
      "LIBVA_DRIVER_NAME" in off and "NVD_BACKEND" in off, off)
check("a driver that is not installed is never named",
      B._va_driver_here("iHD") and not B._va_driver_here("radeonsi")
      and not B._va_driver_here(""),
      [B._va_driver_here(n) for n in ("iHD", "radeonsi", "")])
# the same question the import-time block now asks, asked here: a name
# with no .so behind it leaves libva unable to initialise at all --
# worse than the driver it would have found by itself.
nocard = [dict(cards[0], vendor="0x1002", device="0x7480")]
on, _off = B.gpu_env(cards[0]["slot"], nocard, vaapi=True)
check("...not even the one the card would want",
      "LIBVA_DRIVER_NAME" not in on, on)


# and the same three conditions as the shipped line, which this box
# cannot reach on its own: there is no NVIDIA module in it.
check("the driver is named only with the module, the toggle AND the file",
      [B._nvidia_va_wanted(nvidia=n, vaapi=v)
       for n in (True, False) for v in (True, False)]
      == [True, False, False, False],
      [B._nvidia_va_wanted(nvidia=n, vaapi=v)
       for n in (True, False) for v in (True, False)])
os.environ["LIBVA_DRIVERS_PATH"] = str(scratch / "empty-dri")
check("...and not at all on a machine without libva-nvidia-driver",
      B._nvidia_va_wanted(nvidia=True, vaapi=True) is False)
os.environ["LIBVA_DRIVERS_PATH"] = str(vadir)


print("\n(2c) a driver name the session handed us, with decode off")
# The gate above only decides whether to NAME the driver. A desktop
# session can name it for every program it starts, and his does:
# ~/.config/hypr/configs/ENVariables.conf has `env =
# LIBVA_DRIVER_NAME,nvidia` and `env = NVD_BACKEND,direct`, so the
# engine inherited the name before this file ran and 8d9734c's gate
# never touched it. These run the shipped lines themselves, with an os
# of their own, the way test_winbranch runs the Windows ones.
_src = (HERE / "browser.py").read_text(encoding="utf-8")
# anchored on the comment, not on the guard's own text: a slice keyed
# to `if sys.platform not in (...)` cannot be mutated at all -- change
# the guard and the suite dies looking for it instead of going red,
# which is a guard that proves nothing. Rewrite the comment and this
# raises ValueError, loudly, which is the failure we want.
_from = _src.index("# ...and only where libva exists at all.")
_block = _src[_from:_src.index("# Widevine:", _from)]
check("the names are settled before Qt is imported at all",
      _from < _src.index("from PyQt6.QtCore import"), _from)


class FakeOS:
    """os, as far as those lines reach into it."""

    def __init__(self, env):
        self.environ = env


class FakeSys:
    """...and sys, which is only asked which platform this is."""

    def __init__(self, platform):
        self.platform = platform


def shipped(env, module, toggle, platform="linux"):
    """The real block, with the machine and the toggle as answers."""
    ns = {"os": FakeOS(env), "sys": FakeSys(platform),
          "_nvidia_va_wanted": lambda: bool(module and toggle),
          "_vaapi_wanted": lambda: bool(toggle)}
    exec(compile(_block, "browser.py (the block)", "exec"), ns)
    return env


named = {"LIBVA_DRIVER_NAME": "nvidia", "NVD_BACKEND": "direct"}
check("decode off: a name the session set is taken off again",
      shipped(dict(named), module=True, toggle=False) == {})
check("...on a machine with no NVIDIA in it as well",
      shipped(dict(named), module=False, toggle=False) == {})
check("...and an environment that never had one is not harmed",
      shipped({"PATH": "/x"}, module=True, toggle=False) == {"PATH": "/x"})
check("decode on, NVIDIA: the name is set, as it always was",
      shipped({}, module=True, toggle=True) == named)
check("...and one already there is left as it was found",
      shipped({"LIBVA_DRIVER_NAME": "iHD"}, module=True, toggle=True)
      == {"LIBVA_DRIVER_NAME": "iHD", "NVD_BACKEND": "direct"})
# the case that says this is not a flat line-drop: hardware decode is
# ON and this is not NVIDIA, so the name the machine chose for its own
# card (iHD on his Intel, radeonsi on an AMD) is the right one and
# nothing here knows better than it does.
check("decode on, no NVIDIA module: the machine's own name stands",
      shipped({"LIBVA_DRIVER_NAME": "iHD"}, module=False, toggle=True)
      == {"LIBVA_DRIVER_NAME": "iHD"})

# ...and nowhere that has no libva to name a driver for. VA-API is a
# Linux and BSD interface; on macOS both names are forbidden outright
# (MAC_FORBIDDEN_ENV, linted by that edition's own suite, which this
# tree cannot run), and on Windows they mean nothing. Neither setting
# NOR clearing them is this file's business there.
for platform in ("darwin", "win32"):
    check("%s is left exactly as it was found, decode off" % platform,
          shipped(dict(named), module=True, toggle=False,
                  platform=platform) == named)
    check("...and %s with decode on" % platform,
          shipped({"LIBVA_DRIVER_NAME": "whatever"}, module=True,
                  toggle=True, platform=platform)
          == {"LIBVA_DRIVER_NAME": "whatever"})
check("...while this platform is the one that answers",
      shipped({}, module=True, toggle=True, platform="linux") == named
      and shipped({}, module=True, toggle=True, platform="freebsd12")
      == named)


print("\n(2b) and nothing is offloaded to the card that already draws")
hiscards = B.gpu_cards(str(his))
check("which outputs have a cable in them is read, not thrown away",
      [(c["maker"], c["outputs"], c["drives"]) for c in hiscards]
      == [("Intel", 0, False), ("NVIDIA", 3, True)],
      [(c["maker"], c["outputs"], c["drives"]) for c in hiscards])
check("...and the card with nothing plugged in is offered first",
      hiscards[0]["maker"] == "Intel" and not hiscards[0]["drives"],
      [c["maker"] for c in hiscards])
on, off = B.gpu_env("0000:02:00.0", hiscards, vaapi=False)
check("picking the card the monitors are on asks for no offload",
      on == {}, on)
check("...and clears every variable it could have set",
      all(k in off for k in ("DRI_PRIME", "__NV_PRIME_RENDER_OFFLOAD",
                             "__GLX_VENDOR_LIBRARY_NAME",
                             "__VK_LAYER_NV_optimus", "LIBVA_DRIVER_NAME",
                             "NVD_BACKEND")), off)
on, _off = B.gpu_env("0000:02:00.0", hiscards, vaapi=True)
check("...but the decoder still goes with it when he asked for one",
      on == {"LIBVA_DRIVER_NAME": "nvidia", "NVD_BACKEND": "direct"}, on)
on, _off = B.gpu_env("0000:00:02.0", hiscards, vaapi=False)
check("the card with nothing plugged into it is still a real offload",
      on.get("DRI_PRIME") == "pci-0000_00_02_0"
      and on.get("MESA_VK_DEVICE_SELECT") == "8086:7d67", on)
# ...and a pick that sets nothing must not become a pick that only
# DELETES. Everything in the environment at a fresh start came from the
# desktop session -- his Hyprland names a GL vendor and a VA-API driver
# for every program it starts, and these variables never outlive a
# process, so none of it can be a leftover of ours. Measured on his
# machine on 2026-11-04: every engine process his browser had running
# was missing all three, and this browser was the only program on that
# desktop whose graphics were set up differently from the rest of it.
session = {"PATH": "/x", "LIBVA_DRIVER_NAME": "nvidia",
           "NVD_BACKEND": "direct", "__GLX_VENDOR_LIBRARY_NAME": "nvidia"}
env = dict(session)
B._GPU_PUT.clear()
B.gpu_apply("0000:02:00.0", hiscards, env, vaapi=False)
check("his pick sets nothing, so it takes nothing away either",
      env == session, env)
# The two VA-API names in there ARE wrong for a machine with hardware
# decode off -- and taking them off is the toggle's own business, done
# by the line at the top of browser.py that owns that question. This
# one owns which card draws, and deletes only what it set itself.
env = dict(session, DRI_PRIME="pci-0000_00_02_0",
           MESA_VK_DEVICE_SELECT="8086:7d67")
B._GPU_PUT.clear()
B._GPU_PUT.update({"DRI_PRIME", "MESA_VK_DEVICE_SELECT"})
B.gpu_apply("0000:02:00.0", hiscards, env, vaapi=False)
check("...but a card it offloaded to earlier in this run is undone",
      env == session, env)
# the same thing with nothing told to it: two picks through the real
# function, which has to remember for itself what the first one set
B._GPU_PUT.clear()
env = {"PATH": "/x"}
B.gpu_apply(cards[0]["slot"], cards, env, vaapi=False)
B.gpu_apply("auto", cards, env, vaapi=False)
check("two picks in one run, and the second undoes the first alone",
      env == {"PATH": "/x"}, env)

check("a slot that is not here any more decides nothing",
      B.gpu_env("0000:09:00.0", cards)[0] == {})

env = {"PATH": "/x", "DRI_PRIME": "stale",
       "__GLX_VENDOR_LIBRARY_NAME": "nvidia"}
B._GPU_PUT.clear()
B._GPU_PUT.update({"DRI_PRIME", "__GLX_VENDOR_LIBRARY_NAME"})
B.gpu_apply(cards[1]["slot"], cards, env, vaapi=True)
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
check("...and the row says which card the screens are on",
      "card.drives" in page and "gpuDrives" in page)
for key in ("gpuPickName", "gpuPickHint", "gpuAskName", "gpuAskHint",
            "gpuAuto", "gpuBoot", "gpuDrives", "gpuRestart", "gpuNone"):
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
      '"gpuChoose": sys.platform not in ("win32", "darwin")' in src)
check("...and, separately, whether there is a system page to open",
      '"gpuWindowsPage": sys.platform == "win32"' in src)

# One boolean used to answer both of those. "You cannot pick a card
# here" is true on Windows AND macOS; "there is a Graphics page to
# open" is true only on Windows. Sharing one flag showed macOS a
# Windows instruction and a button whose handler returns False on
# sight, and hid the macOS text that was already written.
#
# The rule, as a table, and the part that matters: the two platforms
# that were already right have to come out EXACTLY as they did before,
# or the fix moved something it was not aiming at.
def rule(platform):
    return (platform not in ("win32", "darwin"), platform == "win32")


def rule_before(platform):
    return (platform != "win32", platform == "win32")


for platform, want in (("linux", (True, False)),
                       ("win32", (False, True)),
                       ("darwin", (False, False))):
    check("%-7s -> picker=%-5s windows page=%s"
          % (platform, want[0], want[1]), rule(platform) == want,
          rule(platform))
for platform in ("linux", "win32"):
    check("...and %s is what it always was" % platform,
          rule(platform) == rule_before(platform),
          (rule(platform), rule_before(platform)))
check("...while darwin is the one that moved",
      rule("darwin") != rule_before("darwin"),
      (rule("darwin"), rule_before("darwin")))
check("exactly one of the three notes shows on each platform",
      all(sum((picker, winpage, not picker and not winpage)) == 1
          for picker, winpage in (rule(p) for p in
                                  ("linux", "win32", "darwin"))))
page = (HERE / "settings.html").read_text(encoding="utf-8")
check("...and the page says where the choice lives instead",
      'id="gpuwindows"' in page and "s.gpuChoose !== false" in page)
check("the ask-at-every-start row is not offered there",
      'askrow.closest(".wrow").hidden = !choose' in page)
for key in ("gpuWindows",):
    check("the word %s is in both languages" % key,
          B.UI_STRINGS["en"].get(key) and B.UI_STRINGS["de"].get(key)
          and B.UI_STRINGS["en"][key] != B.UI_STRINGS["de"][key])

check("...and a button that takes him to where it is made",
      'id="gpuopenwin"' in page
      and "bridge.openWindowsGraphics" in page
      and 'open.hidden = !winpage' in page)
check("...which macOS is not offered, because it has nowhere to go",
      'id="gpumac"' in page and 'mac.hidden = choose || winpage' in page)
check("macOS gets its own sentence, in both languages",
      B.UI_STRINGS["en"].get("gpuMac")
      and B.UI_STRINGS["de"].get("gpuMac")
      and B.UI_STRINGS["en"]["gpuMac"] != B.UI_STRINGS["de"]["gpuMac"])
check("the slot behind it exists and is a slot",
      "def openWindowsGraphics(self)" in src
      and "@pyqtSlot(result=bool)\n    def openWindowsGraphics" in src)
check("...and it does nothing at all on this machine, rather than "
      "handing an unknown address to the desktop",
      B.Bridge.openWindowsGraphics(object()) is False)
check("it opens the shell's own address for that page",
      'os.startfile("ms-settings:display-graphics")' in src)
for key in ("gpuOpenWindows",):
    check("the word %s is in both languages" % key,
          B.UI_STRINGS["en"].get(key) and B.UI_STRINGS["de"].get(key)
          and B.UI_STRINGS["en"][key] != B.UI_STRINGS["de"][key])

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
