#!/bin/bash
# One Grid Engine array task = one lane: lane $SGE_TASK_ID of $LANES computes the units with index i where
# (i - 1) mod LANES == SGE_TASK_ID - 1, $NSLOTS at a time (one core each). Submitted by cluster/submit.sh, which
# passes the queue, the slot count, the run time limit and the log path under OUT on the qsub command line
# (Grid Engine does not expand variables in the #$ lines below, so the -o here is only a fallback, and the
# command-line options override every #$ default):
#
#   qsub -terse -q QUEUE -t 1-LANES -pe smp SLOTS -l h_rt=HOURS:00:00 -o OUT/.cache/gridengine/sge \
#     -v UNITS=...,LANES=...,CODE_DIR=...,PYTHON=... cluster/lane.sh
#
# Units already cached are skipped, a failed unit does not stop the lane, and the lane exits 1 at the end if any
# unit failed (listed in OUT/.cache/gridengine/failed-lane-K.txt). Resubmitting a lane is always safe.
#
#$ -N sim-lane
#$ -S /bin/bash
#$ -cwd
#$ -j y
#$ -o sim-lane.log
#$ -pe smp 1
#$ -l h_rt=02:00:00

set -eu
set -o pipefail
: "${UNITS:?UNITS (the units file) is not set; submit with cluster/submit.sh}"
: "${LANES:?LANES is not set; submit with cluster/submit.sh}"
: "${CODE_DIR:?CODE_DIR is not set; submit with cluster/submit.sh}"
: "${SGE_TASK_ID:?not a Grid Engine array task (SGE_TASK_ID is not set)}"
PY="${PYTHON:-python3}"
WORKERS="${NSLOTS:-1}"
if [ ! -f "$CODE_DIR/run_tier.py" ]; then
  echo "CODE_DIR=$CODE_DIR is not the code/ directory (run_tier.py not found)" >&2
  exit 2
fi
OUT=$(sed -n 's/^# out //p' "$UNITS")
[ -n "$OUT" ] || { echo "$UNITS is not a units file" >&2; exit 2; }
LOGDIR="$OUT/.cache/gridengine"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/lane-$SGE_TASK_ID.log"
{
  echo "=== lane $SGE_TASK_ID of $LANES, job ${JOB_ID:-?}, host $(uname -n), $WORKERS slots, $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  "$PY" "$CODE_DIR/cluster/units.py" run-lane --units "$UNITS" --lane "$SGE_TASK_ID" --lanes "$LANES" \
    --workers "$WORKERS"
} 2>&1 | tee -a "$LOG"
