"""Tests for the unit cache, merge mode, validation and the cluster runner (cluster/units.py).
Run from code/: python3 -m unittest -q tests.test_units"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "cluster"))

from podsim import registry as REG  # noqa: E402
import run_tier  # noqa: E402
import units as CU  # noqa: E402


def square(x):
    return {"x": x, "sq": x * x, "f": 1.0 / 3.0}



def _read(path, mode="r"):
    with open(path, mode) as f:
        return f.read()

class EnvCase(unittest.TestCase):
    def setUp(self):
        # the runners print progress and, for the deliberate failure cases below, the failing unit's traceback;
        # keep that out of the test report (a test that needs the text captures it itself)
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
        self.d = tempfile.mkdtemp()
        self.saved = {k: os.environ.get(k) for k in ("PODSIM_OUT", "PODSIM_TIER", "PODSIM_REQUIRE_CACHED",
                                                       "PODSIM_ONLY_UNIT", "PODSIM_LIST_UNITS")}
        os.environ["PODSIM_OUT"] = self.d
        os.environ["PODSIM_TIER"] = "quick"
        for k in ("PODSIM_REQUIRE_CACHED", "PODSIM_ONLY_UNIT", "PODSIM_LIST_UNITS"):
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.d)


class TestCache(EnvCase):
    def test_round_trip_and_code_hash(self):
        a = REG.cached("t", "k1", lambda: square(3))
        b = REG.cached("t", "k1", lambda: self.fail("recomputed a cached unit"))
        self.assertEqual(a, b)
        p = REG.cache_path("t", "k1")
        import gzip
        with gzip.open(p, "rt") as f:
            obj = json.load(f)
        self.assertEqual(obj["code"], REG.current_code_hash())
        self.assertEqual(obj["value"]["f"], round(1.0 / 3.0, 9))
        self.assertEqual(REG.cached("t", "k2", lambda: square(3), raw=True)["f"], 1.0 / 3.0)

    def test_stale_and_corrupt_entries_refused(self):
        import gzip
        p = REG.cache_path("t", "k")
        with gzip.open(p, "wt") as f:
            json.dump(dict(code="0" * 64, value=1), f)
        with self.assertRaises(REG.StaleCacheError):
            REG.cached("t", "k", lambda: 2)
        with gzip.open(p, "wt") as f:
            f.write("{not json")
        with self.assertRaises(ValueError):
            REG.cache_load(p)
        with open(p, "w") as f:
            f.write("plain text, not gzip")
        with self.assertRaises(ValueError):
            REG.cache_load(p)
        with gzip.open(p, "wt") as f:
            json.dump({"value": 1}, f)
        with self.assertRaises(ValueError):
            REG.cache_load(p)

    def test_no_partial_files(self):
        REG.cached("t", "k", lambda: square(2))
        left = [f for f in os.listdir(os.path.dirname(REG.cache_path("t", "k"))) if f.endswith(".tmp")]
        self.assertEqual(left, [])
        out = os.path.join(self.d, "w.csv")
        REG.write_csv(out, [dict(a=1)])
        self.assertEqual([f for f in os.listdir(self.d) if f.endswith(".tmp")], [])

    def test_unclosed_stream_leaves_no_temp(self):
        code = ("import sys; sys.path.insert(0, %r); from podsim import registry as R; "
                "s = R.CsvStream(%r); s.write([dict(a=1)]); raise SystemExit(3)"
                % (HERE, os.path.join(self.d, "x.csv.gz")))
        r = subprocess.call([sys.executable, "-c", code])
        self.assertEqual(r, 3)
        self.assertEqual(os.listdir(self.d), [])

    def test_args_signature_refuses_other_grid(self):
        REG.cached("g", "k", lambda: 1, sig=REG.args_signature(((15, 30), {"caps": [3, 4]})))
        self.assertEqual(REG.cached("g", "k", lambda: 2, sig=REG.args_signature(((15, 30), {"caps": [3, 4]}))), 1)
        with self.assertRaises(REG.StaleCacheError):
            REG.cached("g", "k", lambda: 2, sig=REG.args_signature(((15, 30), {"caps": [3, 5]})))
        from podsim.exact import NegBinMeans
        self.assertNotEqual(REG.args_signature(NegBinMeans({5: 1.0}, 1)), REG.args_signature(NegBinMeans({5: 1.0}, 4)))
        self.assertNotEqual(REG.args_signature(NegBinMeans({5: 1.0}, 1)), REG.args_signature({5: 1.0}))

    def test_map_units_merge_mode(self):
        items = [("u%d" % i, i) for i in range(4)]
        exp = [REG.canon(square(i)) for i in range(4)]
        self.assertEqual(REG.map_units("m", items, square, n_jobs=1), exp)
        os.environ["PODSIM_REQUIRE_CACHED"] = "1"
        self.assertEqual(REG.map_units("m", items, square, n_jobs=2), exp)
        os.remove(REG.cache_path("m", "u2"))
        with self.assertRaises(REG.MissingUnitsError):
            REG.map_units("m", items, square)

    def test_parallel_equals_serial(self):
        items = [("u%d" % i, i) for i in range(6)]
        a = REG.map_units("p1", items, square, n_jobs=1)
        b = REG.map_units("p2", items, square, n_jobs=2)
        self.assertEqual(a, b)

    def test_bad_keys(self):
        for bad in ([("a/b", 1)], [("", 1)], [(".x", 1)], [("a", 1), ("a", 2)]):
            with self.assertRaises(ValueError):
                REG.map_units("b", bad, square)

    def test_units_only_modes(self):
        items = [("u0", 0), ("u1", 1)]
        lst = os.path.join(self.d, "list.txt")
        os.environ["PODSIM_LIST_UNITS"] = lst
        self.assertTrue(REG.units_only([("s", items, square, False)]))
        self.assertEqual(_read(lst), "s u0\ns u1\n")
        os.environ.pop("PODSIM_LIST_UNITS")
        os.environ["PODSIM_ONLY_UNIT"] = "s/u1"
        self.assertTrue(REG.units_only([("s", items, square, False)]))
        self.assertTrue(os.path.exists(REG.cache_path("s", "u1")))
        self.assertFalse(os.path.exists(REG.cache_path("s", "u0")))
        os.environ["PODSIM_ONLY_UNIT"] = "s/zz"
        with self.assertRaises(KeyError):
            REG.units_only([("s", items, square, False)])
        os.environ.pop("PODSIM_ONLY_UNIT")
        self.assertFalse(REG.units_only([("s", items, square, False)]))

    def test_code_hash_changes_with_code(self):
        h1 = REG.code_hash()
        self.assertEqual(h1, REG.code_hash())
        self.assertEqual(len(h1), 64)

    def test_code_hash_scope(self):
        """Editing a report script, the tier runner or a doc leaves code_hash unchanged; editing a
        computing module (package or unit script) or a vendored engine file changes it. Run on a copy of code/."""
        tmp = tempfile.mkdtemp()
        try:
            cp = os.path.join(tmp, "code")
            shutil.copytree(HERE, cp, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            base = REG.code_hash(cp)
            self.assertEqual(base, REG.code_hash(HERE))
            files = REG.code_files(cp)
            for rel in ("make_summaries.py", "run_x7_report.py", "run_x0.py",
                        "run_checks.py", "run_x2_split.py", "run_tier.py", "README.md", "cluster/units.py",
                        "tests/test_units.py"):
                self.assertNotIn(rel, files)
                with open(os.path.join(cp, *rel.split("/")), "a") as fh:
                    fh.write("\n# edited\n")
                self.assertEqual(REG.code_hash(cp), base, rel)
            for rel in ("podsim/exact.py", "podsim/numeric.py", "run_x6.py", "run_x1.py",
                        "vendor/sumset-undershoot/undershoot/engine_a.py"):
                self.assertIn(rel, files)
                p = os.path.join(cp, *rel.split("/"))
                with open(p, "rb") as fh:
                    orig = fh.read()
                with open(p, "ab") as fh:
                    fh.write(b"\n# edited\n")
                self.assertNotEqual(REG.code_hash(cp), base, rel)
                with open(p, "wb") as fh:
                    fh.write(orig)
                self.assertEqual(REG.code_hash(cp), base, rel)
        finally:
            shutil.rmtree(tmp)


class TestValidation(EnvCase):
    def test_bad_tier(self):
        os.environ["PODSIM_TIER"] = "bogus"
        with self.assertRaises(SystemExit):
            REG.tier_name()
        with self.assertRaises(SystemExit):
            run_tier.tier_env("bogus", self.d, 1)

    def test_out_dir_checks(self):
        f = os.path.join(self.d, "file")
        open(f, "w").close()
        with self.assertRaises(SystemExit):
            run_tier.validate_out(f)
        run_tier.validate_out(os.path.join(self.d, "new", "deep"))
        self.assertTrue(os.path.isdir(os.path.join(self.d, "new", "deep")))
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            ro = os.path.join(self.d, "ro")
            os.makedirs(ro)
            os.chmod(ro, 0o500)
            try:
                with self.assertRaises(SystemExit):
                    run_tier.validate_out(os.path.join(ro, "x"))
            finally:
                os.chmod(ro, 0o700)

    def test_run_tier_cli_errors(self):
        def run(args):
            return subprocess.run([sys.executable, os.path.join(HERE, "run_tier.py")] + args, capture_output=True,
                                  text=True)
        r = run(["--tier", "bogus", "--out", self.d])
        self.assertNotEqual(r.returncode, 0)
        r = run(["--tier", "quick", "--out", os.path.join(self.d, "empty"), "--merge"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no unit cache", r.stderr + r.stdout)
        r = run(["--tier", "quick", "--out", self.d, "--jobs", "0"])
        self.assertNotEqual(r.returncode, 0)

    def test_manifest_excludes(self):
        os.makedirs(os.path.join(self.d, "a", ".cache"))
        for p in ("a/x.csv", "a/timing.json", "a/.cache/u.json", "a/y.csv.123.tmp"):
            with open(os.path.join(self.d, p), "w") as f:
                f.write("1")
        lines = run_tier.manifest(self.d)
        self.assertEqual([r for r, _ in lines], ["a/x.csv"])


class TestListingWritesNothing(EnvCase):
    def test_make_lists_without_outputs(self):
        """units.py make on the quick tier lists every unit step and creates nothing but the cache folder."""
        out = os.path.join(self.d, "o")
        p = CU.make("quick", out, None)
        head, units = CU.read_units(p)
        self.assertEqual(sorted(os.listdir(out)), [".cache"])
        self.assertEqual(sorted(os.listdir(os.path.join(out, ".cache"))), ["units-quick.txt"])
        steps = {u[1] for u in units}
        self.assertEqual(steps, {"x1", "x1v", "x2", "x3", "x3b", "x4floor", "x4dem", "x5", "x6", "x7a", "x7b", "xd"})
        self.assertEqual(head["code"], REG.current_code_hash())


class TestClusterUnits(EnvCase):
    def write_units(self, n=2, code=None, tier="quick"):
        p = os.path.join(self.d, "units.txt")
        lines = ["# podsim-units-v1", "# tier %s" % tier, "# out %s" % self.d,
                 "# code %s" % (code or REG.current_code_hash()), "# units %d" % n]
        lines += ["%d x3 menu_15-30 run_x3.py" % i for i in range(1, 3)]
        with open(p, "w") as f:
            f.write("\n".join(lines) + "\n")
        return p

    def test_read_and_validate(self):
        head, units = CU.read_units(self.write_units())
        self.assertEqual(head["tier"], "quick")
        self.assertEqual(len(units), 2)
        with self.assertRaises(SystemExit):
            CU.read_units(self.write_units(n=3))
        with self.assertRaises(SystemExit):
            CU.read_units(os.path.join(self.d, "nope.txt"))
        head, _ = CU.read_units(self.write_units(code="f" * 64))
        with self.assertRaises(SystemExit):
            CU.check_code(head)
        with self.assertRaises(SystemExit):
            CU.main(["run", "--units", self.write_units(), "--index", "9"])
        bad = os.path.join(self.d, "bad.txt")
        with open(bad, "w") as f:
            f.write("1 x3 k run_x3.py\n")
        with self.assertRaises(SystemExit):
            CU.read_units(bad)

    def test_make_run_merge_small_step(self):
        """End to end on the quick tier's X3 step: list units, run each in its own process, merge, compare
        with a direct run (byte-identical outputs)."""
        out_a = os.path.join(self.d, "direct")
        out_b = os.path.join(self.d, "units")
        env = run_tier.tier_env("quick", out_a, 1)
        os.makedirs(out_a)
        subprocess.check_call([sys.executable, os.path.join(HERE, "run_x3.py")], cwd=out_a, env=env,
                              stdout=subprocess.DEVNULL)
        os.makedirs(out_b)
        env_b = run_tier.tier_env("quick", out_b, 1)
        lst = os.path.join(out_b, "l.txt")
        env_b["PODSIM_LIST_UNITS"] = lst
        subprocess.check_call([sys.executable, os.path.join(HERE, "run_x3.py")], cwd=out_b, env=env_b)
        with open(lst) as fh:
            keys = [ln.split()[1] for ln in fh]
        self.assertEqual(len(keys), 2)
        self.assertEqual(os.listdir(out_b), ["l.txt"])  # listing computes nothing
        os.remove(lst)
        del env_b["PODSIM_LIST_UNITS"]
        for k in keys:
            e = dict(env_b, PODSIM_ONLY_UNIT="x3/" + k)
            subprocess.check_call([sys.executable, os.path.join(HERE, "run_x3.py")], cwd=out_b, env=e)
            subprocess.check_call([sys.executable, os.path.join(HERE, "run_x3.py")], cwd=out_b, env=e)  # idempotent
        e = dict(env_b, PODSIM_REQUIRE_CACHED="1")
        subprocess.check_call([sys.executable, os.path.join(HERE, "run_x3.py")], cwd=out_b, env=e,
                              stdout=subprocess.DEVNULL)
        for fn in ("x3_table.csv", "x3_slopes.csv", "x3_meta.json"):
            self.assertEqual(_read(os.path.join(out_a, "x3", fn), "rb"),
                             _read(os.path.join(out_b, "x3", fn), "rb"), fn)


class TestLanes(EnvCase):
    """Grid Engine lanes (cluster/units.py plan and run-lane)."""

    def units(self, n, step="x6"):
        return [(i, step, "k%d" % i, "run_x6.py") for i in range(1, n + 1)]

    def test_every_unit_in_exactly_one_lane(self):
        for n in (1, 2, 7, 88, 4040):
            us = self.units(n)
            for lanes in (1, 2, 3, 4, 7, 32, n, n + 5):
                seen = {}
                for k in range(1, lanes + 1):
                    for u in CU.lane_units(us, k, lanes):
                        self.assertNotIn(u[0], seen, (n, lanes))
                        seen[u[0]] = k
                        self.assertEqual((u[0] - 1) % lanes, k - 1)
                self.assertEqual(sorted(seen), list(range(1, n + 1)), (n, lanes))
                sizes = [len(CU.lane_units(us, k, lanes)) for k in range(1, lanes + 1)]
                self.assertLessEqual(max(sizes) - min(sizes), 1)
        with self.assertRaises(SystemExit):
            CU.lane_units(self.units(3), 4, 3)
        with self.assertRaises(SystemExit):
            CU.lane_units(self.units(3), 0, 3)

    def test_full_tier_lanes_balanced_and_ordered(self):
        """On the full tier's real unit list, round robin keeps every lane within a few percent of the mean
        estimated cost, and a lane runs its most expensive units first."""
        out = os.path.join(self.d, "o")
        head, us = CU.read_units(CU.make("full", out, None))
        self.assertEqual(len(us), 4040)
        for lanes in (2, 3, 4, 8, 16):
            costs = []
            for k in range(1, lanes + 1):
                costs.append(sum(CU.unit_cost("full", u[1]) for u in CU.lane_units(us, k, lanes)))
            mean = sum(costs) / lanes
            self.assertLess(max(costs) / mean, 1.03, lanes)
        mine = CU.ordered(head, CU.lane_units(us, 2, 4))
        cs = [CU.unit_cost("full", u[1]) for u in mine]
        self.assertEqual(cs, sorted(cs, reverse=True))
        self.assertEqual(sorted(u[0] for u in mine), [u[0] for u in CU.lane_units(us, 2, 4)])
        import io
        buf = io.StringIO()
        hours = CU.plan(head, us, 4, 32, out=buf)
        self.assertIn("lane 4:", buf.getvalue())
        self.assertGreaterEqual(hours, 2)
        head_s = dict(head, tier="fullsmoke")
        self.assertIsNone(CU.plan(head_s, us, 3, 2, out=io.StringIO()))
        self.assertEqual(CU.ordered(head_s, us[:5]), us[:5])

    def test_run_lane_skips_cached_and_reports_failures(self):
        """run-lane skips cached units, keeps going past a failing unit, lists it and exits 1."""
        out = os.path.join(self.d, "o")
        head, us = CU.read_units(CU.make("quick", out, None))
        x3 = [u for u in us if u[1] == "x3"]
        self.assertEqual(len(x3), 2)
        lanes = len(us)  # one unit per lane: lane k is unit k
        bad = (x3[1][0], "x3", "no-such-key", "run_x3.py")
        us2 = [u if u[0] != bad[0] else bad for u in us]
        fail_path = os.path.join(self.d, "failed.txt")
        self.assertEqual(CU.run_lane(head, us2, x3[0][0], lanes, 2, fail_path), 0)
        self.assertTrue(os.path.exists(CU.cache_file(head, "x3", x3[0][2])))
        self.assertFalse(os.path.exists(fail_path))
        self.assertEqual(CU.ordered(head, CU.lane_units(us2, x3[0][0], lanes)), [x3[0]])
        self.assertTrue(CU.is_cached(head, x3[0]))
        self.assertEqual(CU.run_lane(head, us2, x3[0][0], lanes, 2, fail_path), 0)  # cached: skipped
        self.assertEqual(CU.run_lane(head, us2, bad[0], lanes, 2, fail_path), 1)
        with open(fail_path) as f:
            self.assertEqual(f.read().split()[:3], [str(bad[0]), "x3", "no-such-key"])

    def test_two_unit_lane_continues_past_failure(self):
        out = os.path.join(self.d, "o")
        head, us = CU.read_units(CU.make("quick", out, None))
        x3 = [u for u in us if u[1] == "x3"]
        # lane 1 of a two-unit list: one failing unit first, then a good one
        two = [(1, "x3", "no-such-key", "run_x3.py"), (2,) + tuple(x3[1][1:]), (3,) + tuple(x3[0][1:])]
        fail_path = os.path.join(self.d, "f.txt")
        self.assertEqual(CU.run_lane(head, two, 1, 2, 1, fail_path), 1)
        self.assertTrue(os.path.exists(CU.cache_file(head, "x3", x3[0][2])))
        with open(fail_path) as f:
            self.assertEqual(f.read().split()[0], "1")


if __name__ == "__main__":
    unittest.main()
