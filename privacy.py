"""Privacy — what a page is allowed to ask of the network and of you.

A sibling module like theme_web.py and capture.py, loaded the same safe
way: without this file the browser starts and the privacy switches are
simply not there.

What is here works on navigations: `check_request` is called from
WebPage.acceptNavigationRequest for the page and for every frame in it,
and it can refuse one or clean the tracking out of its address. The
comment on that function says why it is not the engine's request
interceptor, which is where this belongs and which crashes this PyQt
build; FEATURES.md says what that costs.

Nothing here talks to the internet by itself: the block list is a file on
this machine, and it is only read when he switches blocking on.
"""

import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from PyQt6.QtCore import QUrl

# the same list the address bar's "copy clean address" uses; kept here as
# a plain tuple so this module stands on its own
TRACKING = (
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_social", "utm_brand", "fbclid", "gclid",
    "dclid", "gbraid", "wbraid", "msclkid", "yclid", "igshid", "igsh",
    "mc_cid", "mc_eid", "mkt_tok", "vero_id", "_hsenc", "_hsmi",
    "ref_src", "ref_url", "s_kwcid", "trk", "trkCampaign", "sc_channel",
    "sc_campaign", "cmpid", "icid", "ncid", "oly_enc_id",
)

# a small, honest starting list: the big trackers, the ones that are on
# every second page. It is not an ad blocker's list and does not pretend
# to be one — his own hosts go in config["blockHosts"].
DEFAULT_BLOCK = (
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "google-analytics.com", "analytics.google.com", "adservice.google.com",
    "scorecardresearch.com", "quantserve.com", "criteo.com", "criteo.net",
    "taboola.com", "outbrain.com", "adnxs.com", "rubiconproject.com",
    "pubmatic.com", "openx.net", "casalemedia.com", "33across.com",
    "bluekai.com", "demdex.net", "everesttech.net", "hotjar.com",
    "mixpanel.com", "segment.io", "amplitude.com", "fullstory.com",
    "clarity.ms", "yandex.ru", "facebook.net",
)


def _host_of(url):
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def matches(host, domains):
    """A host is matched by a domain in the list, or by any of its
    parents: ads.doubleclick.net is matched by doubleclick.net."""
    host = (host or "").lower().removeprefix("www.")
    for d in domains:
        d = (d or "").lower().strip().removeprefix("www.")
        if d and (host == d or host.endswith("." + d)):
            return True
    return False


def strip_tracking(url):
    """The same address with the visitor-tracking parameters gone, or
    the same string when there was nothing to take off."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.query:
        return url
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in TRACKING]
    if len(kept) == len(parse_qsl(parts.query, keep_blank_values=True)):
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(kept), parts.fragment))


def is_local(host):
    """Is this address on this machine or on the home network?

    Names first (localhost, anything .local or .home.arpa, a bare name
    with no dot — a router's own name), then the address itself."""
    host = (host or "").lower().strip("[]")
    if not host:
        return False
    if host == "localhost" or host.endswith((".localhost", ".local",
                                             ".home.arpa", ".internal")):
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_reserved)


class Report:
    """What was turned away or cleaned up, for the page menu to show.
    Counts, not a log: a list of every address a page ever asked for is
    a record of his browsing, and keeping one to show him how private he
    is would be its own joke."""

    def __init__(self):
        self.blocked = 0
        self.stripped = 0
        self.by_host = {}

    def add_block(self, host):
        self.blocked += 1
        self.by_host[host] = self.by_host.get(host, 0) + 1

    def total(self):
        return self.blocked + self.stripped

    def worst(self, n=8):
        return sorted(self.by_host.items(), key=lambda kv: -kv[1])[:n]


def check_request(config, url, page_url):
    """Should this navigation happen, and to what address?

    Returns (allow, url). Called from WebPage.acceptNavigationRequest —
    the UI thread, with no pointer kept on the Qt side.

    This is deliberately *not* a QWebEngineUrlRequestInterceptor. That
    is the engine's hook for every request a page makes, and it is the
    right place for this — but a Python interceptor installed on a
    profile crashes this PyQt build at interpreter exit, measured at
    five crashes in six runs with an interceptor that did nothing at
    all, and none in six without it. The same goes for the cookie
    store's filter. So the rules live here, where they cover what a
    page navigates to (and what its frames navigate to) and not the
    pictures and scripts it fetches. What that costs is written down in
    FEATURES.md next to the blocking features that are marked skipped.
    """
    host = (url.host() or "").lower()
    page_host = (page_url.host() or "").lower() if page_url is not None else ""
    if url.scheme() not in ("http", "https"):
        return True, url

    # 1. a public page may not reach into the home network. A page on
    #    the web sending a frame at 192.168.1.1 is looking at his
    #    router, and there is no good reason for it.
    if (config.get("blockLocal", True) and is_local(host)
            and page_host and not is_local(page_host)):
        return False, url

    # 2. the tracking parameters, taken off on the way out
    if config.get("stripTracking", False):
        text = url.toString()
        clean = strip_tracking(text)
        if clean != text:
            return True, QUrl(clean)
    return True, url
