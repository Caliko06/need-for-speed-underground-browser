#!/bin/sh
# Hopper in parallel, no click: HOP_DIR=<scratchpad> [HOP_WIN=n] hpar.sh <topic> ...
# (q_<topic>.py, rendered from queries.json by mkq.py into build/hopper/ when it is not in HOP_QDIR, writes build/hopper/<topic>.txt ending in "DONE", then closes its document).
# Any PE, not just Speed.exe (OWNER 2026-11-08: Mafia's game/Game.exe needs the same fan-out):
#   HOP_EXE=<path to the .exe>   what every window opens (default pc/Speed.exe, relative to HOP_REPO)
#   HOP_REPO=<repo root>         where build/hopper/ lives and where the script cds (default: this repo, ../../)
#   HOP_QDIR=<dir>               where a hand-made q_<topic>.py lives (default $HOP_REPO/tools/hopper); else mkq.py renders it
# FACT 2026-10-25 (Hopper 6.6.0-demo, PID 20369): an instance opened in the background (open -g -n, persistence off)
# keeps its license panel (697x335, "Try the Demo") off screen and still runs the open event + script (DONE in ~45 s,
# focus untouched). So nobody clicks; never bring a window to the front (the panel then blocks until a click).
# - HOP_WIN windows (default: one per topic, at most one per core) from the exact bundle /Applications/Hopper Disassembler.app
#   (~/Applications and ~/Desktop hold copies with the same id); the new PID is the one not running before.
# - Topics go round-robin to the windows; in each window they run one after another on the same PID. With less than
#   8 min left of its 30 min demo, the window is killed and a new one takes the rest (only our PIDs are killed).
# - Each topic: ONE Apple event (send.js: HoppOpEx + EXPY, loader WinPE; "PE" opens the Loader dialog) to that PID,
#   never retried, so a binary is never opened twice. The script first checks its document is Speed_<topic>.exe,
#   else it writes build/hopper/<topic>.wrong and does nothing.
# - HOP_STALL=s: a window whose output file has not grown for s seconds is killed and the topic left without DONE
#   (Hopper can hang inside one decompile); HOP_KEEP=1 keeps the old output so the script can resume after it.
# - Each window opens through ~/.claude/hooks/macgate.sh (the machine-wide gate; a Hopper window is ~100 MB, so 3 s apart).
dir=${HOP_DIR:?set HOP_DIR to the scratchpad}; ncpu=$(sysctl -n hw.ncpu); win=${HOP_WIN:-$(( $# < ncpu ? $# : ncpu ))}; B=${HOP_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}; cd "$B" || exit 1
S=$(cd "$(dirname "$0")" && pwd)    # send.js lives next to this script, not under $B (HOP_REPO may be another repo)
exe=${HOP_EXE:-pc/Speed.exe}; qdir=${HOP_QDIR:-$B/tools/hopper}; name=$(basename "$exe"); name=${name%.*}
APP="/Applications/Hopper Disassembler.app"; LIFE=1800; MINLEFT=480

prep() {    # topic -> exe copy + wrapper script that checks the document
  t=$1; q=$qdir/q_$t.py
  [ -f "$q" ] || { q=$B/build/hopper/q_$t.py; HOP_REPO=$B python3 "$S/mkq.py" "$S/queries.json" "$t" >/dev/null 2>&1 && [ -f "$q" ] || { echo "hpar: no query for $t"; return 1; }; }
  cp -c "$exe" "$dir/${name}_$t.exe"; [ -n "$HOP_KEEP" ] || rm -f "build/hopper/$t.txt"; rm -f "build/hopper/$t.wrong"
  cat > "$dir/w_$t.py" <<EOF
import os
_p = Document.getCurrentDocument().getExecutableFilePath() or ''
if os.path.basename(_p) != '${name}_$t.exe':
    open('$B/build/hopper/$t.wrong', 'w').write('WRONG DOC %s (wanted ${name}_$t.exe)\n' % _p)
else:
    exec(compile(open('$q').read(), '$q', 'exec'))
EOF
}

launch() {  # -> new PID in $pid, its start in $t0 (launches are serialized by the caller's lock)
  MACGATE_SETTLE=3 "$HOME/.claude/hooks/macgate.sh"
  while ! mkdir "$dir/hpar.lock" 2>/dev/null; do sleep 1; done
  before=$(pgrep -x "Hopper Disassembler")
  open -g -n -a "$APP" --args -ApplePersistenceIgnoreState YES; t0=$(date +%s)
  pid=""; for n in $(seq 40); do
    for p in $(pgrep -x "Hopper Disassembler"); do echo "$before" | grep -qx "$p" || pid=$p; done
    [ -n "$pid" ] && break; sleep 0.5
  done
  rmdir "$dir/hpar.lock"
  [ -n "$pid" ] && echo "$t0 $pid" >> build/hopper/launch.log
}

bye() {     # Hopper ignores a plain TERM at times and the window stays up (OWNER 2026-11-08): TERM, then KILL
  kill "$1" 2>/dev/null; sleep 2; kill -9 "$1" 2>/dev/null
}

window() {  # topics of one window, run in sequence; a fresh window when the demo time runs short
  pid=""; t0=0
  for t in "$@"; do
    if [ -z "$pid" ] || [ $(( LIFE - ($(date +%s) - t0) )) -lt $MINLEFT ] || ! kill -0 "$pid" 2>/dev/null; then
      [ -n "$pid" ] && bye "$pid"
      launch; [ -n "$pid" ] || { echo "hpar: no new Hopper process: $t not started"; continue; }
      echo "hpar: window PID $pid"
    fi
    prep "$t" || continue
    echo "hpar: PID $pid: $t: $(osascript -l JavaScript "$S/send.js" "$pid" "$dir/${name}_$t.exe" "$dir/w_$t.py" 900)"
    ts=$(date +%s)
    while ! grep -q '^DONE' "build/hopper/$t.txt" 2>/dev/null && [ ! -f "build/hopper/$t.wrong" ] \
          && [ $(( $(date +%s) - t0 )) -lt $LIFE ] && kill -0 "$pid" 2>/dev/null; do
      sleep 5
      m=$(stat -f %m "build/hopper/$t.txt" 2>/dev/null || echo 0); [ "$m" -gt "$ts" ] || m=$ts
      [ -n "$HOP_STALL" ] && [ $(( $(date +%s) - m )) -gt "$HOP_STALL" ] && { echo "hpar: PID $pid: $t stalled"; kill -9 "$pid"; break; }
    done
    echo "hpar: PID $pid: $t done: $(tail -1 "build/hopper/$t.txt" 2>/dev/null)$(cat "build/hopper/$t.wrong" 2>/dev/null)"
    sleep 3    # the script closes its document; give Hopper a moment before the next open
  done
  [ -n "$pid" ] && bye "$pid"
}

rmdir "$dir/hpar.lock" 2>/dev/null
i=0
while [ $i -lt "$win" ]; do
  topics=""; k=0
  for t in "$@"; do [ $((k % win)) -eq $i ] && topics="$topics $t"; k=$((k + 1)); done
  window $topics &
  i=$((i + 1))
done
wait
exit 0
