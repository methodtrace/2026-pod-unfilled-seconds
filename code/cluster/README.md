# Running a tier on a cluster

Two ways are supplied: Grid Engine lanes (a few multi-core array tasks plus one held merge job, below) and a
SLURM job array with one core per unit (further down). Both write the same files.

The tier runner splits its work into independent units (one per experiment and menu, or per Monte Carlo block).
On a cluster the units run as tasks of a job array (one unit per task, or a share of them per multi-core
lane); a merge step then assembles the same files, byte for
byte, that `sh code/run_all.sh --tier full` writes on one machine. Only `python3` (3.9 or newer) on PATH is
assumed; no modules, packages or virtual environments are needed. Float totals use `math.fsum`, and results were
identical on the Python versions tested (README.md, Python versions), but use one interpreter generation for all
units of a run: a unit computed on
Python 3.12 or newer and one computed on an older Python carry different code hashes, and the merge refuses to
mix them.

## Grid Engine: a few multi-core lanes and one held merge job

`cluster/submit.sh` submits an array of LANES tasks (`qsub -t 1-LANES`), each a job of SLOTS cores
(`-pe smp SLOTS`). Lane k computes the units whose index i satisfies (i - 1) mod LANES == k - 1, SLOTS at a
time, with `cluster/units.py run-lane`. A second job (`cluster/final.sh`, `-hold_jid` on the lane array) starts
when every lane has ended, runs `cluster/merge.sh` and writes `OUT/MANIFEST.sha256`. Replace `OUT` with a
directory on a filesystem the compute nodes share and `QUEUE` with a queue name; run from the repository's
`code/` directory on a submit host.

```sh
cd code
sh cluster/submit.sh OUT 4 32 QUEUE
```

This makes `OUT/.cache/units-full.txt` if it is missing, prints the lane split with the estimated core-hours of
each lane, submits the lane array and the held final job, and prints both job IDs. The arguments are
`OUT LANES SLOTS QUEUE [HOURS]`: with 4 lanes of 32 slots each lane gets 1,010 of the 4,040 units, about 10.8
core-hours (about 43 in all, estimated on one 2.1 GHz core). HOURS sets `-l h_rt=HOURS:00:00` for every job;
without it the script uses twice the slowest lane's estimate, at least 2 hours. Round robin on the unit index
balances the estimated cost of the lanes to within 1 percent on the full tier (a step's units are contiguous and
equally expensive), and each lane runs its most expensive units first.

Interpreter: `PYTHON=/path/to/python3 sh cluster/submit.sh ...` picks it (default `python3`). submit.sh refuses
an interpreter older than 3.9 and says how to set `PYTHON`; it resolves the interpreter to an absolute path and
passes it with `qsub -v` to every lane and to the final job, so the whole run uses one interpreter (the path must
exist on the compute nodes). `TIER=fullsmoke` selects another tier (default full).

Progress, failures and the tail of every lane log:

```sh
sh cluster/status.sh OUT
```

It prints the done, missing and stale counts, per lane as well, the lanes that still have missing units, the
failed units each lane listed in `OUT/.cache/gridengine/failed-lane-K.txt`, the last lines of
`OUT/.cache/gridengine/lane-K.log` and `final.log`, and the last submissions with their job IDs. It exits 0 only
when every unit is done. Grid Engine's own job output goes to `OUT/.cache/gridengine/sge/`.

A lane skips units already cached, continues past a failed unit, and exits 1 at the end if any unit failed. If a
lane fails or is killed (for example at its run time limit), the final job's merge refuses to start and lists the
missing units. Resubmit only the lanes that `status.sh` names, with a new held final job; the cached units are
skipped:

```sh
TASKS=2 sh cluster/submit.sh OUT 4 32 QUEUE
```

`TASKS` takes the Grid Engine task range (`2`, or `2-3`); keep LANES the same as in the first submission, since
the lane split depends on it. Resubmitting all lanes (no `TASKS`) is also safe. A lane can be run by hand on any
machine:

```sh
python3 cluster/units.py run-lane --units OUT/.cache/units-full.txt --lane 2 --lanes 4 --workers 8
```

The scripts use only `qsub` options common to Grid Engine variants (`-t`, `-pe smp`, `-q`, `-l h_rt`, `-o`,
`-j y`, `-cwd`, `-v`, `-hold_jid`, `-terse`). If the parallel environment has another name at your site, change
`-pe smp` in `cluster/submit.sh`. They are tested with a local qsub stand-in (`tests/gridengine_stub/qsub`):
`sh tests/gridengine_e2e.sh WORKDIR` runs the fullsmoke tier as 3 lanes of 2 slots, checks that the merged
manifest equals a single-machine run byte for byte, then kills one lane midway, resubmits it, and checks that it
skips its cached units and that the merge still matches.

## SLURM: one core per unit

Replace `ACCOUNT`, `PARTITION` and `/shared/OUT` with your own values. Run every command from the repository's
`code/` directory, on a filesystem that the compute nodes share.

### 1. List the units

```sh
cd code
python3 cluster/units.py make --tier full --out /shared/OUT
```

This writes `/shared/OUT/.cache/units-full.txt` and prints the number of units N. Nothing is computed. The file
records the tier, the output directory and a hash of the code; every task checks that hash and refuses to run
if the code changed after listing.

### 2. Run the units as job arrays, at most 1,000 tasks each

Clusters cap the array index (SLURM's MaxArraySize, often 1001, so the largest index is 1000), and the full tier
has about 4,000 units. Submit them in batches of at most 1,000 tasks: task i of a batch with offset OFFSET
computes unit OFFSET + i. From `code/`:

```sh
UNITS=/shared/OUT/.cache/units-full.txt
N=$(sed -n 's/^# units //p' "$UNITS")
OFFSET=0
while [ "$OFFSET" -lt "$N" ]; do
  COUNT=$((N - OFFSET))
  [ "$COUNT" -gt 1000 ] && COUNT=1000
  sbatch --account=ACCOUNT --partition=PARTITION --array=1-$COUNT --export=ALL,UNIT_OFFSET=$OFFSET \
    cluster/array.sbatch "$UNITS"
  OFFSET=$((OFFSET + COUNT))
done
```

The full tier has N = 4,040 units, so this submits five arrays: units 1 to 1,000 (`UNIT_OFFSET=0`), 1,001 to
2,000 (1000), 2,001 to 3,000 (2000), 3,001 to 4,000 (3000) and 4,001 to 4,040 (4000, `--array=1-40`). Add `%50`
after a range (`--array=1-$COUNT%50`) to cap concurrent tasks. Each task uses one core and writes one cache entry under `/shared/OUT/.cache/full/<step>/<key>.json.gz` through a temporary file and an
atomic rename, so a killed task leaves no partial entry. The script's defaults are one core, 2 GB and 2 hours per
task; the longest units take about 6 minutes on a 2 GHz core, most take seconds. The whole full tier is about
43 core-hours (`python3 run_tier.py --tier full --out X --list` prints the estimate).

### 3. Check progress and rerun failures

```sh
python3 cluster/units.py status --units /shared/OUT/.cache/units-full.txt
```

It prints counts and the indices of missing units (unit indices, 1 to N). Resubmit only those, each with the
offset of its batch (a unit already present is skipped, so resubmitting a whole batch with the loop above is also
safe):

```sh
UNITS=/shared/OUT/.cache/units-full.txt
for I in 7 19 2240; do
  OFFSET=$(( (I - 1) / 1000 * 1000 ))
  sbatch --account=ACCOUNT --partition=PARTITION --array=$((I - OFFSET)) --export=ALL,UNIT_OFFSET=$OFFSET \
    cluster/array.sbatch "$UNITS"
done
```

Replace `7 19 2240` with the indices that `status` printed.

A unit can also be run by hand, for example on a login node for a quick test:

```sh
python3 cluster/units.py run --units /shared/OUT/.cache/units-full.txt --index 1
```

### 4. Merge

```sh
sh cluster/merge.sh /shared/OUT/.cache/units-full.txt --check
```

The merge refuses to start while any unit is missing or was computed by a different code version. It then runs
the unit tests, assembles every table from the cached units (it computes no unit), runs the cheap unsplit steps
(the X0 reference checks, the consistency checks, the X2 split, the catalog and the extracts) and writes `/shared/OUT/MANIFEST.sha256`.
With `--check` it compares the manifest with `code/expected/MANIFEST-<tier>.sha256`; the full tier has no file there, so compare a full merge with the released data's manifest instead: `python3 run_tier.py --tier full --out /shared/OUT --merge --check --expected <released data>/MANIFEST.sha256`. The
merge needs one core and a few GB of memory; run it as a single job or on a login node if that is allowed.

## Same result on one machine

```sh
sh code/run_all.sh --tier full --out /some/OUT --jobs 10
```

writes the same files. A stopped single-machine run resumes from its own `.cache` folder. The equivalence of the
two paths is tested on the quick tier: run `sh code/run_all.sh --tier quick --out A`, then steps 1, 2 (with
`python3 cluster/units.py run --units B/.cache/units-quick.txt --all` instead of sbatch) and 4 into B, and compare
`A/MANIFEST.sha256` with `B/MANIFEST.sha256`.

## Rules the runner enforces

- A cache entry carries the hash of the code that produced it: the `podsim` package, the unit-computing
  `run_x*.py` scripts and the vendored engines (not the report scripts, `run_tier.py`, the cluster
  scripts, tests or docs, so editing those keeps the cache valid). Reading an entry from different code stops the
  run with an error naming the file; it is never reused silently. After a change to hashed code, use a new output
  directory.
- Unit keys are unique per step and contain no path separators; an unknown index or a truncated units file is an
  error.
- `.cache`, `timing.json` files and temporary files are excluded from the manifest.
