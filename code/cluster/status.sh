#!/bin/sh
# Progress of a Grid Engine run started with cluster/submit.sh.
#
#   sh cluster/status.sh OUT [LANES] [LINES]
#
# Prints the counts of done, missing and stale units (overall and per lane), the failed units each lane
# reported, the tail (LINES lines, default 5) of every lane log and of the final merge log, and the last
# submissions. LANES defaults to the value of the last submission. Environment: TIER (default: the units file
# found in OUT/.cache), PYTHON (default python3).
set -eu
[ $# -ge 1 ] && [ $# -le 3 ] || { echo "usage: sh cluster/status.sh OUT [LANES] [LINES]" >&2; exit 2; }
OUT=$(CDPATH= cd -- "$1" && pwd)
LANES=${2:-}
LINES=${3:-5}
CODE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PY=${PYTHON:-python3}
LOGDIR="$OUT/.cache/gridengine"
if [ -n "${TIER:-}" ]; then
  UNITS="$OUT/.cache/units-$TIER.txt"
else
  set -- "$OUT"/.cache/units-*.txt
  [ -f "$1" ] || { echo "no units file in $OUT/.cache (submit with cluster/submit.sh first)" >&2; exit 2; }
  [ $# -eq 1 ] || { echo "several units files in $OUT/.cache; set TIER" >&2; exit 2; }
  UNITS=$1
fi
if [ -z "$LANES" ] && [ -f "$LOGDIR/submissions.txt" ]; then
  LANES=$(tail -n 1 "$LOGDIR/submissions.txt" | sed -n 's/.* lanes \([0-9][0-9]*\) .*/\1/p')
fi

set +e
if [ -n "$LANES" ]; then
  "$PY" "$CODE_DIR/cluster/units.py" status --units "$UNITS" --lanes "$LANES"
else
  "$PY" "$CODE_DIR/cluster/units.py" status --units "$UNITS"
fi
RC=$?
set -e

echo
FAILED=0
for f in "$LOGDIR"/failed-lane-*.txt; do
  [ -f "$f" ] || continue
  FAILED=1
  echo "failed units reported by $(basename "$f" .txt):"
  sed 's/^/  /' "$f"
done
[ "$FAILED" -eq 1 ] || echo "no lane reported a failed unit"

for f in "$LOGDIR"/lane-*.log "$LOGDIR"/final.log; do
  [ -f "$f" ] || continue
  echo
  echo "--- $(basename "$f") (last $LINES lines)"
  tail -n "$LINES" "$f"
done
if [ -f "$OUT/MANIFEST.sha256" ]; then
  echo
  echo "manifest: $OUT/MANIFEST.sha256 ($(wc -l < "$OUT/MANIFEST.sha256" | tr -d ' ') files)"
fi
if [ -f "$LOGDIR/submissions.txt" ]; then
  echo
  echo "--- submissions (last 3)"
  tail -n 3 "$LOGDIR/submissions.txt"
fi
exit $RC
