"""Split a tier into independent work units, run one unit, and check unit status.

  python3 cluster/units.py make   --tier full --out OUT [--units FILE]
  python3 cluster/units.py run    --units FILE --index I   (or SLURM_ARRAY_TASK_ID; I is 1-based)
  python3 cluster/units.py run    --units FILE --all       (every unit in turn, one process: for testing)
  python3 cluster/units.py status --units FILE
  python3 cluster/units.py plan     --units FILE --lanes L --slots N [--print-hours]
  python3 cluster/units.py run-lane --units FILE --lane K --lanes L --workers N [--failed FILE]

`make` asks every step script for its unit list (PODSIM_LIST_UNITS mode; nothing is computed) and writes the
units file (default OUT/.cache/units-<tier>.txt): a header with the tier, the output directory and the code
hash, then one line per unit "<index> <step> <key> <script>". `run` computes one unit into OUT/.cache/<tier>/<step>/<key>.json.gz (atomic
write; a unit already present is skipped, so reruns are idempotent and failed units can simply be resubmitted).
Afterwards `python3 run_tier.py --tier full --out OUT --merge` (or cluster/merge.sh) assembles exactly the files
a single-machine run writes, refusing to start if a unit is missing or was produced by different code.

`plan` and `run-lane` serve the Grid Engine lanes (cluster/submit.sh): lane K of L owns the units with index i
where (i - 1) mod L == K - 1. `run-lane` runs its lane's units N at a time (one core each), skips units already
cached, continues past a failed unit, lists the failures at the end (and in OUT/.cache/gridengine/) and exits 1
if any unit failed.

Only python3 >= 3.9 on PATH is assumed.
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
sys.path.insert(0, CODE)

import run_tier  # noqa: E402

# step name used in cache paths -> script that owns it
STEP_SCRIPT = {"x1": "run_x1.py", "x1v": "run_x1.py", "x3": "run_x3.py", "x3b": "run_x3b.py", "x2": "run_x2.py",
               "x4floor": "run_x4.py", "x4dem": "run_x4.py", "x7a": "run_x7.py", "x7b": "run_x7.py",
               "x6": "run_x6.py", "x5": "run_x5.py", "xd": "run_xd.py"}
FORMAT = "podsim-units-v1"

# Estimated CPU seconds per unit, by tier and step: one core of the 2.1 GHz machine of run_tier.FULL_ESTIMATE
# (its per-step totals divided by the unit counts; about 43 CPU hours for the full tier). Used only to print the
# lane split and to order each lane's units (most expensive first); a tier without an entry gets no estimate.
COST_S = {"full": {"x1": 7.5, "x1v": 12.0, "x3": 12.0, "x3b": 12.0, "x2": 46.0, "x4floor": 12.0, "x4dem": 12.0,
                   "x7a": 151.0, "x7b": 12.0, "x6": 32.4, "x5": 107.0, "xd": 17.0}}
LANE_DIR = "gridengine"  # under OUT/.cache: lane logs, failure lists, submitted job IDs


def _registry():
    from podsim import registry as REG
    return REG


def make(tier, out, units_path):
    REG = _registry()
    out = os.path.abspath(out)
    run_tier.validate_out(out)
    scripts = []
    for st in run_tier.STEPS[tier]:
        if st in run_tier.UNIT_STEPS:
            for sc in run_tier.SCRIPTS[st]:
                if sc not in scripts:
                    scripts.append(sc)
    cdir = os.path.join(out, ".cache")
    os.makedirs(cdir, exist_ok=True)
    lst = os.path.join(cdir, "units-listing.%d" % os.getpid())
    if os.path.exists(lst):
        os.remove(lst)
    env = run_tier.tier_env(tier, out, 1)
    env["PODSIM_LIST_UNITS"] = lst
    for sc in scripts:
        r = subprocess.call([sys.executable, os.path.join(CODE, sc)], cwd=out, env=env)
        if r:
            raise SystemExit("listing units of %s failed (exit %d)" % (sc, r))
    with open(lst) as f:
        pairs = [ln.split() for ln in f if ln.strip()]
    os.remove(lst)
    seen = set()
    lines = []
    for step, key in pairs:
        if step not in STEP_SCRIPT:
            raise SystemExit("unknown unit step %r (update STEP_SCRIPT)" % step)
        if (step, key) in seen:
            raise SystemExit("duplicate unit %s %s" % (step, key))
        seen.add((step, key))
        lines.append((step, key))
    # default inside OUT/.cache, which manifests exclude, so the merged output equals a single-machine run
    units_path = os.path.abspath(units_path or os.path.join(cdir, "units-%s.txt" % tier))
    txt = ["# %s" % FORMAT, "# tier %s" % tier, "# out %s" % out, "# code %s" % REG.current_code_hash(),
           "# units %d" % len(lines)]
    for i, (step, key) in enumerate(lines, 1):
        txt.append("%d %s %s %s" % (i, step, key, STEP_SCRIPT[step]))
    tmp = units_path + ".%d.tmp" % os.getpid()
    with open(tmp, "w") as f:
        f.write("\n".join(txt) + "\n")
    os.replace(tmp, units_path)
    print("%d units written to %s" % (len(lines), units_path))
    return units_path


def read_units(path):
    if not os.path.exists(path):
        raise SystemExit("units file %s not found (run: python3 cluster/units.py make ...)" % path)
    head = {}
    units = []
    with open(path) as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln:
                continue
            if ln.startswith("# "):
                parts = ln[2:].split(" ", 1)
                head[parts[0]] = parts[1] if len(parts) > 1 else ""
                continue
            i, step, key, script = ln.split(" ")
            units.append((int(i), step, key, script))
    if FORMAT not in head:
        raise SystemExit("%s is not a units file (missing '# %s' header)" % (path, FORMAT))
    for k in ("tier", "out", "code"):
        if k not in head:
            raise SystemExit("units file %s has no '# %s' header line" % (path, k))
    if int(head.get("units", -1)) != len(units):
        raise SystemExit("units file %s is truncated: header says %s units, found %d" % (path, head.get("units"),
                                                                                         len(units)))
    return head, units


def check_code(head):
    REG = _registry()
    cur = REG.current_code_hash()
    if head["code"] != cur:
        raise SystemExit("units file was made with code %s but this code is %s: the code changed after the units "
                         "were listed. Remake the units file (and use a fresh output directory, or delete its "
                         ".cache) before running." % (head["code"][:12], cur[:12]))


def cache_file(head, step, key):
    return os.path.join(head["out"], ".cache", head["tier"], step, key + ".json.gz")


def run_one(head, unit):
    i, step, key, script = unit
    env = run_tier.tier_env(head["tier"], head["out"], 1)
    env["PODSIM_ONLY_UNIT"] = "%s/%s" % (step, key)
    t0 = time.time()
    r = subprocess.call([sys.executable, os.path.join(CODE, script)], cwd=head["out"], env=env)
    if r:
        raise SystemExit("unit %d (%s %s) failed with exit %d" % (i, step, key, r))
    if not os.path.exists(cache_file(head, step, key)):
        raise SystemExit("unit %d (%s %s) finished but wrote no cache entry" % (i, step, key))
    print("unit %d %s %s done in %.1f s" % (i, step, key, time.time() - t0), flush=True)


def status(head, units, lanes=None):
    REG = _registry()
    os.environ["PODSIM_OUT"] = head["out"]
    os.environ["PODSIM_TIER"] = head["tier"]
    done, missing, stale = [], [], []
    for u in units:
        p = cache_file(head, u[1], u[2])
        try:
            v = REG.cache_load(p)
        except REG.StaleCacheError:
            stale.append(u)
            continue
        except ValueError:  # truncated or foreign file: list it with the missing units so it gets rerun
            print("corrupt cache entry (delete it, then rerun unit %d): %s" % (u[0], p))
            missing.append(u)
            continue
        (done if v is not None else missing).append(u)
    print("units %d: done %d, missing %d, stale (other code version) %d" % (len(units), len(done), len(missing),
                                                                           len(stale)))
    if missing:
        print("missing indices: " + ",".join(str(u[0]) for u in missing[:200]))
    if stale:
        print("stale indices: " + ",".join(str(u[0]) for u in stale[:200]))
    if lanes:
        for k in range(1, lanes + 1):
            mine = lane_units(units, k, lanes)
            todo = [u for u in missing + stale if lane_of(u[0], lanes) == k]
            print("lane %d of %d: %d units, %d done, %d missing or stale" % (k, lanes, len(mine),
                                                                         len(mine) - len(todo), len(todo)))
        bad = sorted({lane_of(u[0], lanes) for u in missing + stale})
        if bad:
            print("lanes to resubmit: " + " ".join(str(k) for k in bad))
    return 0 if not missing and not stale else 1


def lane_of(index, lanes):
    """Lane (1..lanes) that owns 1-based unit index `index`: round robin, (index - 1) mod lanes == lane - 1."""
    if lanes < 1 or index < 1:
        raise ValueError("lanes and unit indices start at 1")
    return (index - 1) % lanes + 1


def unit_cost(tier, step):
    return COST_S.get(tier, {}).get(step)


def lane_units(units, lane, lanes):
    """The units of lane `lane` of `lanes`, in index order. The assignment is round robin on the unit index;
    because a step's units are contiguous in the units file and share one cost estimate, round robin already
    balances the estimated cost to within one unit per step, so no cost-based assignment is needed."""
    if not 1 <= lane <= lanes:
        raise SystemExit("lane %d out of range 1..%d" % (lane, lanes))
    return [u for u in units if lane_of(u[0], lanes) == lane]


def ordered(head, mine):
    """A lane's run order: most expensive first when every unit has an estimate (so the last units to finish
    are short ones), else index order."""
    costs = [unit_cost(head["tier"], u[1]) for u in mine]
    if mine and all(c is not None for c in costs):
        return [u for _, u in sorted(zip(costs, mine), key=lambda cu: (-cu[0], cu[1][0]))]
    return list(mine)


def plan(head, units, lanes, slots, out=sys.stdout):
    """Print the lane split; return the suggested h_rt in whole hours (None without estimates)."""
    if lanes < 1 or slots < 1:
        raise SystemExit("LANES and SLOTS must be at least 1")
    est = all(unit_cost(head["tier"], u[1]) is not None for u in units)
    print("tier %s, %d units, %d lanes of %d slots" % (head["tier"], len(units), lanes, slots), file=out)
    worst = 0.0
    for k in range(1, lanes + 1):
        mine = lane_units(units, k, lanes)
        if est:
            cs = [unit_cost(head["tier"], u[1]) for u in mine]
            core_h = sum(cs) / 3600.0
            # lower bound on wall time with `slots` workers: the larger of the even share and the longest unit
            wall_h = max(core_h / slots, (max(cs) if cs else 0.0) / 3600.0)
            worst = max(worst, wall_h)
            print("  lane %d: %5d units, about %6.1f core-hours, about %5.1f h wall on %d cores"
                  % (k, len(mine), core_h, wall_h, slots), file=out)
        else:
            print("  lane %d: %5d units" % (k, len(mine)), file=out)
    if not est:
        print("  (no per-unit cost estimates for tier %s)" % head["tier"], file=out)
        return None
    total = sum(unit_cost(head["tier"], u[1]) for u in units) / 3600.0
    hours = max(2, int(2.0 * worst) + 1)
    print("  total about %.1f core-hours (estimates from one 2.1 GHz core; cluster cores may differ)" % total,
          file=out)
    print("  suggested h_rt: %d h (twice the slowest lane's estimate, at least 2 h)" % hours, file=out)
    return hours


def is_cached(head, unit):
    REG = _registry()
    try:
        return REG.cache_load(cache_file(head, unit[1], unit[2])) is not None
    except (REG.StaleCacheError, ValueError):
        return False  # rerun; the unit script reports a stale or corrupt entry as a failure


def _run_unit_captured(head, unit):
    i, step, key, script = unit
    env = run_tier.tier_env(head["tier"], head["out"], 1)
    env["PODSIM_ONLY_UNIT"] = "%s/%s" % (step, key)
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, os.path.join(CODE, script)], cwd=head["out"], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        rc, text = p.returncode, p.stdout.decode("utf-8", "replace")
    except OSError as e:
        rc, text = -1, str(e)
    if rc == 0 and not os.path.exists(cache_file(head, step, key)):
        rc, text = -2, text + "\nfinished but wrote no cache entry"
    return rc, time.time() - t0, text


def run_lane(head, units, lane, lanes, workers, failed_path=None):
    """Run lane `lane` of `lanes` with `workers` concurrent units. Returns 0, or 1 if any unit failed."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    if workers < 1:
        raise SystemExit("--workers must be at least 1")
    os.environ["PODSIM_OUT"] = head["out"]
    os.environ["PODSIM_TIER"] = head["tier"]
    mine = lane_units(units, lane, lanes)
    todo = [u for u in ordered(head, mine) if not is_cached(head, u)]
    skipped = len(mine) - len(todo)
    print("lane %d of %d: %d units, %d already cached (skipped), %d to run, %d at a time, python %s"
          % (lane, lanes, len(mine), skipped, len(todo), workers, sys.executable), flush=True)
    lock = threading.Lock()
    failed = []
    state = {"done": 0}

    def work(u):
        rc, dt, text = _run_unit_captured(head, u)
        with lock:
            state["done"] += 1
            if rc == 0:
                print("[%d/%d] unit %d %s %s done in %.1f s" % (state["done"], len(todo), u[0], u[1], u[2], dt),
                      flush=True)
            else:
                failed.append((u, rc))
                tail = "\n".join("    " + ln for ln in text.rstrip().splitlines()[-20:])
                print("[%d/%d] unit %d %s %s FAILED (exit %d) after %.1f s; last output:\n%s"
                      % (state["done"], len(todo), u[0], u[1], u[2], rc, dt, tail), flush=True)

    if todo:
        with ThreadPoolExecutor(max_workers=min(workers, len(todo))) as ex:
            list(ex.map(work, todo))
    failed.sort(key=lambda f: f[0][0])
    if failed_path is None:
        failed_path = os.path.join(head["out"], ".cache", LANE_DIR, "failed-lane-%d.txt" % lane)
    os.makedirs(os.path.dirname(failed_path), exist_ok=True)
    if failed:
        tmp = failed_path + ".%d.tmp" % os.getpid()
        with open(tmp, "w") as f:
            for u, rc in failed:
                f.write("%d %s %s exit %d\n" % (u[0], u[1], u[2], rc))
        os.replace(tmp, failed_path)
    elif os.path.exists(failed_path):
        os.remove(failed_path)
    print("lane %d of %d finished: %d computed, %d skipped, %d failed" % (lane, lanes, len(todo) - len(failed),
                                                                       skipped, len(failed)), flush=True)
    if failed:
        print("failed unit indices: " + ",".join(str(u[0]) for u, _ in failed), flush=True)
        print("listed in %s; resubmit this lane once fixed (cached units are skipped)" % failed_path, flush=True)
        return 1
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    m = sub.add_parser("make")
    m.add_argument("--tier", required=True, choices=sorted(run_tier.STEPS))
    m.add_argument("--out", required=True)
    m.add_argument("--units", default=None)
    r = sub.add_parser("run")
    r.add_argument("--units", required=True)
    r.add_argument("--index", type=int, default=None)
    r.add_argument("--all", action="store_true")
    s = sub.add_parser("status")
    s.add_argument("--units", required=True)
    s.add_argument("--lanes", type=int, default=None, help="also count done and missing units per lane")
    p = sub.add_parser("plan")
    p.add_argument("--units", required=True)
    p.add_argument("--lanes", type=int, required=True)
    p.add_argument("--slots", type=int, required=True)
    p.add_argument("--print-hours", action="store_true", help="print only the suggested h_rt hours (or 0)")
    ln = sub.add_parser("run-lane")
    ln.add_argument("--units", required=True)
    ln.add_argument("--lane", type=int, default=None, help="1-based (default SGE_TASK_ID)")
    ln.add_argument("--lanes", type=int, required=True)
    ln.add_argument("--workers", type=int, default=None, help="default NSLOTS, else 1")
    ln.add_argument("--failed", default=None, help="failure list (default OUT/.cache/gridengine/failed-lane-K.txt)")
    a = ap.parse_args(argv)
    if a.cmd == "make":
        make(a.tier, a.out, a.units)
        return 0
    if a.cmd not in ("run", "status", "plan", "run-lane"):
        ap.print_help()
        return 2
    head, units = read_units(a.units)
    if not os.path.isdir(head["out"]):
        raise SystemExit("output directory %s (from the units file) does not exist" % head["out"])
    if a.cmd == "status":
        return status(head, units, a.lanes)
    check_code(head)
    if a.cmd == "plan":
        if a.print_hours:
            import io
            h = plan(head, units, a.lanes, a.slots, out=io.StringIO())
            print(h or 0)
        else:
            plan(head, units, a.lanes, a.slots)
        return 0
    if a.cmd == "run-lane":
        lane = a.lane
        if lane is None:
            if not os.environ.get("SGE_TASK_ID", "").isdigit():
                raise SystemExit("give --lane K or run inside a Grid Engine array task (SGE_TASK_ID)")
            lane = int(os.environ["SGE_TASK_ID"])
        workers = a.workers
        if workers is None:
            workers = int(os.environ["NSLOTS"]) if os.environ.get("NSLOTS", "").isdigit() else 1
        if a.lanes < 1:
            raise SystemExit("--lanes must be at least 1")
        return run_lane(head, units, lane, a.lanes, workers, a.failed)
    if a.all:
        for u in units:
            run_one(head, u)
        return 0
    idx = a.index
    if idx is None:
        env_idx = os.environ.get("SLURM_ARRAY_TASK_ID")
        if env_idx is None:
            raise SystemExit("give --index I, --all, or run inside a job array (SLURM_ARRAY_TASK_ID)")
        idx = int(env_idx)
    if not 1 <= idx <= len(units):
        raise SystemExit("unit index %d out of range 1..%d" % (idx, len(units)))
    run_one(head, units[idx - 1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
