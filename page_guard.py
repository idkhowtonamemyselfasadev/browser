"""What a page is allowed to do in its own window.

A sibling module like theme_web.py, capture.py and privacy.py, loaded
the same safe way: without this file the browser starts and the guards
are simply not there.

privacy.py is about the network — what a page may ask for. This file is
about the page itself: what its own scripts can read about this machine,
what they may take out of the clipboard, whether they may hold the
window with a "Leave site?" box, whether a consent banner gets clicked
away. All of it happens inside the page, in the page's own world, which
is the one place a Python request interceptor is not needed -- and this
PyQt build cannot have one of those (see privacy.check_request).

Everything here is off until he switches it on, and every guard can be
switched off for one site: a bank that needs WebGL and a call site that
needs WebRTC are both more important than a blanket rule.
"""

import json
import re

GUARD_SCRIPT_NAME = "page-guard"

#: every guard, with its config key and whether a site can be excused
#: from it. The order is the order they are applied in the page.
GUARDS = (
    "fingerprint",     # what the machine looks like to a script
    "clipboardRead",   # reading the clipboard
    "copyGuard",       # adding to what you copy
    "leaveTrap",       # the "Leave site?" box
    "gpc",             # navigator.globalPrivacyControl
    "noFrames",        # frames from other domains
    "localFonts",      # the site's web fonts
    "wsLog",           # a note of the WebSocket connections it opens
    "noWebRTC",        # RTCPeerConnection at all
    "banners",         # consent banners, answered with "reject"
    "popups",          # windows a script opens with nobody asking
    "mediaLog",        # a note of the microphone, camera or screen in use
)

#: the words a "reject everything" button carries, in the two languages
#: the browser speaks. Matched on the button's own text, lower-cased,
#: and only inside something that looks like a consent dialog.
REJECT_WORDS = (
    "reject all", "reject", "decline", "only necessary",
    "necessary only", "essential only", "continue without agreeing",
    "alle ablehnen", "ablehnen", "nur notwendige",
    "nur erforderliche", "weiter ohne einwilligung", "nicht zustimmen",
    "ohne einwilligung fortfahren",
)

#: what a consent dialog's own container tends to be called. Without
#: this the "reject" matcher would click a "decline" button in an
#: ordinary form, which is somebody's actual answer to something.
BANNER_MARKS = (
    "consent", "cookie", "cookies", "gdpr", "privacy-banner",
    "cmp", "didomi", "onetrust", "usercentrics", "sp_message",
    "qc-cmp", "borlabs", "klaro", "cookiebot", "trustarc",
)

#: the APIs a site can be refused one at a time, and what to take out
#: of the page for each. A name that is not here is ignored rather than
#: trusted: this table is the whole of what "block an API" can mean.
API_TARGETS = {
    "webgl": ["WebGLRenderingContext", "WebGL2RenderingContext"],
    "wasm": ["WebAssembly"],
    "webusb": ["USB", "USBDevice"],
    "bluetooth": ["Bluetooth"],
    "serial": ["Serial"],
    "hid": ["HID"],
    "midi": ["MIDIAccess"],
    "sensors": ["Accelerometer", "Gyroscope", "Magnetometer",
                "AbsoluteOrientationSensor", "LinearAccelerationSensor"],
    "idle": ["IdleDetector"],
    "nfc": ["NDEFReader"],
    "battery": ["BatteryManager"],
    "speech": ["SpeechRecognition", "webkitSpeechRecognition"],
}


def _host(text):
    return str(text or "").strip().lower().removeprefix("www.")


def rules(config):
    """What the script needs to know, as plain data.

    One table rather than one script per site: a QWebEngineScript
    belongs to a cookie jar and not to a page, so the page works out
    which rules are its own at run time from its own hostname.
    """
    config = config if isinstance(config, dict) else {}
    on = {}
    for name in GUARDS:
        on[name] = bool(config.get("guard" + name[0].upper() + name[1:],
                                   False))
    off = {}
    for name in GUARDS:
        for host in config.get("guardOff", {}).get(name, []) or []:
            off.setdefault(_host(host), []).append(name)
    apis = {}
    for host, names in (config.get("blockApis") or {}).items():
        wanted = [n for n in (names or []) if n in API_TARGETS]
        if wanted:
            apis[_host(host)] = sorted(
                {target for name in wanted for target in API_TARGETS[name]})
    places = {}
    for host, where in (config.get("fakePlaces") or {}).items():
        try:
            lat = float(where.get("lat"))
            lon = float(where.get("lon"))
        except (AttributeError, TypeError, ValueError):
            continue
        places[_host(host)] = {"lat": lat, "lon": lon}
    hide = {}
    for host, selectors in (config.get("hideElements") or {}).items():
        clean = [str(sel)[:300] for sel in (selectors or []) if str(sel).strip()]
        if clean:
            hide[_host(host)] = clean[:200]
    return {
        "on": on,
        "off": off,
        "apis": apis,
        "places": places,
        "hide": hide,
        "keep": [_host(h) for h in config.get("leaveTrapSites", []) or []],
        "allow": [_host(h) for h in config.get("popupSites", []) or []],
        "mics": {_host(h): str(d)[:200] for h, d in
                 (config.get("micSites") or {}).items() if d},
        "calls": {_host(h): {k: bool(v) for k, v in (row or {}).items()
                             if k in ("gain", "noise", "echo")}
                  for h, row in (config.get("callAudio") or {}).items()
                  if isinstance(row, dict)},
        "fonts": str(config.get("localFontStack")
                     or "system-ui, sans-serif")[:200],
        "reject": list(REJECT_WORDS),
        "marks": list(BANNER_MARKS),
    }


# The guard itself. One function, run at document creation in the
# page's own world, before the page's first line: a fingerprint read in
# an inline script at the top of the document is read before anything
# injected later could have moved.
_JS = r"""
(function () {
  var R = __GUARD_RULES__;
  var host = location.hostname.toLowerCase().replace(/^www\./, "");
  var off = R.off[host] || [];
  function on(name) {
    return !!R.on[name] && off.indexOf(name) < 0;
  }
  function keep(obj, name, value) {
    try {
      Object.defineProperty(obj, name, {get: function () { return value; },
                                        configurable: true});
    } catch (e) {}
  }

  /* ---- what the machine looks like ---------------------------------
     Not lies that stand out: a canvas that reads back pure white is as
     good a fingerprint as the real one. The pixels are nudged by one
     step in a way that is stable for this page and different for the
     next, which is what breaks the match without breaking a photo. */
  if (on("fingerprint")) {
    var seed = 0;
    for (var i = 0; i < host.length; i++) seed = (seed * 31 + host.charCodeAt(i)) & 0xffff;
    var nudge = function (data) {
      for (var i = 0; i < data.length; i += 997 * 4) {
        data[i] = data[i] ^ (seed & 1);
      }
      return data;
    };
    var realGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function () {
      var out = realGetImageData.apply(this, arguments);
      try { nudge(out.data); } catch (e) {}
      return out;
    };
    var realToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function () {
      try {
        var ctx = this.getContext("2d");
        if (ctx) {
          var shot = realGetImageData.call(ctx, 0, 0, this.width || 1,
                                           this.height || 1);
          nudge(shot.data);
          ctx.putImageData(shot, 0, 0);
        }
      } catch (e) {}
      return realToDataURL.apply(this, arguments);
    };
    keep(navigator, "hardwareConcurrency", 4);
    keep(navigator, "deviceMemory", 8);
    keep(navigator, "maxTouchPoints", 0);
    if (window.WebGLRenderingContext) {
      var realParam = WebGLRenderingContext.prototype.getParameter;
      WebGLRenderingContext.prototype.getParameter = function (p) {
        /* UNMASKED_VENDOR_WEBGL / UNMASKED_RENDERER_WEBGL */
        if (p === 37445) return "Mesa";
        if (p === 37446) return "Mesa Software Renderer";
        return realParam.apply(this, arguments);
      };
    }
    if (window.AudioBuffer) {
      var realChannel = AudioBuffer.prototype.getChannelData;
      AudioBuffer.prototype.getChannelData = function () {
        var out = realChannel.apply(this, arguments);
        try {
          for (var i = 0; i < out.length; i += 1000) {
            out[i] = out[i] + (seed % 7) * 1e-7;
          }
        } catch (e) {}
        return out;
      };
    }
  }

  /* ---- the clipboard ---------------------------------------------- */
  if (on("clipboardRead") && navigator.clipboard) {
    var deny = function () {
      return Promise.reject(new DOMException("Blocked by the browser",
                                             "NotAllowedError"));
    };
    try {
      navigator.clipboard.readText = deny;
      navigator.clipboard.read = deny;
    } catch (e) {}
  }
  if (on("copyGuard")) {
    /* The site's own copy handler never runs: this one answers first,
       puts the selection on the clipboard as it stands, and stops the
       event there. That is the whole of "copy what I selected". */
    document.addEventListener("copy", function (e) {
      try {
        var text = String(window.getSelection());
        if (!text) return;
        e.clipboardData.setData("text/plain", text);
        e.preventDefault();
        e.stopImmediatePropagation();
      } catch (err) {}
    }, true);
  }

  /* ---- the "Leave site?" box -------------------------------------- */
  if (on("leaveTrap") && R.keep.indexOf(host) < 0) {
    try {
      Object.defineProperty(window, "onbeforeunload",
                            {get: function () { return null; },
                             set: function () {}, configurable: true});
    } catch (e) {}
    var realAdd = window.addEventListener;
    window.addEventListener = function (type) {
      if (String(type).toLowerCase() === "beforeunload") return;
      return realAdd.apply(this, arguments);
    };
  }

  /* ---- the signal a site can read, if not the header -------------- */
  if (on("gpc")) {
    keep(navigator, "globalPrivacyControl", true);
    keep(navigator, "doNotTrack", "1");
  }

  /* ---- a place of his choosing ------------------------------------ */
  var place = R.places[host];
  if (place && navigator.geolocation) {
    var answer = function (ok) {
      if (typeof ok !== "function") return;
      ok({coords: {latitude: place.lat, longitude: place.lon,
                   accuracy: 1000, altitude: null, altitudeAccuracy: null,
                   heading: null, speed: null},
          timestamp: Date.now()});
    };
    navigator.geolocation.getCurrentPosition = function (ok) { answer(ok); };
    navigator.geolocation.watchPosition = function (ok) { answer(ok); return 1; };
    navigator.geolocation.clearWatch = function () {};
  }

  /* ---- what the page may not use at all --------------------------- */
  var gone = R.apis[host] || [];
  for (var g = 0; g < gone.length; g++) {
    try { delete window[gone[g]]; } catch (e) {}
    try { window[gone[g]] = undefined; } catch (e) {}
  }
  if (gone.indexOf("WebGLRenderingContext") >= 0) {
    var realCtx = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (kind) {
      if (/webgl/i.test(String(kind))) return null;
      return realCtx.apply(this, arguments);
    };
  }
  if (on("noWebRTC")) {
    var names = ["RTCPeerConnection", "webkitRTCPeerConnection",
                 "RTCDataChannel"];
    for (var n = 0; n < names.length; n++) {
      try { window[names[n]] = undefined; } catch (e) {}
    }
    if (navigator.mediaDevices) {
      try { navigator.mediaDevices.getUserMedia = function () {
        return Promise.reject(new DOMException("Blocked", "NotAllowedError"));
      }; } catch (e) {}
    }
  }

  /* ---- windows a script opens with nobody asking ------------------
     The engine refuses script-opened windows outright, which leaves
     nothing to show him and no way to let one through. This keeps the
     refusal and writes down what was refused, so the address bar can
     say so and he can open that one himself. A site on his own allow
     list is not touched at all. */
  if (on("popups") && R.allow.indexOf(host) < 0) {
    window.__guardPopups = [];
    window.open = function (url) {
      try {
        window.__guardPopups.push({url: String(url || ""), t: Date.now()});
      } catch (e) {}
      return null;
    };
  }

  /* ---- his microphone, and how a call should sound ----------------
     A call site asks for "a microphone", and sometimes for noise
     suppression it has decided he wants. This puts his own device and
     his own three switches into the request before it is made, because
     the engine offers no way to say it afterwards. Installed before
     the note-keeping below, so both apply when both are on. */
  var mic = R.mics[host] || "";
  var call = R.calls[host] || null;
  if ((mic || call) && navigator.mediaDevices
      && navigator.mediaDevices.getUserMedia) {
    var fixWant = function (want) {
      if (!want || typeof want !== "object" || !want.audio) return want;
      var audio = want.audio === true ? {} : want.audio;
      if (mic && !audio.deviceId) audio.deviceId = {exact: mic};
      if (call) {
        if (call.gain !== undefined) audio.autoGainControl = call.gain;
        if (call.noise !== undefined) audio.noiseSuppression = call.noise;
        if (call.echo !== undefined) audio.echoCancellation = call.echo;
      }
      want.audio = audio;
      return want;
    };
    var realAsk = navigator.mediaDevices.getUserMedia.bind(
      navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = function (want) {
      return realAsk(fixWant(want));
    };
  }

  /* ---- the microphone, the camera and the screen ------------------
     The engine tells the browser when a page asks for a device, never
     when the device is actually on. The page knows, so the page keeps
     the note: which kinds of track are live, and the streams
     themselves, so "stop using it" has something to stop. After
     noWebRTC on purpose -- with that on, getUserMedia is already a
     refusal and there is nothing to log. */
  if (on("mediaLog") && navigator.mediaDevices) {
    window.__guardMedia = [];
    window.__guardStreams = [];
    var md = navigator.mediaDevices;
    var relist = function () {
      var live = [];
      for (var i = 0; i < window.__guardStreams.length; i++) {
        var tracks = [];
        try { tracks = window.__guardStreams[i].getTracks(); } catch (e) {}
        for (var j = 0; j < tracks.length; j++) {
          if (tracks[j].readyState !== "live") continue;
          var kind = tracks[j].kind === "video" ? "camera" : "microphone";
          if (window.__guardStreams[i].__guardScreen) kind = "screen";
          if (live.indexOf(kind) < 0) live.push(kind);
        }
      }
      window.__guardMedia = live;
    };
    var watch = function (stream, screen) {
      try {
        if (screen) stream.__guardScreen = true;
        window.__guardStreams.push(stream);
        stream.getTracks().forEach(function (t) {
          t.addEventListener("ended", relist);
        });
        relist();
      } catch (e) {}
      return stream;
    };
    if (md.getUserMedia) {
      var realGum = md.getUserMedia.bind(md);
      md.getUserMedia = function (want) {
        return realGum(want).then(function (s) { return watch(s, false); });
      };
    }
    if (md.getDisplayMedia) {
      var realGdm = md.getDisplayMedia.bind(md);
      md.getDisplayMedia = function (want) {
        return realGdm(want).then(function (s) { return watch(s, true); });
      };
    }
  }

  /* ---- a note of the sockets it holds open ------------------------ */
  if (on("wsLog") && window.WebSocket) {
    window.__guardWs = [];
    var RealWS = window.WebSocket;
    var Wrapped = function (url, protocols) {
      var sock = protocols === undefined ? new RealWS(url)
                                         : new RealWS(url, protocols);
      try {
        var row = {url: String(url), open: true, t: Date.now()};
        window.__guardWs.push(row);
        sock.addEventListener("close", function () { row.open = false; });
      } catch (e) {}
      return sock;
    };
    Wrapped.prototype = RealWS.prototype;
    Wrapped.CONNECTING = 0; Wrapped.OPEN = 1;
    Wrapped.CLOSING = 2; Wrapped.CLOSED = 3;
    window.WebSocket = Wrapped;
  }

  /* ---- the things that need a document ---------------------------- */
  function onReady(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  var hide = R.hide[host] || [];
  if (hide.length) {
    /* his own hidden elements, as a stylesheet rather than a script
       walking the page: a rule keeps working when the site rebuilds
       the node, and costs nothing per frame. */
    var css = hide.join(",") + "{display:none !important}";
    onReady(function () {
      var style = document.createElement("style");
      style.id = "guard-hide";
      style.textContent = css;
      (document.head || document.documentElement).appendChild(style);
    });
  }

  if (on("localFonts")) {
    onReady(function () {
      var style = document.createElement("style");
      style.id = "guard-fonts";
      style.textContent =
        "body, p, li, td, th, h1, h2, h3, h4, h5, h6, blockquote, dd, dt" +
        "{font-family:" + R.fonts + " !important}";
      (document.head || document.documentElement).appendChild(style);
    });
  }

  if (on("noFrames")) {
    var dropFrames = function () {
      var frames = document.querySelectorAll("iframe[src]");
      for (var i = 0; i < frames.length; i++) {
        var src = frames[i].getAttribute("src") || "";
        if (!/^https?:/i.test(src)) continue;
        var other = "";
        try { other = new URL(src, location.href).hostname
                        .toLowerCase().replace(/^www\./, ""); } catch (e) {}
        if (other && other !== host && other.indexOf("." + host) < 0
            && host.indexOf("." + other) < 0) {
          frames[i].remove();
        }
      }
    };
    onReady(function () {
      dropFrames();
      new MutationObserver(dropFrames).observe(
        document.documentElement, {childList: true, subtree: true});
    });
  }

  if (on("banners")) {
    /* A consent dialog, answered with its own "reject" button. Only
       inside something that calls itself a consent dialog: a "decline"
       button in an ordinary form is somebody's actual answer to
       something, and clicking it would be the browser speaking for
       him. Tried a few times, because these things arrive late. */
    var tries = 0;
    var looksLikeBanner = function (el) {
      for (var node = el; node && node !== document.body; node = node.parentElement) {
        var text = ((node.id || "") + " " + (node.className || "")).toLowerCase();
        for (var m = 0; m < R.marks.length; m++) {
          if (text.indexOf(R.marks[m]) >= 0) return true;
        }
      }
      return false;
    };
    var reject = function () {
      var buttons = document.querySelectorAll(
        "button, a[role=button], [role=button], input[type=button], input[type=submit]");
      for (var i = 0; i < buttons.length; i++) {
        var b = buttons[i];
        var label = (b.textContent || b.value || "").trim().toLowerCase();
        if (!label || label.length > 40) continue;
        if (R.reject.indexOf(label) < 0) continue;
        if (!looksLikeBanner(b)) continue;
        var box = b.getBoundingClientRect();
        if (!box.width || !box.height) continue;
        b.click();
        window.__guardBanner = label;
        return true;
      }
      return false;
    };
    var tick = function () {
      if (reject() || ++tries > 10) return;
      setTimeout(tick, 400);
    };
    onReady(function () { setTimeout(tick, 250); });
  }
})();
"""


def source(config):
    """The guard script for this config, with the rule table baked in."""
    return _JS.replace("__GUARD_RULES__",
                       json.dumps(rules(config), separators=(",", ":")))


def wanted(config):
    """Whether anything at all is switched on. Nothing on means no
    script is injected, which is the difference between a feature that
    is off and a feature that is off but still runs."""
    table = rules(config)
    return bool(any(table["on"].values()) or table["apis"]
                or table["places"] or table["hide"] or table["mics"]
                or table["calls"])


def selector_for(path):
    """A short, stable CSS selector for one element, out of the path the
    picker collected. Used by the element hider: the id when there is
    one, otherwise the tag with its own classes, a couple of levels
    deep -- enough to be specific without being a path that breaks the
    next time the site renders."""
    parts = []
    for step in list(path or [])[-3:]:
        tag = re.sub(r"[^a-zA-Z0-9-]", "", str(step.get("tag") or "")).lower()
        if not tag:
            continue
        ident = str(step.get("id") or "").strip()
        if ident and re.fullmatch(r"[A-Za-z][\w-]*", ident):
            return "#" + ident
        classes = [c for c in str(step.get("class") or "").split()
                   if re.fullmatch(r"[A-Za-z][\w-]*", c)][:2]
        parts.append(tag + "".join("." + c for c in classes))
    return " > ".join(parts)
