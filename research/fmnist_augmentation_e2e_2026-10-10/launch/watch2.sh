#!/bin/bash
# Session-2 copy of watch.sh (process check matches launcher.py and launcher_resume_*.py). Emits a line whenever the project's stage, run statuses or task statuses change, or the backend dies.
cd "$(dirname "$0")"
prev=""
while true; do
  out=$(bash st.sh 2>&1)
  sig=$(echo "$out" | grep -E "^project|^  run|^  tasks" | sed -E 's/now=[0-9:]+Z//; s/\([0-9.]+m\)//; s/phase=[^ ]+//')
  if [ "$sig" != "$prev" ]; then
    echo "$out" | grep -E "^project|^  run .*(running|error)|^  tasks|note:|^  spend|ERR=" | tr '\n' ' | '; echo
    prev=$sig
  fi
  if ! wsl -d Ubuntu -- pgrep -f "launch/launcher" >/dev/null; then echo "BACKEND PROCESS NOT RUNNING"; fi
  sleep 90
done
