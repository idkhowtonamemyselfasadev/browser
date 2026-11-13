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
import os
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

# letters of any alphabet are kept: with [a-z0-9] only, "Küche" and
# "Kuche" (or 日本 and 中文) all became one file
_SLUG = re.compile(r"[\W_]+", re.UNICODE)
_SLUG_OLD = re.compile(r"[^a-z0-9]+")


def _write_atomic(path, text):
    """Written beside the file and swapped in, the way the browser
    writes its own files: a kill or a power cut in the middle of a save
    leaves the note as it was, not half of it or nothing. A note, the
    to-do list and the snippets are his own words, and the one copy."""
    path = Path(path)
    tmp = path.with_name(path.name + ".new")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def slug(text, fallback="note"):
    out = _SLUG.sub("-", str(text or "").lower()).strip("-")
    return (out or fallback)[:48]


def slug_old(text, fallback="note"):
    """The name an older version gave the file, for finding it again."""
    out = _SLUG_OLD.sub("-", str(text or "").lower()).strip("-")
    return (out or fallback)[:48]


def today():
    return time.strftime("%Y-%m-%d")


def parse_note(text):
    """A note file as a dictionary. A file with no front matter is a
    note with no title: that is what a file somebody dropped in the
    folder looks like, and it is still a note."""
    out = {"title": "", "link": "", "tags": [], "t": 0, "edited": 0,
           "body": str(text or "")}
    # split on "\n" only: splitlines also cuts at U+2028, \x0b, \x0c and
    # "\r", and the join below then turned each of them (and the last
    # newline) into something else on every save
    lines = str(text or "").split("\n")
    if not lines or lines[0].strip() != "---":
        return out
    body_at = None
    plain = dict(out)
    extra = []
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            body_at = i + 1
            break
        key, colon, value = line.partition(":")
        if not colon:
            if line[:1] in (" ", "\t", "-") or not line.strip():
                if line.strip():
                    extra.append(line)   # a YAML list under a key of his
                continue
            # "---" then a line of text: a rule at the top of a note,
            # not front matter. Read as fields, the text was dropped
            # and the next Save wrote the file back without it.
            return plain
        key = key.strip().lower()
        value = value.strip()
        if key not in FIELDS:
            # his own keys (date:, aliases:) are kept and written back
            extra.append(line)
            continue
        if key == "tags":
            out["tags"] = [t.strip() for t in value.split(",") if t.strip()]
        elif key in ("t", "edited"):
            try:
                out[key] = max(0, int(float(value)))
            except (ValueError, OverflowError):
                # "inf" or 1e999 overflowed and took the whole list with it
                out[key] = 0
        else:
            out[key] = value
    if body_at is None:
        return plain       # no closing line: none of it was front matter
    out["body"] = "\n".join(lines[body_at:])
    if extra:
        out["extra"] = extra
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
    head.extend(str(line) for line in note.get("extra") or [])
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

    def _note_id(self, nid):
        """A note's file name, never the to-do list's: a note called
        "Todo" is todo.md by its slug, and written there it was read as
        the list and wiped by the next to-do added."""
        raw = str(nid or "")
        # a file that is there under exactly this name is that note: one
        # dropped into the folder ("Meeting Notes.md", "README.md") is
        # listed by its own stem, and its slug named a different file,
        # so it could be listed but not opened, edited or deleted -- and
        # saving it wrote a second copy beside it. Only a plain name in
        # this folder, never a path, and never the to-do list.
        if (raw and "/" not in raw and "\\" not in raw
                and not raw.startswith(".") and "\0" not in raw
                and raw + ".md" != self.TODO_FILE):
            try:
                if (self.folder / (raw + ".md")).is_file():
                    return raw
            except (OSError, ValueError):
                pass
        nid = slug(nid)
        if nid + ".md" == self.TODO_FILE:
            nid += "-note"
        return nid

    def note(self, nid):
        path = self.folder / (self._note_id(nid) + ".md")
        if not path.exists():
            return None
        try:
            note = parse_note(path.read_text(encoding="utf-8",
                                             errors="replace"))
        except OSError:
            return None
        note["id"] = path.stem
        return note

    def save_note(self, nid=None, title=None, body=None, link=None,
                  tags=None):
        """Write a note. Without an id it is a new one, named after its
        title so the folder reads like a folder of notes rather than a
        folder of numbers.

        None keeps what the note has; anything else, an empty string or
        an empty list included, is the new value. It was "or the old
        one", so a link or the tags emptied in the panel came back on
        the next load."""
        now = int(time.time())
        if nid:
            note = self.note(nid) or {}
            nid = self._note_id(nid)
        else:
            note = {}
            nid = self._note_id(title or time.strftime("%Y-%m-%d-%H%M"))
            if (self.folder / (nid + ".md")).exists():
                nid = "%s-%d" % (nid, now % 100000)
        note.update({
            "title": str((note.get("title") or "") if title is None
                         else title)[:200],
            "body": str(body if body is not None else note.get("body", "")),
            "link": str((note.get("link") or "") if link is None
                        else link)[:2000],
            "tags": [str(t)[:40] for t in
                     ((note.get("tags") or []) if tags is None else tags)],
            "t": note.get("t") or now,
            "edited": now,
        })
        path = self._dir(nid + ".md")
        try:
            _write_atomic(path, note_text(note))
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
        path = self.folder / (self._note_id(nid) + ".md")
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
                # only taken out when it was read: "(due: tomorrow)" was
                # dropped and the line rewritten without it the next
                # time any to-do in the file was ticked or moved
                if due:
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

    @staticmethod
    def _todo_line(row):
        text = " ".join(str(row.get("text", "")).split())
        if row.get("due"):
            text += " (due: %s)" % time.strftime(
                "%Y-%m-%d %H:%M", time.localtime(row["due"]))
        if row.get("link"):
            text += " <%s>" % row["link"]
        return "- [%s] %s" % ("x" if row.get("done") else " ", text.strip())

    def _write_todos(self, rows):
        """The list back into its file, around everything else in it.

        The file is his as much as the browser's -- a heading, a note
        under a to-do, a blank line between two groups -- and this used
        to write the to-do lines alone, so ticking one off in the panel
        deleted every other line he had put there. Now each to-do keeps
        its own line (rows carry the line they came from as "id"), a
        deleted one takes only its line with it, a moved one trades
        places with the others among the to-do lines, a new one goes in
        after the last to-do, and nothing else is touched."""
        try:
            lines = self.todo_path().read_text(
                encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        slots = [i for i, line in enumerate(lines) if self._TODO.match(line)]
        old = [r for r in rows if isinstance(r.get("id"), int)]
        new = [r for r in rows if not isinstance(r.get("id"), int)]
        alive = {r["id"] for r in old}
        kept = [i for i in slots if i in alive]
        placed = dict(zip(kept, old))
        out = []
        last = -1
        for i, line in enumerate(lines):
            if i in placed:
                out.append(self._todo_line(placed[i]))
                last = len(out) - 1
            elif i in slots:
                continue                    # a deleted to-do: its line goes
            else:
                out.append(line)
        # anything the old file had no line for (a fresh one, or one
        # read before the file was there) after the last to-do
        extra = [self._todo_line(r) for r in old[len(kept):] + new]
        at = last + 1 if last >= 0 else len(out)
        out[at:at] = extra
        try:
            _write_atomic(self.todo_path(), "\n".join(out) + "\n")
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
        step = int(delta)
        if step in (-1, 1):
            # the panel shows open and done ones apart: moved past a done
            # one, an open to-do did not move on screen at all
            j = at + step
            while 0 <= j < len(rows) and rows[j]["done"] != rows[at]["done"]:
                j += step
            if not 0 <= j < len(rows):
                return self.todos()
            rows[at], rows[j] = rows[j], rows[at]
        else:
            to = max(0, min(len(rows) - 1, at + step))
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

    def _collection_path(self, name):
        """A collection's file: the one by exactly this name if it is
        there ("Reading List.md", dropped in by hand), else the slug's.
        Listed by its own name and looked up by its slug, it showed
        empty and could not be deleted."""
        raw = str(name or "")
        if (raw and "/" not in raw and "\\" not in raw
                and not raw.startswith(".") and "\0" not in raw):
            try:
                path = self.folder / "collections" / (raw + ".md")
                if path.is_file():
                    return path
            except (OSError, ValueError):
                pass
        new = self.folder / "collections" / (slug(name) + ".md")
        old = self.folder / "collections" / (slug_old(name) + ".md")
        try:
            # only when the old name was a real one: every name in another
            # alphabet used to fall back to "note", and that file is not
            # this collection's
            if not new.is_file() and old.is_file() \
                    and slug_old(name, fallback=""):
                return old     # written by an older version: still found
        except OSError:
            pass
        return new

    def collection(self, name):
        path = self._collection_path(name)
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def add_to_collection(self, name, title, url="", note=""):
        """One line per thing, as a Markdown list -- which means the
        file is already the export."""
        # the file it is read from: "Reading List.md" dropped in by hand
        # got a second "reading-list.md" beside it, never shown
        path = self._collection_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
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
            self._collection_path(name).unlink()
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
            _write_atomic(self.snippet_path(), json.dumps(table, indent=1))
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
        # cut first: it is the cut text that is stored, so it is the cut
        # text a copy of the same thing has to be compared with
        text = str(text or "")[:20000]
        if not text.strip():
            return self._clips
        # a pinned one copied again stays pinned (it lost its star, and
        # then the next Clear or the cap took it)
        was = any(c["text"] == text and c.get("pinned") for c in self._clips)
        self._clips = [c for c in self._clips if c["text"] != text]
        self._clips.insert(0, {"text": text, "kind": str(kind),
                               "t": int(time.time()), "pinned": was})
        pinned = [c for c in self._clips if c["pinned"]]
        rest = [c for c in self._clips if not c["pinned"]][:CLIPS_MAX]
        self._clips = pinned + [c for c in rest if c not in pinned]
        return self._clips

    def clip_index(self, index, text=None):
        """Where a clip is NOW. The panel's row number goes stale the
        moment something new is copied (the newest goes on top), and
        pin, drop and copy then hit the clip below the one he clicked.
        A clip's text is unique in the list (add_clip keeps one of
        each), so the text names it; the number is only the fallback."""
        if text is not None:
            for at, clip in enumerate(self._clips):
                if clip["text"] == str(text)[:20000]:
                    return at
            return -1
        try:
            return int(index)
        except (TypeError, ValueError):
            return -1

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
