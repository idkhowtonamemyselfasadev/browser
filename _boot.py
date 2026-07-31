#!/usr/bin/env python3
"""Boot the real Browser offscreen against scratch data files, take a
screenshot if asked, and never go near your own vault."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
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
