#!/bin/sh
# Run one tier of the pod simulator: tests, then the tier's experiments, then a manifest.
#
#   sh code/run_all.sh --tier quick|narrow|full|fullsmoke [--out DIR] [--check] [--jobs N] [--list]
#   (fullsmoke runs the full tier's code paths on a tiny grid, in a few minutes; it is a test, not a result tier)
#
#   --out DIR   output directory (default ./podsim-run-<tier>); nothing is written anywhere else
#   --check     compare DIR/MANIFEST.sha256 with code/expected/MANIFEST-<tier>.sha256
#   --jobs N    worker processes (default 2)
#   --list      print the scenario catalog (and what the full tier skips) and exit
#
# Needs only python3 >= 3.9 (standard library). POSIX sh; works with macOS /bin/sh.
set -e

TIER=""
OUT=""
CHECK=""
JOBS="${PODSIM_JOBS:-2}"
LIST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tier) TIER="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --check) CHECK="--check"; shift ;;
    --jobs) JOBS="$2"; shift 2 ;;
    --list) LIST="--list"; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
case "$TIER" in
  quick|narrow|full|fullsmoke) ;;
  *) echo "usage: sh code/run_all.sh --tier quick|narrow|full|fullsmoke [--out DIR] [--check] [--jobs N] [--list]" >&2; exit 2 ;;
esac
[ -n "$OUT" ] || OUT="./podsim-run-$TIER"

PY="${PYTHON:-python3}"
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
  echo "python3 >= 3.9 is required (found: $("$PY" --version 2>&1))" >&2
  exit 2
fi

CODE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -n "$LIST" ]; then
  exec "$PY" "$CODE_DIR/run_tier.py" --tier "$TIER" --out "$OUT" --list
fi
mkdir -p "$OUT"
OUT_ABS=$(CDPATH= cd -- "$OUT" && pwd)

set +e
"$PY" "$CODE_DIR/run_tier.py" --tier "$TIER" --out "$OUT_ABS" --jobs "$JOBS" $CHECK
STATUS=$?
set -e
exit $STATUS
