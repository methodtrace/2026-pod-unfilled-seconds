#!/bin/sh
# One work unit per array task. Submit from the code/ directory of the repository:
#
#   sbatch --account=ACCOUNT --partition=PARTITION --array=1-COUNT --export=ALL,UNIT_OFFSET=OFFSET \
#     cluster/array.sbatch UNITS_FILE
#
# Task i computes unit OFFSET + i; COUNT is at most 1,000 per submission (cluster/README.md, step 2, has the loop
# over OFFSET = 0, 1000, 2000, ... up to the "# units" count in UNITS_FILE). Each task computes one unit into
# OUT/.cache/<tier>/<step>/<key>.json.gz (OUT is recorded in UNITS_FILE). A unit already present is skipped, so
# resubmitting a whole batch, or only failed tasks, is safe.
#
#SBATCH --job-name=sim-units
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=02:00:00
#SBATCH --output=slurm-%A_%a.log

set -eu
UNITS="${1:?usage: sbatch ... cluster/array.sbatch UNITS_FILE}"
CODE_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
if [ ! -f "$CODE_DIR/run_tier.py" ]; then
  echo "submit from the code/ directory (run_tier.py not found in $CODE_DIR)" >&2
  exit 2
fi
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
  echo "python3 >= 3.9 is required on PATH" >&2; exit 2; }
# Clusters cap array indices (MaxArraySize, often 1001), so the full tier's ~4,000 units go in several arrays of at
# most 1,000 tasks (the submission loop is in cluster/README.md, step 2):
# unit index = SLURM_ARRAY_TASK_ID + UNIT_OFFSET, e.g. sbatch --array=1-1000 --export=ALL,UNIT_OFFSET=1000 ...
TASK="${SLURM_ARRAY_TASK_ID:?not an array task}"
OFFSET="${UNIT_OFFSET:-0}"
exec "$PY" "$CODE_DIR/cluster/units.py" run --units "$UNITS" --index "$((TASK + OFFSET))"
