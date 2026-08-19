#!/usr/bin/env python3
"""Boot the real Browser offscreen against scratch data files, take a
screenshot if asked, and never go near your own vault."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# no browser booted for a test or a screenshot goes looking for library
# updates: a real dnf/pip per boot would be slow, would depend on what the
# distribution is shipping this morning, and could raise a toast over a
# window under assertion. runall.sh sets this for its own runs, but a bare
# `python3 test_wizard.py` (which stays up past LIB_FIRST_MS) would arm and
# fire a real check without it -- so it belongs here too.
os.environ.setdefault("BROWSER_NO_LIB_CHECK", "1")
SCRATCH = Path(tempfile.mkdtemp(prefix="browsershot-"))
os.environ["XDG_DATA_HOME"] = str(SCRATCH / "share")
os.environ["XDG_CONFIG_HOME"] = str(SCRATCH / "config")
os.environ["XDG_CACHE_HOME"] = str(SCRATCH / "cache")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser as B  # noqa: E402

B.CONFIG_FILE = SCRATCH / "config.json"
B.HISTORY_FILE = SCRATCH / "history.json"
B.DOWNLOADS_FILE = SCRATCH / "downloads.json"
B.HOSTS_FILE = SCRATCH / "hosts.json"
B.BOOKMARKS_FILE = SCRATCH / "bookmarks.json"
SCRATCH.mkdir(parents=True, exist_ok=True)
# Vault Password is opt-in, and a scratch config is a fresh install, so
# it would default off and take the whole feature with it. Every suite
# in here is testing that feature: switch it on before Browser() reads
# it, which happens at profile-build time, not on first use.
if not B.CONFIG_FILE.exists():
    B.CONFIG_FILE.write_text(json.dumps({"vaultPassword": True}))
