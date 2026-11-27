#!/bin/bash
# The final Grid Engine job: held until every lane task has ended (qsub -hold_jid LANE_JOB_ID), then merges the
# cached units into exactly the files a single-machine run writes, and writes OUT/MANIFEST.sha256. Submitted by
# cluster/submit.sh:
#
#   qsub -terse -q QUEUE -hold_jid LANE_JOB_ID -pe smp 1 -l h_rt=HOURS:00:00 -o OUT/.cache/gridengine/sge \
#     -v UNITS=...,CODE_DIR=...,PYTHON=... cluster/final.sh
#
# If a lane failed or was killed, the merge refuses (cluster/merge.sh lists the missing units) and this job
# exits 1; resubmit with cluster/submit.sh (cached units are skipped) and a new final job is queued.
#
#$ -N sim-final
#$ -S /bin/bash
#$ -cwd
#$ -j y
#$ -o sim-final.log
#$ -pe smp 1
#$ -l h_rt=02:00:00

set -eu
set -o pipefail
: "${UNITS:?UNITS (the units file) is not set; submit with cluster/submit.sh}"
: "${CODE_DIR:?CODE_DIR is not set; submit with cluster/submit.sh}"
PYTHON="${PYTHON:-python3}"
export PYTHON
OUT=$(sed -n 's/^# out //p' "$UNITS")
TIER=$(sed -n 's/^# tier //p' "$UNITS")
[ -n "$OUT" ] && [ -n "$TIER" ] || { echo "$UNITS is not a units file" >&2; exit 2; }
LOGDIR="$OUT/.cache/gridengine"
mkdir -p "$LOGDIR"
CHECK=""
[ -f "$CODE_DIR/expected/MANIFEST-$TIER.sha256" ] && CHECK="--check"
{
  echo "=== final merge, job ${JOB_ID:-?}, host $(uname -n), $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  sh "$CODE_DIR/cluster/merge.sh" "$UNITS" $CHECK
  echo "manifest: $OUT/MANIFEST.sha256 ($(wc -l < "$OUT/MANIFEST.sha256" | tr -d ' ') files)"
} 2>&1 | tee -a "$LOGDIR/final.log"
