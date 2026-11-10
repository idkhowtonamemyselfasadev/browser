#!/bin/sh
# Run a command under a memory cap, so a browser that runs away kills
# only itself. Uses a systemd --user scope when the user bus answers;
# otherwise a watchdog that sums the RSS of the command's whole process
# tree every 2 s and kills it past the cap. Either way the command is
# niced. The cap is in MB (default 3500); the scope also stops at
# CAPPED_TASKS threads+processes (default 1500), so a rig that keeps
# relaunching itself hits a wall instead of the whole machine.
#   theme-audit/capped.sh [-m MB] <cmd...>
CAP=3500
if [ "$1" = "-m" ]; then CAP="$2"; shift 2; fi
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
if systemd-run --user --scope -p MemoryMax=1M --quiet true >/dev/null 2>&1; then
  exec systemd-run --user --scope -p MemoryMax="${CAP}M" -p MemorySwapMax=0 -p TasksMax="${CAPPED_TASKS:-1500}" \
    --quiet nice -n 10 "$@"
fi
nice -n 10 "$@" &
PID=$!
tree() { # all pids under $1
  echo "$1"
  for c in $(pgrep -P "$1"); do tree "$c"; done
}
while kill -0 "$PID" 2>/dev/null; do
  sleep 2
  TOTAL=0
  for p in $(tree "$PID"); do
    r=$(awk '/VmRSS/ {print $2}' "/proc/$p/status" 2>/dev/null)
    TOTAL=$((TOTAL + ${r:-0}))
  done
  if [ $((TOTAL / 1024)) -gt "$CAP" ]; then
    echo "capped.sh: $((TOTAL / 1024)) MB > $CAP MB, killing pid $PID tree" >&2
    for p in $(tree "$PID"); do kill -9 "$p" 2>/dev/null; done
    wait "$PID" 2>/dev/null
    exit 137
  fi
done
wait "$PID"
