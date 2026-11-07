#!/bin/sh
# Memory of one capped matrix run over time: the scope's cgroup
# memory.current every 2 s next to the row the run is on.
#   theme-audit/memprobe.sh <out> <theme-module|-> <url> <themes>
R=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd); cd "$R" || exit 1
OUT="$1"; MOD="$2"; URL="$3"; THEMES="$4"; mkdir -p "$OUT"
MODARG=""; [ "$MOD" != "-" ] && MODARG="--theme-module $MOD"
# never start under 7 GB free: the cap below is 6 GB
while [ "$(free -g | awk '/^Mem:/ {print $7}')" -lt 7 ]; do sleep 10; done
PY="$R/.venv/bin/python"
theme-audit/capped.sh -m 6000 "$PY" _sitematrix.py --out "$OUT" --sites "$URL" \
  --themes "$THEMES" --boot mocha $MODARG > "$OUT/stdout.txt" 2>&1 &
sleep 5
PID=$(pgrep -f "^$PY _sitematrix.py --out $OUT" | head -1)
CG=$(awk -F: '{print $3}' "/proc/$PID/cgroup")
while kill -0 "$PID" 2>/dev/null; do
  cur=$(cat "/sys/fs/cgroup$CG/memory.current" 2>/dev/null || echo 0)
  echo "$(date +%T) $((cur / 1048576)) MB | $(tail -1 "$OUT/log.txt" 2>/dev/null | cut -c1-90)" >> "$OUT/mem.log"
  sleep 2
done
echo "$(date +%T) exit" >> "$OUT/mem.log"
