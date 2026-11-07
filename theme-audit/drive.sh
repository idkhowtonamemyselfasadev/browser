#!/bin/sh
# The matrix, one site per capped process, a few at a time.
#   theme-audit/drive.sh <outdir> [before|after]
# "before" measures git HEAD's theme_web.py, "after" the tree's.
# Parallelism is read from theme-audit/P before every launch (default
# 2), and a launch waits while less than 4 GB is available. A site
# already measured in a mode (its rows.jsonl exists and ends in
# "done") is skipped, so a run can be resumed.
R=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$R" || exit 1
OUT="$1"; MODE="${2:-after}"
[ -n "$OUT" ] || { echo "usage: drive.sh <outdir> [before|after]"; exit 2; }
mkdir -p "$OUT"
PY="$R/.venv/bin/python"
# the desktop has PyQt6 in its system python and no venv
[ -x "$PY" ] || PY="$(command -v python3)"
MOD=""
if [ "$MODE" = "before" ]; then
  git show HEAD:theme_web.py > "$OUT/theme_web.before.py"
  MOD="--theme-module $OUT/theme_web.before.py"
fi
DARKA="mocha,gruvbox,nord,dracula,terminal,steampunk,aero"
LIGHTA="latte,gruvbox-light,solarized-light,newspaper,papercolor,high-contrast"
slug() { printf '%s' "$1" | sed 's#^https\?://##; s#^www\.##' | tr -c 'a-z0-9.\n' '_' | cut -c1-60; }
wait_slot() {
  while :; do
    P=$(cat "${PFILE:-$R/theme-audit/P}" 2>/dev/null || echo 2)
    # the python processes only: the capped.sh and systemd-run wrappers
    # carry the same command line and counted double, so "2 at a time"
    # was one
    running=$(pgrep -fc "^$PY _sitematrix.py --out $OUT")
    avail=$(free -g | awk '/^Mem:/ {print $7}')
    if [ "$running" -lt "$P" ] && [ "$avail" -ge 4 ]; then return; fi
    sleep 5
  done
}
one() { # mode-folder, site, args...
  mode="$1"; d="$OUT/$1/$(slug "$2")"; site="$2"; shift 2
  if [ -f "$d/log.txt" ] && grep -q "^.* done:" "$d/log.txt"; then return; fi
  rm -rf "$d"; mkdir -p "$d"
  wait_slot
  echo "$(date +%H:%M:%S) start $mode $site" >> "$OUT/drive.log"
  "$R/theme-audit/capped.sh" -m 3500 "$PY" _sitematrix.py --out "$d" --sites "$site" $MOD "$@" \
    > "$d/stdout.txt" 2>&1 &
  sleep 3
}
grep -v '^#' "$R/theme-audit/sites.txt" | grep -v '^$' | while read -r site; do
  one live-dark  "$site" --themes dark --boot mocha
  one live-light "$site" --themes light --boot latte
  one fresh-dark "$site" --themes "$DARKA" --boot mocha --fresh
  one fresh-light "$site" --themes "$LIGHTA" --boot latte --fresh
done
while [ "$(pgrep -fc "^$PY _sitematrix.py --out $OUT")" -gt 0 ]; do sleep 10; done
echo "$(date +%H:%M:%S) all done" >> "$OUT/drive.log"
