"""The desk drawer: notes, to-dos, collections, snippets and clips.

A sibling module like theme_web.py, capture.py, privacy.py and
page_guard.py, loaded the same safe way: without this file the browser
starts and the notes panel is simply not there.

Everything is plain text in a folder he can point anywhere -- one
Markdown file per note, one `todo.md` with `- [ ] ` lines, one
`snippets.json`, a `collections/` folder. That is deliberate: a note
locked inside a browser's own database is a note he cannot open in an
editor, cannot grep and cannot back up with the rest of his files. The
browser is not the only program allowed to touch them.

Nothing here goes near the network, and nothing here holds a Qt object:
it is files and dictionaries, so it can be tested on its own.
"""

import json
import re
import time
from pathlib import Path

#: how many clips the clipboard history keeps. In memory only -- see
#: Desk.add_clip for why it is not written down.
CLIPS_MAX = 60

#: the front matter a note file carries. Written as plain `key: value`
#: lines between `---` markers, which is what every Markdown editor
#: already understands.
FIELDS = ("title", "link", "tags", "t", "edited")

_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text, fallback="note"):
    out = _SLUG.sub("-", str(text or "").lower()).strip("-")
    return (out or fallback)[:48]


def today():
    return time.strftime("%Y-%m-%d")


def parse_note(text):
    """A note file as a dictionary. A file with no front matter is a
    note with no title: that is what a file somebody dropped in the
    folder looks like, and it is still a note."""
    out = {"title": "", "link": "", "tags": [], "t": 0, "edited": 0,
           "body": str(text or "")}
    lines = str(text or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return out
    body_at = None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            body_at = i + 1
            break
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key not in FIELDS:
            continue
        if key == "tags":
            out["tags"] = [t.strip() for t in value.split(",") if t.strip()]
        elif key in ("t", "edited"):
            try:
                out[key] = int(float(value))
            except ValueError:
                out[key] = 0
        else:
            out[key] = value
    out["body"] = "\n".join(lines[body_at:]) if body_at is not None else ""
    return out


def note_text(note):
    """The other direction: a dictionary as a file."""
    head = ["---"]
    for key in FIELDS:
        value = note.get(key)
        if key == "tags":
            value = ", ".join(value or [])
        if value in (None, "", 0, []):
            continue
        head.append("%s: %s" % (key, value))
    head.append("---")
    return "\n".join(head) + "\n" + str(note.get("body") or "")


class Desk:
    """One folder of notes, and the small lists that go with them."""

    def __init__(self, folder):
        self.folder = Path(str(folder))
        self._clips = []

    # ---- the folder ----
    def _dir(self, *parts):
        path = self.folder.joinpath(*parts) if parts else self.folder
        try:
            (path if not parts else path.parent).mkdir(parents=True,
                                                       exist_ok=True)
        except OSError:
            pass
        return path

    def ready(self):
        try:
            self._dir().mkdir(parents=True, exist_ok=True)
            return self.folder.is_dir()
        except OSError:
            return False

    # ---- notes ----
    def note_files(self):
        """Every note file. todo.md is not one of them: it is the
        to-do list, in the same folder on purpose so the whole drawer
        is one folder, and it would otherwise read as a note called
        "todo"."""
        try:
            return sorted(p for p in self.folder.glob("*.md")
                          if p.name != self.TODO_FILE)
        except OSError:
            return []

    def notes(self, query=""):
        """Every note, newest first. A query matches the title, the body
        and the tags, word by word."""
        words = [w for w in str(query or "").lower().split() if w]
        out = []
        for path in self.note_files():
            try:
                note = parse_note(path.read_text(encoding="utf-8",
                                                 errors="replace"))
            except OSError:
                continue
            note["id"] = path.stem
            note["title"] = note["title"] or path.stem
            # the file's own time, to break a tie: two notes saved in
            # the same second are otherwise in whatever order the
            # folder happens to list them
            try:
                note["_mtime"] = path.stat().st_mtime
            except OSError:
                note["_mtime"] = 0
            if words:
                hay = " ".join((note["title"], note["body"],
                                " ".join(note["tags"]))).lower()
                if any(word not in hay for word in words):
                    continue
            out.append(note)
        out.sort(key=lambda n: (-(n.get("edited") or n.get("t") or 0),
                                -n.get("_mtime", 0)))
        for note in out:
            note.pop("_mtime", None)
        return out

    def note(self, nid):
        path = self.folder / (slug(nid) + ".md")
        if not path.exists():
            return None
        try:
            note = parse_note(path.read_text(encoding="utf-8",
                                             errors="replace"))
        except OSError:
            return None
        note["id"] = path.stem
        return note

    def save_note(self, nid=None, title="", body="", link="", tags=()):
        """Write a note. Without an id it is a new one, named after its
        title so the folder reads like a folder of notes rather than a
        folder of numbers."""
        now = int(time.time())
        if nid:
            note = self.note(nid) or {}
            nid = slug(nid)
        else:
            note = {}
            nid = slug(title or time.strftime("%Y-%m-%d-%H%M"))
            if (self.folder / (nid + ".md")).exists():
                nid = "%s-%d" % (nid, now % 100000)
        note.update({
            "title": str(title or note.get("title") or "")[:200],
            "body": str(body if body is not None else note.get("body", "")),
            "link": str(link or note.get("link") or "")[:2000],
            "tags": [str(t)[:40] for t in (tags or note.get("tags") or [])],
            "t": note.get("t") or now,
            "edited": now,
        })
        path = self._dir(nid + ".md")
        try:
            path.write_text(note_text(note), encoding="utf-8")
        except OSError:
            return None
        note["id"] = nid
        return note

    def append_note(self, nid, text):
        """Add a line to a note that is already there -- what "clip the
        selection" and the daily note do."""
        note = self.note(nid)
        if note is None:
            return None
        body = (note.get("body") or "").rstrip()
        body = (body + "\n\n" if body else "") + str(text or "")
        return self.save_note(nid, note.get("title", ""), body,
                              note.get("link", ""), note.get("tags", []))

    def delete_note(self, nid):
        path = self.folder / (slug(nid) + ".md")
        try:
            path.unlink()
        except OSError:
            return False
        return True

    def daily_note(self):
        """Today's note, made if it is not there yet."""
        nid = today()
        note = self.note(nid)
        if note is not None:
            return note
        return self.save_note(nid, today(), "")

    # ---- to-dos ----
    #
    # One `todo.md` of `- [ ] ` lines, in order, which is a to-do list
    # in every Markdown editor as well as in here. A line can carry
    # `(due: ...)` and `<url>`; both are read back out.
    TODO_FILE = "todo.md"
    _TODO = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(.*)$")

    def todo_path(self):
        return self._dir(self.TODO_FILE)

    def todos(self):
        try:
            lines = self.todo_path().read_text(
                encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        out = []
        for i, line in enumerate(lines):
            found = self._TODO.match(line)
            if not found:
                continue
            text = found.group(2).strip()
            link = ""
            due = 0
            url = re.search(r"<(https?://[^>]+)>", text)
            if url:
                link = url.group(1)
                text = text.replace(url.group(0), "").strip()
            when = re.search(r"\(due:\s*([^)]+)\)", text)
            if when:
                due = self._parse_due(when.group(1))
                text = text.replace(when.group(0), "").strip()
            out.append({"id": i, "text": text, "done": found.group(1) != " ",
                        "link": link, "due": due})
        return out

    @staticmethod
    def _parse_due(text):
        text = str(text or "").strip()
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d.%m.%Y %H:%M",
                    "%d.%m.%Y"):
            try:
                return int(time.mktime(time.strptime(text, fmt)))
            except ValueError:
                continue
        return 0

    def _write_todos(self, rows):
        lines = []
        for row in rows:
            text = row.get("text", "")
            if row.get("due"):
                text += " (due: %s)" % time.strftime(
                    "%Y-%m-%d %H:%M", time.localtime(row["due"]))
            if row.get("link"):
                text += " <%s>" % row["link"]
            lines.append("- [%s] %s" % ("x" if row.get("done") else " ",
                                        text.strip()))
        try:
            self.todo_path().write_text("\n".join(lines) + "\n",
                                        encoding="utf-8")
        except OSError:
            return False
        return True

    def add_todo(self, text, link="", due=0):
        rows = self.todos()
        rows.append({"text": str(text or "").strip()[:500], "done": False,
                     "link": str(link or "")[:2000], "due": int(due or 0)})
        if not rows[-1]["text"]:
            return []
        self._write_todos(rows)
        return self.todos()

    def toggle_todo(self, tid, done=None):
        rows = self.todos()
        for row in rows:
            if row["id"] == int(tid):
                row["done"] = (not row["done"]) if done is None else bool(done)
        self._write_todos(rows)
        return self.todos()

    def delete_todo(self, tid):
        rows = [r for r in self.todos() if r["id"] != int(tid)]
        self._write_todos(rows)
        return self.todos()

    def move_todo(self, tid, delta):
        rows = self.todos()
        at = next((i for i, r in enumerate(rows) if r["id"] == int(tid)), None)
        if at is None:
            return rows
        to = max(0, min(len(rows) - 1, at + int(delta)))
        rows.insert(to, rows.pop(at))
        self._write_todos(rows)
        return self.todos()

    def clear_done_todos(self):
        rows = [r for r in self.todos() if not r["done"]]
        gone = len(self.todos()) - len(rows)
        self._write_todos(rows)
        return gone

    def due_todos(self, at=None):
        """The to-dos whose time has come, and not yet done."""
        at = time.time() if at is None else at
        return [r for r in self.todos()
                if r["due"] and not r["done"] and r["due"] <= at]

    # ---- collections ----
    def collections(self):
        try:
            return sorted(p.stem for p in
                          (self.folder / "collections").glob("*.md"))
        except OSError:
            return []

    def collection(self, name):
        path = self.folder / "collections" / (slug(name) + ".md")
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def add_to_collection(self, name, title, url="", note=""):
        """One line per thing, as a Markdown list -- which means the
        file is already the export."""
        path = self._dir("collections", slug(name) + ".md")
        line = "- "
        line += ("[%s](%s)" % (title or url, url)) if url else (title or "")
        if note:
            line += " — " + str(note)
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line.strip() + "\n")
        except OSError:
            return ""
        return str(path)

    def delete_collection(self, name):
        try:
            (self.folder / "collections" / (slug(name) + ".md")).unlink()
        except OSError:
            return False
        return True

    # ---- snippets ----
    def snippet_path(self):
        return self._dir("snippets.json")

    def snippets(self):
        try:
            raw = json.loads(self.snippet_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(k)[:40]: str(v)[:4000] for k, v in raw.items()
                if str(k).strip()}

    def set_snippet(self, key, text):
        table = self.snippets()
        key = str(key or "").strip()[:40]
        if not key:
            return {}
        if text:
            table[key] = str(text)[:4000]
        else:
            table.pop(key, None)
        try:
            self.snippet_path().write_text(json.dumps(table, indent=1),
                                           encoding="utf-8")
        except OSError:
            return {}
        return table

    def expand(self, word):
        """What a snippet key stands for, or "" when it is not one."""
        return self.snippets().get(str(word or "").strip(), "")

    # ---- the clipboard history ----
    def clips(self):
        return list(self._clips)

    def add_clip(self, text, kind="text"):
        """Remember something copied.

        In memory only, and never written to the folder: a file of
        everything he has copied is a file of passwords, card numbers
        and private messages. It lives as long as the browser does and
        not a moment longer, and a private tab never feeds it (see
        Browser.remember_clip)."""
        text = str(text or "")
        if not text.strip():
            return self._clips
        self._clips = [c for c in self._clips if c["text"] != text]
        self._clips.insert(0, {"text": text[:20000], "kind": str(kind),
                               "t": int(time.time()), "pinned": False})
        pinned = [c for c in self._clips if c["pinned"]]
        rest = [c for c in self._clips if not c["pinned"]][:CLIPS_MAX]
        self._clips = pinned + [c for c in rest if c not in pinned]
        return self._clips

    def pin_clip(self, index, on=None):
        if not (0 <= int(index) < len(self._clips)):
            return self._clips
        clip = self._clips[int(index)]
        clip["pinned"] = (not clip["pinned"]) if on is None else bool(on)
        return self._clips

    def drop_clip(self, index):
        if 0 <= int(index) < len(self._clips):
            del self._clips[int(index)]
        return self._clips

    def clear_clips(self, keep_pinned=True):
        before = len(self._clips)
        self._clips = [c for c in self._clips
                       if keep_pinned and c["pinned"]]
        return before - len(self._clips)

    # ---- one search across the drawer ----
    def search_all(self, query, limit=40):
        """Notes, to-dos, collections and clips in one list. What the
        "everything" box asks."""
        words = [w for w in str(query or "").lower().split() if w]
        if not words:
            return []
        out = []
        for note in self.notes(query):
            out.append({"kind": "note", "title": note["title"],
                        "id": note["id"], "text": note["body"][:200]})
        for row in self.todos():
            hay = (row["text"] + " " + row["link"]).lower()
            if all(w in hay for w in words):
                out.append({"kind": "todo", "title": row["text"],
                            "id": row["id"], "text": row["link"]})
        for name in self.collections():
            body = self.collection(name)
            if all(w in (name + " " + body).lower() for w in words):
                out.append({"kind": "collection", "title": name,
                            "id": name, "text": body[:200]})
        for i, clip in enumerate(self._clips):
            if all(w in clip["text"].lower() for w in words):
                out.append({"kind": "clip", "title": clip["text"][:60],
                            "id": i, "text": ""})
        return out[:limit]
