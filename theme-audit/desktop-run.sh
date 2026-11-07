#!/bin/sh
# On the desktop: run _profileshots.py from a profile copy, niced, in
# the background. Synced here through pcsync; called over desktop.sh.
#   desktop-run.sh start <copydir> <urls>   |  status <copydir>  |  stop  |  dump <copydir>
cd "$HOME/claude/browser-linux" || exit 1
case "$1" in
  start)
    T="$2"; U="$3"
    pkill -f '[_]profileshots.py' 2>/dev/null; sleep 1
    rm -rf "$T/out"; mkdir -p "$T/out"
    nohup nice -n 10 python3 _profileshots.py --copy "$T" --out "$T/out" --urls "$U" \
      > "$T/out.log" 2>&1 < /dev/null &
    echo "started pid $!"
    ;;
  status)
    T="$2"
    pgrep -af '[_]profileshots.py' | cut -c1-70
    grep '^[0-9]' "$T/out.log" | tail -4 | cut -c1-120
    ls "$T/out" | wc -l
    ;;
  dump)
    T="$2"
    pkill -USR1 -f '[_]profileshots.py'; sleep 2
    grep -A30 'Current thread' "$T/out.log" | head -40
    ;;
  stop)
    pkill -f '[_]profileshots.py'; echo stopped
    ;;
esac
