"""Screenshots — the visible page, the whole page, one element, an area.

A sibling module like theme_web.py, loaded the same safe way: if this
file is missing or broken the browser still starts, it simply has no
capture entries. browser.py calls visible(), full_page(), element(),
area(), save(), to_clipboard(), pin(), clean() and redact(), and nothing
in here reaches back into the browser except through the view it is
handed.

Three things make a capture of a web page different from a capture of a
window. A page is taller than its window, so the whole page has to be
taken a screen at a time and stitched; the parts that are fixed to the
window (headers, cookie rails) would then appear once per screen, so
they are pinned down for the length of the capture; and a page often has
something on it that should not be in a picture at all — a password in a
field — so that can be blurred before the shutter.
"""

import time

from PyQt6.QtCore import (QBuffer, QByteArray, QEventLoop, QIODevice, QRect,
                          Qt, QTimer)
from PyQt6.QtGui import (QColor, QGuiApplication, QImage, QPainter,
                         QPen, QPixmap)
from PyQt6.QtWidgets import QLabel, QWidget, QVBoxLayout

# the formats he can ask for, and what Qt calls them
FORMATS = {"png": "PNG", "jpeg": "JPEG", "jpg": "JPEG", "webp": "WEBP"}

# while a capture is running the page is held still: nothing fixed to
# the window, no scrollbars, no caret, and (optionally) no cookie rails
CLEAN_JS = """(function (on) {
  var s = document.getElementById("__shotclean");
  if (s) s.remove();
  if (!on) {
    (window.__shotPinned || []).forEach(function (el) {
      el.style.removeProperty("position");
    });
    window.__shotPinned = [];
    return "off";
  }
  s = document.createElement("style");
  s.id = "__shotclean";
  s.textContent =
    "::-webkit-scrollbar { display: none !important; }"
    + "html { scrollbar-width: none !important; }"
    + "*, *::before, *::after { animation-play-state: paused !important;"
    + " transition: none !important; caret-color: transparent !important; }";
  document.documentElement.appendChild(s);
  // what is fixed to the window would otherwise be in every screen of a
  // long capture; each one is put back where it belongs in the page
  window.__shotPinned = [];
  var all = document.querySelectorAll("body *");
  for (var i = 0; i < all.length && i < 6000; i++) {
    var cs = getComputedStyle(all[i]);
    if (cs.position === "fixed" || cs.position === "sticky") {
      window.__shotPinned.push(all[i]);
      all[i].style.setProperty("position", "absolute", "important");
    }
  }
  return "on";
})(%s)"""

# anything that should not end up in a picture: what is typed in a
# password field, and anything he marked himself
REDACT_JS = """(function (on) {
  var s = document.getElementById("__shotredact");
  if (s) s.remove();
  if (!on) return "off";
  s = document.createElement("style");
  s.id = "__shotredact";
  s.textContent = "input[type=password], [data-redact],"
    + " .__redact { filter: blur(7px) !important; }";
  document.documentElement.appendChild(s);
  return "on";
})(%s)"""

# how tall the page is, how wide, and where it is scrolled to
METRICS_JS = """(function () {
  var d = document.documentElement, b = document.body || d;
  return [Math.max(d.scrollHeight, b.scrollHeight),
          Math.max(d.scrollWidth, b.scrollWidth),
          window.innerHeight, window.innerWidth,
          window.scrollX, window.scrollY,
          window.devicePixelRatio || 1];
})()"""

ELEMENT_JS = """(function (sel) {
  var el = document.querySelector(sel);
  if (!el) return null;
  el.scrollIntoView({block: "center", inline: "center"});
  var r = el.getBoundingClientRect();
  return [r.left, r.top, r.width, r.height, window.scrollX, window.scrollY];
})(%s)"""

POINT_JS = """(function (x, y) {
  var el = document.elementFromPoint(x, y);
  if (!el) return null;
  var r = el.getBoundingClientRect();
  return [r.left, r.top, r.width, r.height];
})(%s, %s)"""


def _spin(ms):
    """Let the engine paint. A capture is one of the few places that
    genuinely has to wait for a frame."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _js(view, code, world):
    """runJavaScript is asynchronous; a capture needs the answer before
    it can take the next step, so this one waits for it."""
    box = {}
    loop = QEventLoop()

    def done(value):
        box["v"] = value
        loop.quit()
    view.page().runJavaScript(code, world, done)
    QTimer.singleShot(4000, loop.quit)
    loop.exec()
    return box.get("v")


def clean(view, world, on=True):
    """Hold the page still for a capture, and put it back afterwards."""
    return _js(view, CLEAN_JS % ("true" if on else "false"), world)


def redact(view, world, on=True):
    """Blur what should not be in a picture."""
    return _js(view, REDACT_JS % ("true" if on else "false"), world)


def visible(view):
    """What is on the screen now."""
    return view.grab().toImage()


def area(view, rect):
    """A rectangle of what is on the screen, in device pixels."""
    shot = visible(view)
    if shot.isNull():
        return shot
    box = QRect(int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
    box = box.intersected(QRect(0, 0, shot.width(), shot.height()))
    if box.isEmpty():
        return QImage()
    return shot.copy(box)


def full_page(view, world, settle=160, limit=30000):
    """The whole scrolling page, one screen at a time.

    The page is held still first (see CLEAN_JS), then walked down a
    screen at a time with a moment at each stop for lazy images to
    arrive, and the screens are painted into one tall image. The last
    screen is usually a part-screen, so it is taken from the bottom of
    the page and painted at the bottom of the image rather than
    stretched.

    limit is there because some pages are endless: a timeline that grows
    as you scroll would otherwise capture until the memory ran out."""
    metrics = _js(view, METRICS_JS, world)
    if not metrics:
        return visible(view)
    height, width, inner_h, inner_w, was_x, was_y, ratio = metrics
    height = min(int(height), limit)
    shot = visible(view)
    if shot.isNull() or not inner_h:
        return shot
    scale = shot.height() / float(inner_h)      # device pixels per CSS pixel
    out = QImage(shot.width(), int(height * scale),
                 QImage.Format.Format_ARGB32)
    out.fill(Qt.GlobalColor.white)
    painter = QPainter(out)
    clean(view, world, True)
    try:
        y = 0
        while y < height:
            _js(view, "window.scrollTo(0, %d)" % y, world)
            _spin(settle)
            screen = visible(view)
            if screen.isNull():
                break
            top = int(y * scale)
            if y + inner_h > height:
                # the last screen: the page cannot scroll any further,
                # so take the bottom of it and put it at the bottom
                keep = int((height - y) * scale)
                painter.drawImage(0, out.height() - keep, screen,
                                  0, screen.height() - keep,
                                  screen.width(), keep)
                break
            painter.drawImage(0, top, screen)
            y += inner_h
    finally:
        painter.end()
        clean(view, world, False)
        _js(view, "window.scrollTo(%d, %d)" % (was_x, was_y), world)
    return out


def element(view, world, selector):
    """One element, named by a CSS selector, brought into view first."""
    box = _js(view, ELEMENT_JS % _q(selector), world)
    if not box:
        return QImage()
    _spin(160)
    shot = visible(view)
    if shot.isNull():
        return shot
    metrics = _js(view, METRICS_JS, world)
    scale = (shot.height() / float(metrics[2])
             if metrics and metrics[2] else 1.0)
    left, top, width, height = (box[0] * scale, box[1] * scale,
                                box[2] * scale, box[3] * scale)
    return area(view, (left, top, width, height))


def element_at(view, world, x, y):
    """The element under a point — what an element capture aims with."""
    return _js(view, POINT_JS % (int(x), int(y)), world)


def _q(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_clipboard(image):
    if image is None or image.isNull():
        return False
    QGuiApplication.clipboard().setImage(image)
    return True


def encode(image, fmt="png", quality=-1):
    """The image as bytes, for saving or for measuring how big it is."""
    if image is None or image.isNull():
        return b""
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, FORMATS.get(fmt.lower(), "PNG"), quality)
    buf.close()
    return bytes(data)


def fit_under(image, limit_bytes, fmt="jpeg"):
    """The same picture small enough to go somewhere with a size limit
    (Discord's, by default 10 MB). Quality first, then size: a readable
    screenshot at 70% quality beats a sharp one scaled to a postcard."""
    raw = encode(image, fmt, 92)
    if len(raw) <= limit_bytes:
        return raw, image
    shrunk = image
    for quality in (80, 70, 60, 50):
        raw = encode(shrunk, fmt, quality)
        if len(raw) <= limit_bytes:
            return raw, shrunk
    for _ in range(4):
        shrunk = shrunk.scaled(int(shrunk.width() * .75),
                              int(shrunk.height() * .75),
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        raw = encode(shrunk, fmt, 70)
        if len(raw) <= limit_bytes:
            return raw, shrunk
    return raw, shrunk


def name_for(pattern, title="", host="", fmt="png"):
    """The file name, from his pattern. %Y %m %d %H %M %S are the
    clock's, {title} and {site} are the page's."""
    stamp = time.strftime(pattern or "shot-%Y%m%d-%H%M%S")
    safe = "".join(c for c in (title or "") if c.isalnum() or c in " -_")[:60]
    stamp = stamp.replace("{title}", safe.strip() or "page")
    stamp = stamp.replace("{site}", host or "page")
    if not stamp.lower().endswith("." + fmt.lower()):
        stamp += "." + fmt.lower()
    return stamp


def save(image, directory, pattern="shot-%Y%m%d-%H%M%S", title="", host="",
         fmt="png", quality=-1):
    """Write it out; returns the path, or None if it could not be."""
    raw = encode(image, fmt, quality)
    if not raw:
        return None
    path = directory / name_for(pattern, title, host, fmt)
    n = 2
    while path.exists():
        path = directory / ("%s-%d.%s" % (path.stem, n, fmt.lower()))
        n += 1
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    except OSError:
        return None
    return path


class PinnedShot(QWidget):
    """A capture kept in a small window above everything, to copy from
    or compare against while working in another tab."""

    def __init__(self, image, title="", parent=None):
        super().__init__(parent, Qt.WindowType.Tool
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(title or "Screenshot")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        label = QLabel(self)
        shown = image
        if image.width() > 900:
            shown = image.scaledToWidth(
                900, Qt.TransformationMode.SmoothTransformation)
        label.setPixmap(QPixmap.fromImage(shown))
        lay.addWidget(label)
        self.image = image
        self.resize(shown.width(), shown.height())

    def mouseDoubleClickEvent(self, _event):
        to_clipboard(self.image)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_C and (
                event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            to_clipboard(self.image)
        else:
            super().keyPressEvent(event)

# =====================================================================
# Moving pictures, written here
# =====================================================================
# A tab is grabbed frame by frame -- there is no other way: the engine
# hands an embedder pixels, not a stream. The frames are kept as images
# and written out at the end, which is what makes the replay buffer and
# the trimming possible at all: the recording is a list, so keeping the
# last thirty seconds and cutting the first two are the same operation.
#
# What writes the file:
#   * a GIF is written here, in full, with its own LZW coder -- Qt
#     cannot write one and ffmpeg may not be installed;
#   * WebM and MP4 are handed to ffmpeg when it is installed, and the
#     entry says so when it is not.


class Recording:
    """A list of frames and when each was taken.

    Deliberately plain: the thing that makes a replay buffer, a trim and
    a GIF all possible is that a recording is a list of pictures with
    timestamps and nothing cleverer."""

    def __init__(self, fps=10, seconds=0):
        self.fps = max(1, min(30, int(fps)))
        self.seconds = max(0, int(seconds))      # 0 = keep everything
        self.frames = []                         # (when, QImage)
        self.started = time.time()
        self.stopped = None
        self.clicks = []                         # what to draw on top

    def add(self, image, when=None):
        if image is None or image.isNull():
            return False
        self.frames.append((float(when or time.time()), image))
        if self.seconds:
            cut = self.frames[-1][0] - self.seconds
            while len(self.frames) > 2 and self.frames[0][0] < cut:
                del self.frames[0]
        return True

    def length(self):
        if not self.frames:
            return 0.0
        return self.frames[-1][0] - self.frames[0][0]

    def trimmed(self, start=0.0, end=None):
        """A copy with the ends cut off, by seconds from the start."""
        if not self.frames:
            return []
        first = self.frames[0][0]
        last = self.frames[-1][0] - first
        end = last if end is None else float(end)
        return [(when, image) for when, image in self.frames
                if start <= (when - first) <= end]


# ---- GIF, written out in full ---------------------------------------
# One palette for the whole animation (the 6x6x6 web cube plus a grey
# ramp), nearest-colour mapping, and the LZW coder the format calls for.
# Not a quantiser: a screen recording of a web page is flat colour, and
# a shared cube keeps every frame's colours the same between frames,
# which is what stops a GIF of a page from shimmering.

def _gif_palette():
    rows = []
    for r in range(6):
        for g in range(6):
            for b in range(6):
                rows.append((r * 51, g * 51, b * 51))
    for i in range(40):
        grey = int(i * 255 / 39)
        rows.append((grey, grey, grey))
    return rows


_GIF_PALETTE = _gif_palette()


def _gif_index(r, g, b, _cache={}):
    key = (r >> 3, g >> 3, b >> 3)
    found = _cache.get(key)
    if found is not None:
        return found
    best, score = 0, None
    for at, (pr, pg, pb) in enumerate(_GIF_PALETTE):
        cost = (pr - r) ** 2 + (pg - g) ** 2 + (pb - b) ** 2
        if score is None or cost < score:
            best, score = at, cost
    _cache[key] = best
    return best


def _lzw(indices, bits=8):
    """The GIF variant of LZW: a code table that grows, cleared when it
    reaches twelve bits, and codes packed low bit first into blocks of
    at most 255 bytes."""
    clear, end = 1 << bits, (1 << bits) + 1
    out = bytearray()
    bit_buffer = 0
    bit_count = 0
    width = bits + 1
    table = {}
    next_code = end + 1

    def push(code):
        nonlocal bit_buffer, bit_count
        bit_buffer |= code << bit_count
        bit_count += width
        while bit_count >= 8:
            out.append(bit_buffer & 0xFF)
            bit_buffer >>= 8
            bit_count -= 8

    push(clear)
    if not indices:
        push(end)
    else:
        current = bytes([indices[0]])
        for value in indices[1:]:
            nxt = current + bytes([value])
            if nxt in table:
                current = nxt
                continue
            push(table.get(current, current[0]) if len(current) > 1
                 else current[0])
            table[nxt] = next_code
            next_code += 1
            if next_code == (1 << width) + 1 and width < 12:
                width += 1
            elif next_code > 4095:
                push(clear)
                table = {}
                next_code = end + 1
                width = bits + 1
            current = bytes([value])
        push(table.get(current, current[0]) if len(current) > 1
             else current[0])
        push(end)
    if bit_count:
        out.append(bit_buffer & 0xFF)
    # ...and into sub-blocks
    blocks = bytearray()
    at = 0
    while at < len(out):
        chunk = out[at:at + 255]
        blocks.append(len(chunk))
        blocks += chunk
        at += len(chunk)
    blocks.append(0)
    return bytes(blocks)


def write_gif(path, frames, delay_ms=100, width=0, height=0):
    """An animated GIF of these frames, written with nothing
    installed.

    `frames` is a list of QImage. They are scaled to the first one's
    size (or the size asked for), mapped onto one shared palette and
    LZW-coded. Returns the path, or "" when there was nothing to
    write."""
    rows = [one for one in frames if one is not None and not one.isNull()]
    if not rows:
        return ""
    width = int(width or rows[0].width())
    height = int(height or rows[0].height())
    if width < 1 or height < 1:
        return ""
    out = bytearray(b"GIF89a")
    out += bytes([width & 0xFF, width >> 8, height & 0xFF, height >> 8])
    out += bytes([0xF7, 0, 0])          # global table, 256 colours
    for r, g, b in _GIF_PALETTE:
        out += bytes([r, g, b])
    out += bytes([0, 0, 0]) * (256 - len(_GIF_PALETTE))
    # loop for ever (the Netscape extension, which is how a GIF loops)
    out += b"\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00"
    delay = max(2, int(delay_ms / 10))  # GIF counts in hundredths
    for one in rows:
        shot = one
        if shot.width() != width or shot.height() != height:
            shot = shot.scaled(width, height,
                               Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        shot = shot.convertToFormat(QImage.Format.Format_RGB888)
        indices = bytearray()
        for y in range(height):
            line = shot.constScanLine(y)
            raw = bytes(line.asarray(width * 3)) if hasattr(line, "asarray") \
                else bytes(shot.copy(0, y, width, 1).constBits().asstring(
                    width * 3))
            for x in range(width):
                indices.append(_gif_index(raw[x * 3], raw[x * 3 + 1],
                                          raw[x * 3 + 2]))
        out += b"\x21\xF9\x04\x00"
        out += bytes([delay & 0xFF, delay >> 8, 0, 0])
        out += b"\x2C"
        out += bytes([0, 0, 0, 0, width & 0xFF, width >> 8,
                      height & 0xFF, height >> 8, 0])
        out += bytes([8])
        out += _lzw(bytes(indices), 8)
    out += b"\x3B"
    try:
        with open(str(path), "wb") as handle:
            handle.write(bytes(out))
    except OSError:
        return ""
    return str(path)


def frames_to_video(frames, path, fps=10, ffmpeg="ffmpeg", quality="good"):
    """These frames as a WebM or MP4, through ffmpeg.

    Each frame is handed over as a PNG on ffmpeg's standard input, so
    nothing is written to disk twice and no temporary folder is left
    behind. Returns the path, or "" when ffmpeg is not there or said
    no."""
    import subprocess
    rows = [one for one in frames if one is not None and not one.isNull()]
    if not rows or not ffmpeg:
        return ""
    want = str(path).lower()
    if want.endswith(".mp4"):
        codec = ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    else:
        codec = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p"]
    rate = {"best": ["-crf", "20"], "good": ["-crf", "32"],
            "small": ["-crf", "42"]}.get(quality, ["-crf", "32"])
    args = [ffmpeg, "-y", "-f", "image2pipe", "-framerate", str(int(fps)),
            "-i", "-"] + codec + rate + ["-b:v", "0", str(path)]
    try:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except OSError:
        return ""
    try:
        for one in rows:
            proc.stdin.write(encode(one, "png"))
        proc.stdin.close()
        proc.wait(timeout=120)
    except (OSError, BrokenPipeError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass
        return ""
    return str(path) if proc.returncode == 0 else ""


# =====================================================================
# The editor after the shutter
# =====================================================================
# Crop, arrows, boxes, numbered markers, text and blur -- drawn onto the
# image itself with QPainter, so what is saved is exactly what is shown
# and there is no scene graph to serialise. Every step is a method that
# takes coordinates, which is what makes it testable without a mouse.


class Annotator:
    """A picture being marked up."""

    def __init__(self, image, colour="#f38ba8"):
        self.base = QImage(image)
        self.image = QImage(image)
        self.colour = colour
        self.steps = []
        self.counter = 0

    def _paint(self):
        painter = QPainter(self.image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        return painter

    def crop(self, x, y, width, height):
        box = QRect(int(x), int(y), int(width), int(height)).intersected(
            QRect(0, 0, self.image.width(), self.image.height()))
        if box.isEmpty():
            return False
        self.image = self.image.copy(box)
        self.base = QImage(self.image)
        self.steps.append(("crop", box.x(), box.y(), box.width(),
                           box.height()))
        return True

    def box(self, x, y, width, height, thick=3):
        painter = self._paint()
        pen = QPen(QColor(self.colour))
        pen.setWidth(int(thick))
        painter.setPen(pen)
        painter.drawRect(int(x), int(y), int(width), int(height))
        painter.end()
        self.steps.append(("box", x, y, width, height))
        return True

    def arrow(self, x1, y1, x2, y2, thick=3):
        painter = self._paint()
        pen = QPen(QColor(self.colour))
        pen.setWidth(int(thick))
        painter.setPen(pen)
        painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        # the head, as two lines back from the point
        import math
        angle = math.atan2(y2 - y1, x2 - x1)
        for side in (-0.4, 0.4):
            painter.drawLine(
                int(x2), int(y2),
                int(x2 - 16 * math.cos(angle + side)),
                int(y2 - 16 * math.sin(angle + side)))
        painter.end()
        self.steps.append(("arrow", x1, y1, x2, y2))
        return True

    def marker(self, x, y, radius=14):
        """A numbered circle: one, two, three, as a tutorial wants."""
        self.counter += 1
        painter = self._paint()
        painter.setBrush(QColor(self.colour))
        pen = QPen(QColor("#11111b"))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawEllipse(int(x - radius), int(y - radius),
                            radius * 2, radius * 2)
        painter.setPen(QPen(QColor("#11111b")))
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(int(radius * 1.3))
        painter.setFont(font)
        painter.drawText(QRect(int(x - radius), int(y - radius),
                               radius * 2, radius * 2),
                         Qt.AlignmentFlag.AlignCenter, str(self.counter))
        painter.end()
        self.steps.append(("marker", x, y, self.counter))
        return self.counter

    def text(self, x, y, words, size=18):
        painter = self._paint()
        font = painter.font()
        font.setPixelSize(int(size))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor(self.colour)))
        painter.drawText(int(x), int(y), str(words))
        painter.end()
        self.steps.append(("text", x, y, str(words)))
        return True

    def blur(self, x, y, width, height, radius=8):
        """A rectangle made unreadable, by scaling it down and back up.

        A box average would be a filter nobody can read through either;
        this is three lines and exactly as irreversible."""
        box = QRect(int(x), int(y), int(width), int(height)).intersected(
            QRect(0, 0, self.image.width(), self.image.height()))
        if box.isEmpty():
            return False
        patch = self.image.copy(box)
        small = patch.scaled(max(1, box.width() // max(2, radius)),
                             max(1, box.height() // max(2, radius)),
                             Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        back = small.scaled(box.width(), box.height(),
                            Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.FastTransformation)
        painter = self._paint()
        painter.drawImage(box.topLeft(), back)
        painter.end()
        self.steps.append(("blur", box.x(), box.y(), box.width(),
                           box.height()))
        return True

    def stamp(self, words, where="bottom"):
        """A strip along the edge with the address and the date on it --
        which is what makes a capture a record rather than a picture."""
        height = 26
        tall = self.image.height() + height
        sheet = QImage(self.image.width(), tall, QImage.Format.Format_RGB32)
        sheet.fill(QColor("#11111b"))
        painter = QPainter(sheet)
        top = height if where == "top" else 0
        painter.drawImage(0, top, self.image)
        font = painter.font()
        font.setPixelSize(14)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#cdd6f4")))
        painter.drawText(QRect(8, 0 if where == "top" else self.image.height(),
                               self.image.width() - 16, height),
                         Qt.AlignmentFlag.AlignVCenter, str(words))
        painter.end()
        self.image = sheet
        self.base = QImage(sheet)
        self.steps.append(("stamp", str(words), where))
        return True

    def undo(self):
        """Everything again except the last step -- which is why the
        steps are kept as data rather than painted and forgotten."""
        if not self.steps:
            return False
        self.steps.pop()
        steps, self.steps = list(self.steps), []
        self.image = QImage(self.base)
        self.counter = 0
        for step in steps:
            name = step[0]
            if name == "crop":
                self.crop(*step[1:])
            elif name == "box":
                self.box(*step[1:])
            elif name == "arrow":
                self.arrow(*step[1:])
            elif name == "marker":
                self.marker(step[1], step[2])
            elif name == "text":
                self.text(*step[1:])
            elif name == "blur":
                self.blur(*step[1:])
            elif name == "stamp":
                self.stamp(*step[1:])
        return True


def diff_images(first, second, colour="#f38ba8", tolerance=24):
    """What changed between two captures, drawn on the second one.

    Pixel by pixel with a tolerance, because a page re-rendered is
    never identical: anti-aliasing moves by a value or two and a diff
    that shouts about that is a diff nobody reads. Returns the picture
    and how many pixels really moved."""
    if first is None or second is None or first.isNull() or second.isNull():
        return QImage(), 0
    width = min(first.width(), second.width())
    height = min(first.height(), second.height())
    if width < 1 or height < 1:
        return QImage(), 0
    left = first.convertToFormat(QImage.Format.Format_RGB32)
    right = second.convertToFormat(QImage.Format.Format_RGB32)
    out = QImage(right)
    mark = QColor(colour)
    changed = 0
    for y in range(height):
        for x in range(width):
            a = left.pixelColor(x, y)
            b = right.pixelColor(x, y)
            if (abs(a.red() - b.red()) + abs(a.green() - b.green())
                    + abs(a.blue() - b.blue())) <= tolerance:
                continue
            changed += 1
            out.setPixelColor(x, y, mark)
    return out, changed
