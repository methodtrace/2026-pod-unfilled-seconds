#!/bin/sh
# End-to-end test of the Grid Engine scripts (cluster/submit.sh, lane.sh, final.sh, status.sh) on one machine,
# with tests/gridengine_stub/qsub standing in for Grid Engine. Takes several minutes (fullsmoke tier, three
# times). Not part of the tier's test step; run it by hand from code/:
#
#   sh tests/gridengine_e2e.sh WORKDIR [REF_OUT]
#
# WORKDIR    empty or new scratch directory
# REF_OUT    output directory of a finished `sh run_all.sh --tier fullsmoke --out REF_OUT` (computed into
#            WORKDIR/single if omitted)
#
# 1. LANES=3, SLOTS=2: submit, wait for the held final job, compare MANIFEST.sha256 with the single-machine one.
# 2. Same into a fresh OUT, but kill lane 2 midway: the final job must refuse to merge; resubmit lane 2 only
#    (TASKS=2), which must skip its cached units, and the new final job's manifest must match again.
set -eu
[ $# -ge 1 ] || { echo "usage: sh tests/gridengine_e2e.sh WORKDIR [REF_OUT]" >&2; exit 2; }
CODE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$1"
W=$(CDPATH= cd -- "$1" && pwd)
PY=${PYTHON:-python3}
export TIER=fullsmoke
export QSUB_STUB_DIR="$W/qsub-state"
mkdir -p "$QSUB_STUB_DIR"
PATH="$CODE_DIR/tests/gridengine_stub:$PATH"
export PATH

if [ $# -ge 2 ]; then
  REF=$(CDPATH= cd -- "$2" && pwd)
else
  REF="$W/single"
  echo "== single-machine reference run into $REF"
  sh "$CODE_DIR/run_all.sh" --tier fullsmoke --out "$REF" --jobs 2 > "$W/single.log" 2>&1
fi
[ -f "$REF/MANIFEST.sha256" ] || { echo "no reference manifest at $REF/MANIFEST.sha256" >&2; exit 2; }

job_exit() {  # print the exit status of task $2 of stub job $1 once it has ended
  while [ ! -f "$QSUB_STUB_DIR/jobs/$1/task-$2.exit" ]; do sleep 1; done
  cat "$QSUB_STUB_DIR/jobs/$1/task-$2.exit"
}
submit() {  # submit.sh output into $W/$2.submit.log; sets LANE_JOB and FINAL_JOB
  sh "$CODE_DIR/cluster/submit.sh" "$1" 3 2 testq 1 > "$W/$2.submit.log" 2>&1
  cat "$W/$2.submit.log"
  LANE_JOB=$(sed -n 's/^lane array job: \([0-9]*\) .*/\1/p' "$W/$2.submit.log")
  FINAL_JOB=$(sed -n 's/^final merge job: \([0-9]*\) .*/\1/p' "$W/$2.submit.log")
}
FAIL=0
compare() {
  if cmp -s "$REF/MANIFEST.sha256" "$1/MANIFEST.sha256"; then
    echo "PASS  $2: $1/MANIFEST.sha256 equals the single-machine manifest byte for byte" \
      "($(wc -l < "$1/MANIFEST.sha256" | tr -d ' ') files, sha256 $(sha256sum "$1/MANIFEST.sha256" | cut -c1-16))"
  else
    echo "FAIL  $2: manifests differ"
    diff "$REF/MANIFEST.sha256" "$1/MANIFEST.sha256" || true
    FAIL=1
  fi
}

echo "== 1. three lanes of two slots"
B="$W/ge"
submit "$B" ge
for k in 1 2 3; do echo "lane $k exit $(job_exit "$LANE_JOB" "$k")"; done
RC=$(job_exit "$FINAL_JOB" 0)
echo "final job exit $RC"
[ "$RC" -eq 0 ] || FAIL=1
compare "$B" "three lanes"
sh "$CODE_DIR/cluster/status.sh" "$B" > "$W/ge.status.log" 2>&1 || FAIL=1
head -n 5 "$W/ge.status.log"

echo "== 2. kill lane 2 midway, then resubmit it"
C="$W/ge-kill"
submit "$C" kill
LOG2="$C/.cache/gridengine/lane-2.log"
while :; do  # wait until lane 2 has finished at least 4 units, then kill its whole process group
  N=$( (grep -c ' done in ' "$LOG2" 2>/dev/null) || true)
  [ "${N:-0}" -ge 4 ] && break
  [ -f "$QSUB_STUB_DIR/jobs/$LANE_JOB/task-2.exit" ] && { echo "FAIL  lane 2 ended before it could be killed"; exit 1; }
  sleep 1
done
PGID=$(cat "$QSUB_STUB_DIR/jobs/$LANE_JOB/task-2.pgid")
"$PY" -c 'import os, signal, sys; os.killpg(int(sys.argv[1]), signal.SIGTERM)' "$PGID"
echo "killed lane 2 (process group $PGID) after $N finished units"
for k in 1 3; do echo "lane $k exit $(job_exit "$LANE_JOB" "$k")"; done
RC=$(job_exit "$FINAL_JOB" 0)
echo "final job after the kill: exit $RC (must be nonzero: merge refused)"
[ "$RC" -ne 0 ] || FAIL=1
[ ! -f "$C/MANIFEST.sha256" ] || { echo "FAIL  a manifest was written despite the missing units"; FAIL=1; }
sh "$CODE_DIR/cluster/status.sh" "$C" 3 2 > "$W/kill.status.log" 2>&1 && FAIL=1  # must report missing units
sed -n '1p;/^lane [0-9] of/p;/^lanes to resubmit/p' "$W/kill.status.log"
TASKS=2 submit "$C" resubmit
RC=$(job_exit "$LANE_JOB" 2)
echo "resubmitted lane 2 exit $RC"
grep '^lane 2 of 3: ' "$LOG2" | tail -n 1
SKIPPED=$(grep '^lane 2 of 3: ' "$LOG2" | tail -n 1 | sed -n 's/.*, \([0-9]*\) already cached.*/\1/p')
[ "${SKIPPED:-0}" -ge "$N" ] || { echo "FAIL  the resubmitted lane did not skip its cached units"; FAIL=1; }
RC=$(job_exit "$FINAL_JOB" 0)
echo "final job after the resubmission: exit $RC"
[ "$RC" -eq 0 ] || FAIL=1
compare "$C" "killed and resubmitted lane"
sh "$CODE_DIR/cluster/status.sh" "$C" > "$W/resubmit.status.log" 2>&1 || FAIL=1
head -n 5 "$W/resubmit.status.log"

[ "$FAIL" -eq 0 ] && echo "ALL GRID ENGINE CHECKS PASSED" || echo "SOME GRID ENGINE CHECKS FAILED"
exit $FAIL
