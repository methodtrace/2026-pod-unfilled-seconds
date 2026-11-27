"""Run one tier: tests, then the tier's experiments, then the manifest (and optional check).

Usage: python3 run_tier.py --tier quick|narrow|full|fullsmoke --out DIR [--check [--expected FILE]] [--jobs N]
       [--list] [--merge]
Called by run_all.sh. Writes into DIR only (plus DIR/.cache for resumable full-tier work). Every result
file is deterministic; timing goes to DIR/timing.json and DIR/<step>/timing.json, excluded from the
manifest along with DIR/.cache and DIR/MANIFEST.sha256 itself. Manifest hashes of .gz files are of the
decompressed content.
"""
import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

STEPS = {
    "quick": ["tests", "x0", "checks", "x1", "x3", "x3b", "x2", "x2split", "x4", "x7", "x6", "x5", "xd", "catalog"],
    "narrow": ["tests", "x0", "checks", "x1", "x3", "x3b", "x2", "x2split", "x4", "x7", "x6", "x5", "summaries",
               "catalog"],
    "full": ["tests", "x0", "checks", "x1", "x3", "x3b", "x2", "x2split", "x4", "x7", "x6", "x5", "xd", "catalog",
             "extracts"],
}
STEPS["fullsmoke"] = list(STEPS["full"])
SCRIPTS = {
    "x0": ["run_x0.py"], "checks": ["run_checks.py"], "x1": ["run_x1.py"], "x3": ["run_x3.py"],
    "x3b": ["run_x3b.py"], "x2": ["run_x2.py"], "x2split": ["run_x2_split.py"], "x7": ["run_x7.py"],
    "x6": ["run_x6.py"], "x5": ["run_x5.py"], "x4": ["run_x4.py"], "xd": ["run_xd.py"],
    "extracts": ["extract.py"],
    "summaries": ["make_summaries.py", "run_x7_report.py"],
}
# steps whose scripts split their work into cached units (cluster/units.py lists them)
UNIT_STEPS = ("x1", "x3", "x3b", "x2", "x4", "x7", "x6", "x5", "xd")
TEST_MODULES = ["tests.test_podsim", "tests.test_x6", "tests.test_x5", "tests.test_x4", "tests.test_new_axes",
                "tests.test_units", "tests.test_numeric", "tests.test_decomposition",
                "tests.test_engine_equivalence", "tests.test_review_fixes", "tests.test_round5"]


def tier_env(tier, out, jobs, base=None):
    """Environment for the tier's scripts (also used by the cluster unit runner and merge)."""
    sys.path.insert(0, HERE)
    from podsim import registry as REG
    if tier not in REG.TIERS:
        raise SystemExit("unknown tier %r (expected one of: %s)" % (tier, ", ".join(sorted(REG.TIERS))))
    env = dict(os.environ if base is None else base)
    env["PODSIM_TIER"] = tier
    env["PODSIM_OUT"] = out
    env["PODSIM_JOBS"] = str(jobs)
    env["PODSIM_TMAX"] = str(REG.TIERS[tier]["tmax"])
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def validate_out(out):
    """Create the output directory if needed and check it is writable; clear error otherwise."""
    if os.path.exists(out) and not os.path.isdir(out):
        raise SystemExit("output path %s exists and is not a directory" % out)
    try:
        os.makedirs(out, exist_ok=True)
        probe = os.path.join(out, ".write-probe.%d" % os.getpid())
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
    except OSError as e:
        raise SystemExit("output directory %s is not writable: %s" % (out, e))


# measured on a 2-core Linux machine (Intel Xeon at 2.10 GHz), seconds of wall time
MEASURED = {"quick": 76, "narrow": 4084}
FULL_ESTIMATE = (
    "Full tier estimate (TMAX 360 s; X1, X2, X3, X4, X7 part A and the demand sweep on 86 menus; X5 and X6 on 31\n"
    "  menus; 25 law-convention pairs; caps 1-20 and uncapped). Per-unit CPU time measured on one core of the\n"
    "  2-core Linux machine (Intel Xeon, 2.1 GHz), single units timed, the tier itself not run there:\n"
    "    X1 exact        6 to 9 s per menu                 86 units     about 0.2 CPU h\n"
    "    X2 levers       10 s (2 parts) to 76 s (4 parts), plus the sampled range lever 95 to 290 s\n"
    "                    (2,000 samples)                    86 units     about 5.7 CPU h\n"
    "    demand sweep    10 to 23 s per menu (135 scen.), plus the sampled range lever 44 to 223 s\n"
    "                    (1,000 samples)                    86 units     about 3.4 CPU h\n"
    "    X7 part A       74 s ({15,30}) to 250 s ({5,6,10}) 86 units    about 3.6 CPU h\n"
    "    X6              8.1 ms per break per block x 4,000 breaks, 3,100 blocks   about 28 CPU h\n"
    "    X5              0.14 to 0.39 s per break per law (31 menus, caps 3-13 and uncapped), 304 units of\n"
    "                    500 breaks                                                about 9 CPU h\n"
    "    X1 verifier and X7 part B at narrow size; X3, X3b, X4, checks             about 1 CPU h\n"
    "  Total about 51 CPU hours by these per-step estimates (cluster/units.py, from per-unit timings, gives about 43; X6 and X5 are 72% of it); 4,040 units; largest unit about 6 minutes.\n"
    "    2 cores of that machine (--jobs 2): about 26 h wall\n"
    "    a 10-core 2026 desktop computer (--jobs 10): about 90 minutes wall, measured\n"
    "    SLURM array (cluster/README.md): wall time set by the queue; about 51 core-hours in total\n"
    "  Memory: under 1 GB per worker; the unit cache needs a few GB of disk. Every unit is cached in OUT/.cache\n"
    "  with a code hash, so a stopped run resumes and a changed code version is refused.")


def content_sha256(p):
    """sha256 of a result file's content: for .gz files the decompressed bytes, so a manifest does not depend on
    the zlib build (zlib and zlib-ng compress identical data to different bytes)."""
    h = hashlib.sha256()
    op = gzip.open if p.endswith(".gz") else open
    with op(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest(out):
    lines = []
    for root, dirs, files in os.walk(out):
        dirs[:] = sorted(d for d in dirs if d != ".cache")
        for fn in sorted(files):
            if fn in ("timing.json", "MANIFEST.sha256") or fn.endswith(".tmp") or fn.endswith(".log") \
                    or fn.startswith(".write-probe"):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, out).replace(os.sep, "/")
            lines.append((rel, content_sha256(p)))
    lines.sort()
    with open(os.path.join(out, "MANIFEST.sha256"), "w") as f:
        for rel, h in lines:
            f.write("%s  %s\n" % (h, rel))
    return lines


def check(out, tier, expected=None):
    """Compare OUT/MANIFEST.sha256 with an expected manifest: code/expected/MANIFEST-<tier>.sha256, or the file
    given with --expected (for example the MANIFEST.sha256 shipped with the released full-tier data)."""
    exp_path = expected or os.path.join(HERE, "expected", "MANIFEST-%s.sha256" % tier)
    if not os.path.exists(exp_path):
        print("no expected manifest at %s" % exp_path)
        return 1
    exp = {}
    for line in open(exp_path):
        if line.strip():
            h, rel = line.rstrip("\n").split("  ", 1)
            exp[rel] = h
    got = {}
    for line in open(os.path.join(out, "MANIFEST.sha256")):
        if line.strip():
            h, rel = line.rstrip("\n").split("  ", 1)
            got[rel] = h
    bad = 0
    for rel in sorted(set(exp) | set(got)):
        if rel not in got:
            print("FAIL  %s (missing)" % rel)
            bad += 1
        elif rel not in exp:
            print("FAIL  %s (not in expected manifest)" % rel)
            bad += 1
        elif exp[rel] != got[rel]:
            print("FAIL  %s" % rel)
            bad += 1
        else:
            print("PASS  %s" % rel)
    print("ALL MATCH" if bad == 0 else "%d MISMATCH" % bad)
    return 0 if bad == 0 else 1


def write_catalog(out, tier):
    sys.path.insert(0, HERE)
    from podsim import registry as REG
    d = os.path.join(out, "catalog")
    os.makedirs(d, exist_ok=True)
    REG.write_csv(os.path.join(d, "axes.csv"), REG.catalog_rows())
    cfg = REG.config(tier)
    desc = {k: (v if not isinstance(v, list) or not v or not isinstance(v[0], tuple) else [list(x) for x in v])
            for k, v in cfg.items()}
    REG.write_json(os.path.join(d, "tier_%s.json" % tier), desc)
    REG.write_code_record(d)
    lines = ["# Scenario catalog and tier %s" % tier, "",
             "Axes and status: `axes.csv` (%d entries; %d built, %d planned, %d extension). Tier contents: "
             "`tier_%s.json`." % (len(REG.AXES), sum(1 for a in REG.AXES if a[3] == "built"),
                                  sum(1 for a in REG.AXES if a[3] == "planned"),
                                  sum(1 for a in REG.AXES if a[3] == "extension"), tier), ""]
    lines.append("Not run by any tier (registered only):")
    lines.append("")
    for a, i, dsc, st in REG.AXES:
        if st != "built":
            lines.append("- %s %s (%s): %s" % (a, i, st, dsc))
    lines.append("")
    if REG.big(tier):
        REG.write_csv(os.path.join(d, "menu_sample.csv"),
                      [dict(index=i, menu=" ".join(map(str, m)), source=("M7" if m in REG.M7 else "M85 sample"))
                       for i, m in enumerate(REG.menu_sample())])
        lines.append("X5 and X6 menu set: `menu_sample.csv` (the seven study menus plus %d menus sampled from the "
                     "85-menu grid with random.Random(%r))." % (REG.MENU_SAMPLE_N, REG.MENU_SAMPLE_SEED))
        lines.append("")
        lines.append("Skipped or narrowed in the full tier:")
        lines.append("")
        for x in REG.FULL_SKIPPED:
            lines.append("- " + x)
        lines.append("")
    REG.write_text(os.path.join(d, "README.md"), "\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", required=True, choices=sorted(STEPS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--expected", default=None,
                    help="with --check: the expected manifest to compare with (default code/expected/MANIFEST-<tier>.sha256)")
    ap.add_argument("--jobs", type=int, default=int(os.environ.get("PODSIM_JOBS", "2")))
    ap.add_argument("--list", action="store_true", help="print the catalog and what the tier skips, then exit")
    ap.add_argument("--merge", action="store_true",
                    help="assemble a tier from per-unit cache entries computed elsewhere (cluster/units.py run); "
                         "refuses to compute any unit and refuses entries from other code versions")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    sys.path.insert(0, HERE)
    from podsim import registry as REG
    if a.list:
        for ax, i, d, st in REG.AXES:
            print("%-11s %-6s %-9s %s" % (ax, i, st, d))
        if a.tier == "full":
            print("\nfull tier skips:")
            for x in REG.FULL_SKIPPED:
                print(" - " + x)
        return 0
    if a.jobs < 1:
        raise SystemExit("--jobs must be at least 1")
    if a.tier == "full":
        print(FULL_ESTIMATE, flush=True)
    validate_out(out)
    env = tier_env(a.tier, out, a.jobs)
    if a.merge:
        env["PODSIM_REQUIRE_CACHED"] = "1"
        if not os.path.isdir(os.path.join(out, ".cache", a.tier)):
            raise SystemExit("--merge: no unit cache at %s; run the units first" % os.path.join(out, ".cache", a.tier))
    timing = {}
    t_all = time.time()
    for step in STEPS[a.tier]:
        t0 = time.time()
        if step == "tests":
            mods = [m for m in TEST_MODULES if os.path.exists(os.path.join(HERE, *m.split(".")) + ".py")]
            if len(mods) != len(TEST_MODULES):
                raise SystemExit("test modules missing: %s" % ", ".join(sorted(set(TEST_MODULES) - set(mods))))
            cmd = [sys.executable, "-m", "unittest", "-q"] + mods
            import shutil
            import tempfile
            tdir = tempfile.mkdtemp(prefix="sim-tests-")
            tenv = dict(env, PODSIM_OUT=tdir)  # tests never write into the tier's output or cache
            tenv.pop("PODSIM_REQUIRE_CACHED", None)
            try:
                r = subprocess.call(cmd, cwd=HERE, env=tenv)
            finally:
                shutil.rmtree(tdir, ignore_errors=True)
        elif step == "catalog":
            write_catalog(out, a.tier)
            r = 0
        else:
            r = 0
            for sc in SCRIPTS[step]:
                r = subprocess.call([sys.executable, os.path.join(HERE, sc)], cwd=out, env=env)
                if r:
                    break
        dt = time.time() - t0
        timing[step] = round(dt, 3)
        print("[%s] %-10s %8.1f s%s" % (a.tier, step, dt, "" if r == 0 else "  FAILED (exit %d)" % r), flush=True)
        if r:
            with open(os.path.join(out, "timing.json"), "w") as f:
                json.dump(timing, f, indent=1, sort_keys=True)
            return r
    timing["total"] = round(time.time() - t_all, 3)
    sys.path.insert(0, HERE)
    from podsim import registry as REG
    timing["code_sha256"] = REG.current_code_hash()
    timing["tree_sha256"], timing["tree_files"] = REG.tree_digest()
    with open(os.path.join(out, "timing.json"), "w") as f:
        json.dump(timing, f, indent=1, sort_keys=True)
    lines = manifest(out)
    print("[%s] total      %8.1f s; manifest: %d files in MANIFEST.sha256" % (a.tier, timing["total"], len(lines)))
    if a.check:
        return check(out, a.tier, a.expected)
    return 0


if __name__ == "__main__":
    sys.exit(main())
