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

OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
bad=""

run() {
  echo "=== $1 ==="
  timeout 900 python "$1" > "$OUT/log" 2>&1
  rc=$?
  tail -3 "$OUT/log"
  echo "exit=$rc"
  [ "$rc" -eq 0 ] || bad="$bad $2"
}

for t in test_page.py test_newtab.py test_panes.py test_paneload.py \
         test_vaultoff.py \
         test_theme.py test_trust.py test_vault.py test_vaultguard.py \
         test_master.py test_masterrace.py test_providers.py \
         test_async.py test_upgrade.py test_op_page.py test_toolbar.py \
         test_wizard.py test_contrast.py test_themefix.py \
         test_favorites.py test_favclip.py test_update.py; do
  [ -f "$t" ] || continue
  run "$t" "$t"
done

cd "$R/tests" || exit 1
for t in test_twostep.py test_round3.py test_msaccounts.py test_identbox.py \
         test_subdomain.py test_acctpick.py test_private.py \
         test_masterlock.py test_masterwizard.py; do
  [ -f "$t" ] || continue
  run "$t" "tests/$t"
done

cd "$R" || exit 1
echo "=== invariants ==="
timeout 900 python .github/scripts/invariant_checks.py > "$OUT/log" 2>&1
rc=$?
tail -4 "$OUT/log"
echo "exit=$rc"
[ "$rc" -eq 0 ] || bad="$bad invariants"

if [ -n "$bad" ]; then
  echo "FAILED:$bad"
  exit 1
fi
echo "all green"
