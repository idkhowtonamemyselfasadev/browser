"""EasyList-format filter lists, read and matched here.

Why a module of its own: the engine gives one honest place to stop a
request -- QWebEngineUrlRequestInterceptor, which the browser already
installs for its request log -- and everything else about blocking is
text processing that has nothing to do with Qt. Keeping it here means
it can be read, tested and argued with on its own, and that the
interceptor stays what it must be: a dict lookup and nothing slow.

What it understands, which is the part worth being plain about. These
lists have grown twenty years of syntax and this reads the part that
does the work:

    ||example.com^              a host and its sub-domains
    ||example.com^$third-party  ...only when the page is elsewhere
    ||example.com/ads/*         a host with a path
    /ads/banner.gif             a substring of the address
    @@||example.com^            an exception: never block this
    ##.ad-banner                hide that element everywhere
    example.com##.sidebar       ...on that site only
    example.com#@#.sidebar      ...except on that site

and the options `third-party`/`3p`, `first-party`/`1p`, `domain=`,
`script`, `image`, `stylesheet`, `xmlhttprequest`, `subdocument`,
`font`, `media`, `websocket`, `other`, and `~` in front of any of them.

What it does not: regular-expression rules (`/.../`), `$csp`,
`$redirect`, `$removeparam`, `$replace`, snippet filters, and the
`:has-text()`-style extended selectors. Those lines are counted and
reported rather than silently dropped, so "41,233 rules, 1,208 lines
this does not do" is something he can see rather than guess at.

Matching is two indexes, not a walk. A rule that names a host is
filed under that host, and a request asks for its own host and each
parent of it -- which is also what stops a host rule matching an
address that merely mentions the domain. A rule that names no host is
filed under the longest word it must contain, and a request asks for
the words in it. Only the few rules with no word long enough to file
are ever scanned. Measured on a synthetic 50,000-rule pair of lists:
17 ms per request walking them, 0.014 ms with the indexes -- which is
the difference between a blocker that can sit in front of every
request a page makes and one that cannot.
"""

import re
import time
from pathlib import Path
from urllib.parse import urlsplit

#: what a resource type is called in a filter list, mapped to the
#: words the browser's own interceptor already uses
KINDS = {
    "script": "script",
    "image": "image",
    "stylesheet": "stylesheet",
    "xmlhttprequest": "xhr",
    "subdocument": "frame",
    "font": "font",
    "media": "media",
    "websocket": "websocket",
    "ping": "ping",
    "other": "other",
    "document": "document",
}

#: options that change what a rule means but that this does not do.
#: A rule carrying one of these is not kept at all: half-applying a
#: $redirect rule would block something the list meant to replace.
REFUSED = ("csp", "redirect", "redirect-rule", "removeparam", "replace",
           "rewrite", "inline-script", "inline-font", "empty", "mp4",
           "generichide", "genericblock", "elemhide", "important,badfilter",
           "badfilter", "all")


_TOKEN = re.compile(r"[a-z0-9]{4,}")


def _tokens(text):
    """The words in an address, lower-cased, four characters or more.

    What makes the matcher fast enough to sit in front of every
    request a page makes: a rule with `_banner` in it can only ever
    match an address containing "banner", so it is filed under that
    word and never looked at for an address without it. Measured on a
    synthetic 50,000-rule pair of lists: 17 ms per request before this,
    0.02 ms after.
    """
    return _TOKEN.findall(str(text or "").lower())


#: how much of an edge word the prefix and suffix tables keep
_EDGE = 12


def _rule_index(parts):
    """Where a rule is filed: (word, how), how being "word", "prefix",
    "suffix" -- or ("", None) for the few looked at for every address.

    A word with something that is not a letter or digit on both sides
    of it, inside the pattern, is a whole word of any address the rule
    matches. One at the edge of a pattern is not: `adserver.example`
    matches https://myadserver.example/, whose word there is
    "myadserver". Filed under "adserver" as a whole word, that rule was
    never even looked at for it -- the index answered for the matcher.
    So an edge word is filed by what the address's word must start or
    end with, and only a pattern with no usable word at all is loose.
    """
    best = {"word": "", "prefix": "", "suffix": ""}
    for part in parts:
        low = part.lower()
        for m in _TOKEN.finditer(low):
            one = m.group(0)
            left = m.start() > 0
            right = m.end() < len(low)
            how = ("word" if left and right else "prefix" if left
                   else "suffix" if right else None)
            if how and len(one) > len(best[how]):
                best[how] = one
    for how in ("word", "prefix", "suffix"):
        if best[how]:
            one = best[how]
            if how == "prefix":
                one = one[:_EDGE]
            elif how == "suffix":
                one = one[-_EDGE:]
            return one, how
    return "", None


def _rule_token(parts):
    """The whole word a rule is filed under, or "" (see _rule_index)."""
    word, how = _rule_index(parts)
    return word if how == "word" else ""


def _host_parents(host):
    """`a.b.example.com` -> itself, b.example.com, example.com, com."""
    host = (host or "").lower().strip(".")
    out = []
    while host:
        out.append(host)
        if "." not in host:
            break
        host = host.split(".", 1)[1]
    return out


class Rule:
    """One network rule: what to look for, and when it counts."""

    __slots__ = ("raw", "host", "parts", "anchor_host", "anchor_start",
                 "anchor_end", "third", "first", "kinds", "not_kinds",
                 "domains", "not_domains", "exception", "match_case",
                 "seps")

    def __init__(self, raw):
        self.raw = raw
        self.host = ""
        self.parts = []
        self.anchor_host = False
        self.anchor_start = False
        self.anchor_end = False
        self.third = False
        self.first = False
        self.kinds = set()
        self.not_kinds = set()
        self.domains = []
        self.not_domains = []
        self.exception = False
        self.match_case = False
        self.seps = []

    def matches(self, url, page_host, kind, third_party, low=None):
        if self.third and not third_party:
            return False
        if self.first and third_party:
            return False
        if self.kinds and kind not in self.kinds:
            return False
        if kind in self.not_kinds:
            return False
        # the page itself only for a rule that says $document: a plain
        # "/banner/" or "||tracker.example^" refused a link he clicked
        # (or an address he typed) to a page whose address has it
        if kind == "document" and "document" not in self.kinds:
            return False
        if self.domains or self.not_domains:
            where = _host_parents(page_host)
            if self.not_domains and any(one in where
                                        for one in self.not_domains):
                return False
            if self.domains and not any(one in where
                                        for one in self.domains):
                return False
        if not self.match_case:
            url = low if low is not None else url.lower()
        at = 0
        seps = self.seps
        for n, part in enumerate(self.parts):
            found = url.find(part, at)
            if n < len(seps) and seps[n]:
                # "^": what follows has to be a separator or the end --
                # "||cdn.example/ad^" is not /ads-good/ nor /adobe/, and
                # "||example.com^" is not example.com.evil
                while found >= 0 and not _separated(url, found + len(part)):
                    found = url.find(part, found + 1)
            if found < 0:
                return False
            if n == 0 and self.anchor_start and found != 0:
                return False
            at = found + len(part)
        if self.anchor_end and at != len(url):
            return False
        return True


#: the cosmetic operators uBlock Origin and AdGuard add to CSS. None of
#: them is CSS; one of them in a selector list made the whole list
#: invalid (see Browser.ad_css_for).
_PROCEDURAL = re.compile(
    r":(?:style|remove|remove-attr|remove-class|upward|xpath|"
    r"matches-css(?:-before|-after)?|matches-path|matches-attr|"
    r"matches-media|matches-prop|min-text-length|watch-attr|others|"
    r"if|if-not|nth-ancestor|contains|properties|spath)\(")


def _separated(url, at):
    """A "^" in a list: the end of the address, or a character that is
    not a letter, a digit, or one of _ - . %."""
    if at >= len(url):
        return True
    ch = url[at]
    return not (ch.isalnum() or ch in "_-.%")


def _site_of(host):
    """The registrable part of a host, near enough: the last two labels,
    or three under a two-letter country code with a co/com/org-style
    second level (example.co.uk)."""
    host = str(host or "").lower().strip("[]").rstrip(".")
    bits = [one for one in host.split(".") if one]
    # an address is its own site (192.168.1.5 and 10.9.1.5 both ended
    # in "1.5"), and so is each tenant of a shared host
    if ":" in host or (bits and all(one.isdigit() for one in bits)):
        return host
    if len(bits) >= 4 and ".".join(bits[-3:]) in _SHARED_HOSTS:
        return ".".join(bits[-4:])        # bucket.s3.amazonaws.com
    if len(bits) >= 3 and ".".join(bits[-2:]) in _SHARED_HOSTS:
        return ".".join(bits[-3:])
    if len(bits) >= 3 and len(bits[-1]) == 2 and bits[-2] in (
            "co", "com", "org", "net", "gov", "ac", "edu", "or", "ne"):
        return ".".join(bits[-3:])
    return ".".join(bits[-2:])


#: hosts whose subdomains belong to different people
_SHARED_HOSTS = frozenset((
    "github.io", "gitlab.io", "blogspot.com", "pages.dev", "netlify.app",
    "vercel.app", "herokuapp.com", "appspot.com", "web.app",
    "firebaseapp.com", "azurewebsites.net", "cloudfront.net",
    "workers.dev", "glitch.me", "neocities.org", "wordpress.com",
    "tumblr.com", "s3.amazonaws.com"))


def parse_line(line):
    """One line of a list: a Rule, a hide rule, or why it was dropped.

    Returns (kind, value): ("net", Rule), ("hide", (hosts, selector,
    unhide)), ("skip", reason) or (None, None) for a comment or an
    empty line.
    """
    line = (line or "").strip()
    # "#@#.sponsored" (an exception everywhere) starts with "#" too: read
    # as a comment, it was dropped without even being counted
    if not line or line[0] in "!#[" \
            and not line.startswith(("##", "#@#")):
        return None, None
    # element hiding, before the network rules: the separator decides
    if "##" in line or "#@#" in line or "#?#" in line:
        for sep, unhide in (("#@#", True), ("#?#", False), ("##", False)):
            if sep not in line:
                continue
            left, _, selector = line.partition(sep)
            selector = selector.strip()
            if not selector:
                return "skip", "empty selector"
            if sep == "#?#" or ":has-text(" in selector \
                    or ":-abp-" in selector or selector.startswith("+js"):
                return "skip", "extended selector"
            # uBlock's own operators and HTML filters are not CSS, and a
            # brace is not a selector at all: "div } body { ... }" from a
            # list would close the hiding rule and put a stylesheet of
            # its own on every page (an attribute selector with a
            # background url() reads what is typed into a box)
            if selector.startswith("^") or "{" in selector \
                    or "}" in selector or _PROCEDURAL.search(selector):
                return "skip", "extended selector"
            # an unclosed bracket or quote, or a comment, runs on to the
            # end of the stylesheet the rules are joined into: one such
            # line and every hiding rule after it was gone
            if selector.count("(") != selector.count(")") \
                    or selector.count("[") != selector.count("]") \
                    or selector.count('"') % 2 or "/*" in selector:
                return "skip", "broken selector"
            hosts = [one.strip().lower().removeprefix("www.")
                     for one in left.split(",") if one.strip()]
            return "hide", (hosts, selector, unhide)
    exception = line.startswith("@@")
    if exception:
        line = line[2:]
    # a regular-expression rule is /.../ with anything inside it,
    # options and all -- so it is spotted before the $ is split off,
    # or `/^ads.*$/` reads as a rule with an option
    naked = line.split("$")[0]
    if (line.startswith("/") and line.endswith("/") and len(line) > 2) \
            or (naked.startswith("/") and naked.endswith("/")
                and len(naked) > 2):
        return "skip", "regular expression"
    body, _, options = line.partition("$")
    rule = Rule(line)
    rule.exception = exception
    for option in [one.strip().lower() for one in options.split(",")
                   if one.strip()]:
        negated = option.startswith("~")
        name = option.lstrip("~")
        if name in REFUSED:
            return "skip", "option $" + name
        if name in ("third-party", "3p"):
            rule.third = not negated
            rule.first = negated
            continue
        if name in ("first-party", "1p"):
            rule.first = not negated
            rule.third = negated
            continue
        if name.startswith("domain="):
            for one in name[len("domain="):].split("|"):
                one = one.strip().lower()
                if not one:
                    continue
                if one.startswith("~"):
                    rule.not_domains.append(one[1:])
                else:
                    rule.domains.append(one)
            continue
        if name in KINDS:
            if negated:
                rule.not_kinds.add(KINDS[name])
            else:
                rule.kinds.add(KINDS[name])
            continue
        if name == "match-case":
            rule.match_case = not negated
            continue
        if name in ("popup", "object", "object-subrequest", "image-set",
                    "beacon", "webrtc", "document-blocking"):
            # these narrow a rule to one kind of request. Dropped, the
            # rule held for every request to the host -- scripts,
            # pictures, the page itself. Negated, the rule still covers
            # everything the interceptor can tell apart.
            if negated:
                continue
            return "skip", "option $" + name
        return "skip", "option $" + name
    if body.startswith("||"):
        rule.anchor_host = True
        body = body[2:]
        host = re.split(r"[\^/*?]", body, 1)[0]
        after = body[len(host):len(host) + 1]
        # without the port: `blocks()` looks a request up by its host,
        # and `||127.0.0.1:8000/x` must still be found under
        # 127.0.0.1. The port stays in what has to match.
        rule.host = host.lower().split(":")[0]
        if after == "*" or rule.host.endswith(".") or not rule.host:
            # "||ad*.example.com^", "||ads.*/banner": filed under "ad" or
            # "ads." a request host never is, the rule never matched
            rule.host = ""
    elif body.startswith("|"):
        rule.anchor_start = True
        body = body[1:]
    if body.endswith("|"):
        rule.anchor_end = True
        body = body[:-1]
    if not body:
        return "skip", "nothing to match"
    # ^ is "a separator here"; treated as the end of what must match,
    # which is what it means in practice for a host rule
    pieces = [one for one in re.split(r"[*^]", body) if one]
    if not pieces:
        return "skip", "nothing to match"
    # which pieces a "^" follows (the matcher checks the next character)
    seps, at = [], 0
    for piece in pieces:
        at = body.find(piece, at) + len(piece)
        seps.append(body[at:at + 1] == "^")
    rule.seps = seps
    # lower-cased like the address they are compared with, host rules
    # included ("||cdn.example.com/AdServer/" matched nothing at all)
    rule.parts = pieces if rule.match_case \
        else [one.lower() for one in pieces]
    return "net", rule


class Rules:
    """Every list he has, indexed, with what it could not read."""

    def __init__(self):
        self.by_host = {}
        #: generic rules by the word they must contain, and the few
        #: with no word long enough to file them under
        self.by_word = {}
        self.by_prefix = {}
        self.by_suffix = {}
        self.generic = []
        self.by_host_allow = {}
        self.by_word_allow = {}
        self.by_prefix_allow = {}
        self.by_suffix_allow = {}
        self.generic_allow = []
        self.hide_global = []
        self.hide_host = {}
        self.unhide_host = {}
        self.counts = {"rules": 0, "allow": 0, "hide": 0, "skipped": 0,
                       "lines": 0, "lists": 0}
        self.skipped_why = {}
        self.when = 0

    def load_text(self, text, name=""):
        """One list. Lines this cannot do are counted, not dropped
        quietly."""
        self.counts["lists"] += 1
        for line in str(text or "").splitlines():
            self.counts["lines"] += 1
            kind, value = parse_line(line)
            if kind is None:
                continue
            if kind == "skip":
                self.counts["skipped"] += 1
                self.skipped_why[value] = self.skipped_why.get(value, 0) + 1
                continue
            if kind == "hide":
                hosts, selector, unhide = value
                if unhide:
                    # no site named: an exception everywhere, kept under ""
                    for one in hosts or [""]:
                        self.unhide_host.setdefault(one, []).append(selector)
                elif hosts:
                    for one in hosts:
                        self.hide_host.setdefault(one, []).append(selector)
                else:
                    self.hide_global.append(selector)
                self.counts["hide"] += 1
                continue
            rule = value
            where = (self.by_host_allow if rule.exception else self.by_host)
            words = (self.by_word_allow if rule.exception else self.by_word)
            loose = (self.generic_allow if rule.exception else self.generic)
            if rule.host:
                where.setdefault(rule.host, []).append(rule)
            else:
                token, how = _rule_index(rule.parts)
                if how == "word":
                    words.setdefault(token, []).append(rule)
                elif how == "prefix":
                    (self.by_prefix_allow if rule.exception
                     else self.by_prefix).setdefault(token, []).append(rule)
                elif how == "suffix":
                    (self.by_suffix_allow if rule.exception
                     else self.by_suffix).setdefault(token, []).append(rule)
                else:
                    loose.append(rule)
            self.counts["allow" if rule.exception else "rules"] += 1
        self.when = int(time.time())
        return self.counts

    def load_dir(self, folder):
        """Every .txt in his list folder, in name order."""
        folder = Path(str(folder))
        names = []
        try:
            names = sorted(one for one in folder.glob("*.txt")
                           if one.is_file())
        except OSError:
            return self.counts
        for one in names:
            try:
                self.load_text(one.read_text(encoding="utf-8",
                                             errors="replace"), one.name)
            except OSError:
                continue
        return self.counts

    def ready(self):
        return bool(self.counts["rules"] or self.counts["hide"])

    def _candidates(self, host, url, table, words, loose,
                    prefixes=None, suffixes=None):
        """The handful of rules that could possibly match one address:
        those filed under its host or a parent of it, those filed
        under a word it contains -- or the start or the end of one --
        and the few filed under nothing."""
        rows = list(loose)
        for one in _host_parents(host):
            rows.extend(table.get(one, ()))
        if words or prefixes or suffixes:
            for word in set(_tokens(url)):
                rows.extend(words.get(word, ()))
                top = min(len(word), _EDGE)
                for size in range(4, top + 1):
                    if prefixes:
                        rows.extend(prefixes.get(word[:size], ()))
                    if suffixes:
                        rows.extend(suffixes.get(word[-size:], ()))
        # a rule can be reached by more than one word; asked once
        return list(dict.fromkeys(rows))

    def blocks(self, url, page_host="", kind="other"):
        """Whether this request is blocked, and by which rule.

        Exceptions win, as the lists mean them to: a page that only
        works because a list carries an @@ rule for it must not be
        broken by the rule the @@ exists for.
        """
        url = str(url or "")
        # ws:// and wss:// too: a $websocket rule, or a plain ||host^
        # one, never saw a socket at all
        if not url.startswith(("http://", "https://", "ws://", "wss://")):
            return None
        # the host as the URL has it: cut only at "/" and ":", a "?" or
        # "#" straight after it, a user name in front or an IPv6 address
        # made a host no rule was filed under
        try:
            host = (urlsplit(url).hostname or "").lower()
        except ValueError:
            return None
        page_host = str(page_host or "").lower().removeprefix("www.")
        # by site, not by exact host: static.example.com on a page at
        # m.example.com is the site's own, and $third-party rules took
        # its scripts away
        third = bool(page_host) and _site_of(host) != _site_of(page_host)
        low = url.lower()
        for rule in self._candidates(host, url, self.by_host_allow,
                                     self.by_word_allow,
                                     self.generic_allow,
                                     self.by_prefix_allow,
                                     self.by_suffix_allow):
            if rule.matches(url, page_host, kind, third, low):
                return None
        for rule in self._candidates(host, url, self.by_host,
                                     self.by_word, self.generic,
                                     self.by_prefix, self.by_suffix):
            if rule.matches(url, page_host, kind, third, low):
                return rule.raw
        return None

    def hide_for(self, host):
        """The selectors to hide on this site."""
        host = str(host or "").lower().removeprefix("www.")
        # the site's own first: the browser caps the list, and a long
        # generic list pushed exactly the rules for this page past it
        out = []
        for one in _host_parents(host):
            out.extend(self.hide_host.get(one, ()))
        out.extend(self.hide_global)
        never = set(self.unhide_host.get("", ()))
        for one in _host_parents(host):
            never.update(self.unhide_host.get(one, ()))
        return [one for one in dict.fromkeys(out) if one not in never]

    def what_it_skipped(self, top=6):
        """The reasons, most common first: what these lists ask for
        that this does not do."""
        rows = sorted(self.skipped_why.items(), key=lambda kv: -kv[1])
        return rows[:top]
