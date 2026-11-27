#!/bin/sh
# Assemble a tier from its computed units into exactly the files (and MANIFEST.sha256) that
# `sh code/run_all.sh --tier TIER --out OUT` writes on one machine.
#
#   sh cluster/merge.sh UNITS_FILE [--check]
#
# Refuses to start if any unit is missing or was produced by a different code version (cluster/units.py status
# lists them). The merge itself recomputes no unit; it reruns the unit tests and the cheap unsplit steps
# (x0, checks, x2split, catalog, extracts), which take minutes.
set -eu
UNITS="${1:?usage: sh cluster/merge.sh UNITS_FILE [--check]}"
CHECK="${2:-}"
CODE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PY="${PYTHON:-python3}"
TIER=$(sed -n 's/^# tier //p' "$UNITS")
OUT=$(sed -n 's/^# out //p' "$UNITS")
[ -n "$TIER" ] && [ -n "$OUT" ] || { echo "$UNITS is not a units file" >&2; exit 2; }
"$PY" "$CODE_DIR/cluster/units.py" status --units "$UNITS" || {
  echo "merge refused: some units are missing or stale (see the indices above); rerun them first" >&2; exit 1; }
exec "$PY" "$CODE_DIR/run_tier.py" --tier "$TIER" --out "$OUT" --jobs 1 --merge ${CHECK:+"$CHECK"}
