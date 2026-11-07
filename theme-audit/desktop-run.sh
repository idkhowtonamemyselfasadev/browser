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
  after-restart)
    # the site x theme matrix, afresh, under OUT (outside the synced tree)
    OUTD="$2"; P="${3:-2}"
    pkill -f "[d]rive.sh $OUTD"; pkill -f "[_]sitematrix.py --out $OUTD"; sleep 2
    rm -rf "$OUTD"; mkdir -p "$OUTD"; echo "$P" > "$OUTD/P"
    PFILE="$OUTD/P" nohup theme-audit/drive.sh "$OUTD" after > "$OUTD/drive.out" 2>&1 < /dev/null &
    sleep 3; cat "$OUTD/drive.log"
    ;;
  after-status)
    OUTD="$2"
    tail -2 "$OUTD/drive.log"
    for m in live-dark live-light fresh-dark fresh-light; do echo "$m: $(ls "$OUTD/$m" 2>/dev/null | wc -l)"; done
    ;;
esac
