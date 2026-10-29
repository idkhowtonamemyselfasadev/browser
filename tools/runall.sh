#!/bin/sh
# The whole offscreen suite, in one go, with a tail of each run.
# Everything here redirects its own data into scratch; nothing touches
# the vault or the config of the browser you actually use.
#
# The exit status has to come from python, not from tail. Piping a test
# straight into `tail` reports tail's status, which is always 0 -- so
# every failure, every crash and every timeout read as a pass, and the
# suite said "all green" while it was not. It is written out to a file
# and tailed afterwards for exactly that reason.
R=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$R" || exit 1
export QT_QPA_PLATFORM=offscreen
# no browser started in here goes looking for library updates: a real
# dnf per test would be slow, would depend on what the distribution is
# shipping this morning, and could raise a toast over a window another
# test is inspecting. test_libs drives that check by hand instead.
export BROWSER_NO_LIB_CHECK=1

OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
bad=""

missing=""

# A name in a list below with no file behind it used to be skipped by a
# bare `|| continue`, which says nothing. That is how a suite can be on
# disk, in the port set, and never run: test_offpalette, test_barmarks
# and test_barmargins were all in that state on 2026-10-29, found by
# browser-mac-8f on their own tree. Skipping is still right -- an
# edition need not carry every suite -- but it is reported at the end
# so the next one is visible instead of silent.
skip() {
  missing="$missing $1"
}

run() {
  echo "=== $1 ==="
  timeout 900 python "$1" > "$OUT/log" 2>&1
  rc=$?
  tail -3 "$OUT/log"
  echo "exit=$rc"
  [ "$rc" -eq 0 ] || bad="$bad $2"
}

# The static guards first. Neither opens a window and both finish in
# seconds, and both answer a question about the whole tree rather than
# about one feature -- "does any page call a Bridge method that is not
# there", "does any colour this file asks for exist". A broken one of
# those is worth knowing before the hour of browser boots below, not
# after it.
for t in test_bridgecalls.py test_themetokens.py test_uistrings.py test_idn.py \
         test_jssilence.py test_offpalette.py test_barmarks.py \
         test_capability.py \
         test_updatecheck.py test_downloaddir.py; do
  [ -f "$t" ] || { skip "$t"; continue; }
  run "$t" "$t"
done

for t in test_page.py test_newtab.py test_panes.py test_paneload.py \
         test_vaultoff.py \
         test_theme.py test_trust.py test_vault.py test_vaultguard.py \
         test_master.py test_masterrace.py test_providers.py \
         test_async.py test_upgrade.py test_op_page.py test_toolbar.py \
         test_wizard.py test_contrast.py test_themefix.py \
         test_favorites.py test_favclip.py test_update.py \
         test_libs.py test_looks.py test_navguard.py test_external.py \
         test_lifecycle.py test_deadtab.py test_libguard.py test_clicks.py \
         test_bpgame.py test_permreload.py test_callguard.py test_agent.py \
         test_saveimage.py test_screenshare.py test_sitetheme_render.py \
         test_tabwork.py test_tabwork2.py test_bookmarks2.py \
         test_addressbar.py \
         test_pagetools.py test_media.py \
         test_capture.py test_privacy.py test_pageguard.py \
         test_privacy2.py test_desk.py test_reading2.py \
         test_media2.py test_games.py test_forms.py test_downloads.py \
         test_bar.py test_dev.py test_look2.py test_a11y.py test_nav2.py test_perf2.py test_capture2.py test_keys2.py test_agent2.py test_read3.py test_privacy3.py test_marks3.py test_tools3.py test_block3.py test_gaps3.py test_setpage.py test_gpu.py \
         test_devtools.py test_keyboard.py \
         test_agentops.py test_reading.py test_gaming.py test_files.py \
         test_perf.py test_sitelook.py test_winbranch.py \
         test_histrender.py test_histicon.py test_sidebar.py \
         test_daystep.py test_paintcontrast.py test_palette.py \
         test_sleep.py test_panecache.py test_barmargins.py; do
  [ -f "$t" ] || { skip "$t"; continue; }
  run "$t" "$t"
done

cd "$R/tests" || exit 1
for t in test_twostep.py test_round3.py test_msaccounts.py test_identbox.py \
         test_subdomain.py test_acctpick.py test_private.py \
         test_masterlock.py test_masterwizard.py; do
  [ -f "$t" ] || { skip "tests/$t"; continue; }
  run "$t" "tests/$t"
done

cd "$R" || exit 1
echo "=== invariants ==="
timeout 900 python .github/scripts/invariant_checks.py > "$OUT/log" 2>&1
rc=$?
tail -4 "$OUT/log"
echo "exit=$rc"
[ "$rc" -eq 0 ] || bad="$bad invariants"

if [ -n "$missing" ]; then
  echo "NOT RUN (named here, no file):$missing"
fi
# and the other direction: a suite on disk that no list names. That is
# the one that bit -- a guard nobody runs is a guard that is not there.
unlisted=""
for f in test_*.py; do
  grep -q "$f" "$0" || unlisted="$unlisted $f"
done
for f in tests/test_*.py; do
  grep -q "$(basename "$f")" "$0" || unlisted="$unlisted $f"
done
if [ -n "$unlisted" ]; then
  echo "ON DISK BUT IN NO LIST:$unlisted"
  bad="$bad unlisted-suites"
fi

if [ -n "$bad" ]; then
  echo "FAILED:$bad"
  exit 1
fi
echo "all green"
