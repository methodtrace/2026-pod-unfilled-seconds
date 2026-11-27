#!/bin/sh
# Submit a tier to Grid Engine as LANES multi-core lanes plus one held final merge job.
#
#   sh cluster/submit.sh OUT LANES SLOTS QUEUE [HOURS]
#
#   OUT     output directory on a filesystem the compute nodes share (created if missing)
#   LANES   number of array tasks; lane k computes the units with (index - 1) mod LANES == k - 1
#   SLOTS   cores per lane (qsub -pe smp SLOTS); each lane runs SLOTS units at a time
#   QUEUE   queue name (qsub -q QUEUE)
#   HOURS   run time limit per job, whole hours (qsub -l h_rt=HOURS:00:00); default: twice the slowest lane's
#           estimate (at least 2 h) when the tier has per-unit estimates, else 2
#
# Environment: TIER (default full), PYTHON (interpreter, default python3; must be 3.9 or newer; it is resolved
# to an absolute path and passed to every lane and to the final job), TASKS (array range to submit, default
# 1-LANES; for example TASKS=2 resubmits lane 2 only). Run from anywhere; the jobs run in the code/ directory.
# Makes OUT/.cache/units-TIER.txt if it is missing, prints the lane split, submits, prints the job IDs.
set -eu

usage() {
  echo "usage: sh cluster/submit.sh OUT LANES SLOTS QUEUE [HOURS]" >&2
  echo "       (environment: TIER=full|fullsmoke|..., PYTHON=/path/to/python3, TASKS=1-LANES)" >&2
  exit 2
}
[ $# -ge 4 ] && [ $# -le 5 ] || usage
OUT_ARG=$1
LANES=$2
SLOTS=$3
QUEUE=$4
HOURS=${5:-}
TIER=${TIER:-full}
TASKS=${TASKS:-1-$LANES}
is_count() { case "$1" in ''|*[!0-9]*|0*) return 1 ;; *) return 0 ;; esac; }
is_count "$LANES" || { echo "LANES must be a positive whole number (got '$LANES')" >&2; exit 2; }
is_count "$SLOTS" || { echo "SLOTS must be a positive whole number (got '$SLOTS')" >&2; exit 2; }
[ -z "$HOURS" ] || is_count "$HOURS" || { echo "HOURS must be a positive whole number (got '$HOURS')" >&2; exit 2; }
[ -n "$QUEUE" ] || { echo "QUEUE must not be empty" >&2; exit 2; }
case "$TASKS" in
  *[!0-9-]*|'') echo "TASKS must look like 2 or 1-$LANES (got '$TASKS')" >&2; exit 2 ;;
esac
command -v qsub >/dev/null 2>&1 || { echo "qsub not found on PATH: run this on a Grid Engine submit host" >&2; exit 2; }

CODE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

PY=${PYTHON:-python3}
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "interpreter '$PY' not found. Point PYTHON at a Python 3.9 or newer, for example:" >&2
  echo "  PYTHON=/path/to/python3.11 sh cluster/submit.sh $*" >&2
  exit 2
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
  echo "Python 3.9 or newer is required; '$PY' is $("$PY" --version 2>&1)." >&2
  echo "Point PYTHON at another interpreter (it must be reachable from the compute nodes), for example:" >&2
  echo "  PYTHON=/path/to/python3.11 sh cluster/submit.sh $*" >&2
  exit 2
fi
# one interpreter for every lane and the final job: its absolute path is exported to all of them
PYTHON=$("$PY" -c 'import sys; print(sys.executable)')
export PYTHON

mkdir -p "$OUT_ARG"
OUT=$(CDPATH= cd -- "$OUT_ARG" && pwd)
UNITS="$OUT/.cache/units-$TIER.txt"
for v in "$OUT" "$CODE_DIR" "$PYTHON"; do
  case "$v" in
    *,*|*' '*) echo "paths passed to qsub -v must not contain commas or spaces: '$v'" >&2; exit 2 ;;
  esac
done

if [ ! -f "$UNITS" ]; then
  "$PYTHON" "$CODE_DIR/cluster/units.py" make --tier "$TIER" --out "$OUT"
else
  echo "using existing units file $UNITS"
fi
UT=$(sed -n 's/^# tier //p' "$UNITS")
[ "$UT" = "$TIER" ] || { echo "$UNITS is for tier '$UT', not '$TIER'" >&2; exit 2; }
# plan also refuses if the code changed after the units were listed
"$PYTHON" "$CODE_DIR/cluster/units.py" plan --units "$UNITS" --lanes "$LANES" --slots "$SLOTS"
if [ -z "$HOURS" ]; then
  HOURS=$("$PYTHON" "$CODE_DIR/cluster/units.py" plan --units "$UNITS" --lanes "$LANES" --slots "$SLOTS" --print-hours)
  [ "$HOURS" -gt 0 ] || HOURS=2
fi

LOGDIR="$OUT/.cache/gridengine"
mkdir -p "$LOGDIR/sge"
VARS="UNITS=$UNITS,LANES=$LANES,CODE_DIR=$CODE_DIR,PYTHON=$PYTHON"
cd "$CODE_DIR"
LANE_OUT=$(qsub -terse -q "$QUEUE" -t "$TASKS" -pe smp "$SLOTS" -l "h_rt=$HOURS:00:00" -o "$LOGDIR/sge/" \
  -v "$VARS" cluster/lane.sh)
LANE_JOB=${LANE_OUT%%.*}
is_count "$LANE_JOB" || { echo "could not read the lane job ID from qsub output: $LANE_OUT" >&2; exit 1; }
FINAL_OUT=$(qsub -terse -q "$QUEUE" -hold_jid "$LANE_JOB" -pe smp 1 -l "h_rt=$HOURS:00:00" -o "$LOGDIR/sge/" \
  -v "$VARS" cluster/final.sh)
FINAL_JOB=${FINAL_OUT%%.*}
echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') tier $TIER lanes $LANES tasks $TASKS slots $SLOTS h_rt $HOURS python $PYTHON lane-job $LANE_JOB final-job $FINAL_JOB" \
  >> "$LOGDIR/submissions.txt"
echo "interpreter: $PYTHON ($("$PYTHON" --version 2>&1))"
echo "lane array job: $LANE_JOB (tasks $TASKS of $LANES, $SLOTS slots each, h_rt $HOURS h)"
echo "final merge job: $FINAL_JOB (held until job $LANE_JOB ends)"
echo "progress: sh cluster/status.sh $OUT $LANES"
