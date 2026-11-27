"""Scenario registry: every axis and value of the scenario catalog with its build status, the run tiers (quick, narrow,
full and the full-tier smoke test), output locations and deterministic writers.

Status values: "built" (in code and run by at least one tier), "planned" (registered, not in code),
"extension" (registered, outside the scope of the paper). Tiers (steps per tier in run_tier.STEPS):
  quick   minutes; one small block of every experiment, for every code change
  narrow  the seven study menus on nine law-convention pairs: X0, checks, X1 (with a sampled verifier), X3, X3b, X2 and its
          split, X4, X7, X6, X5 and the markdown summaries
  full    every built axis value crossed; exact where possible, sampled parts at narrow size; the paper's
          numbers come from this tier
  fullsmoke  the full tier's code paths on a tiny grid (a test, not a result tier)

Environment read by the run scripts: PODSIM_TIER (default narrow), PODSIM_OUT (output root; default the
repository's data/results), PODSIM_JOBS (worker processes, default 2), PODSIM_MP_START (multiprocessing start
method, default the platform's). PODSIM_TMAX is set by run_tier.py from the tier (240, or 360 for full).
"""
import csv
import gzip
import io
import json
import multiprocessing
import os
from fractions import Fraction

UNION = (5, 6, 10, 15, 20, 30, 45, 60)
M7 = [(15, 30), (15, 30, 60), (10, 15, 30), (6, 15, 30), (5, 15, 30), (10, 15, 20, 30), (15, 20, 30, 45, 60)]


def m85():
    """The 85-menu grid: every 2- and 3-part subset of UNION plus {10, 15, 20, 30} (85 menus)."""
    from itertools import combinations
    ms = [tuple(c) for k in (2, 3) for c in combinations(UNION, k)] + [(10, 15, 20, 30)]
    return ms


def menus_m7_m85():
    out = list(M7)
    for m in m85():
        if m not in out:
            out.append(m)
    return out


# ------------------------------------------------------------------------------------- catalog

AXES = [
    # (axis, id, description, status)
    ("break length", "L1", "grid {60, 90, ..., 240}", "built"),
    ("break length", "L2", "hybrid remainder T = B - S, S uniform on a set, present with probability p", "built"),
    ("break length", "L3u", "uniform integers [60, 240]", "built"),
    ("break length", "L3s", "discretized Beta(2,5) on [60, 240] (synthetic)", "built"),
    ("break length", "L4", "L3u and L3s on 5 s and 15 s lattices", "built"),
    ("break length", "L5", "FreeWheel Q1 2023 mid-roll minute bins 8/32/26/10/24%, uniform seconds inside, top bin cut to [240, 300]", "built"),
    ("break length", "L6", "short breaks, uniform integers [15, 60]", "built"),
    ("break length", "L7", "long breaks, uniform integers [240, 360]", "built"),
    ("break length", "L8", "bimodal live: L1 grid with prob 1 - q, stoppage breaks uniform [30, 120] with prob q, q in {0.25, 0.5, 0.75} (synthetic)", "built"),
    ("break length", "L9", "tick-accurate T (integer law plus sub-second offset)", "built"),
    ("break length", "L10", "T revised after pod construction", "extension"),
    ("hybrid", "H0", "no structured portion", "built"),
    ("hybrid", "H1", "one structured spot, S from {5, 10, 15, 20, 45}", "built"),
    ("hybrid", "H2", "S sets {15, 30}, {5, 10}, {7, 8, 12}, {60}, B from L1, p = 1", "built"),
    ("hybrid", "H3", "two structured spots (open and close), each uniform on {5, 10, 15, 20, 45}, conditioned on fitting B; convention b gives the remainder h - 2", "built"),
    ("hybrid", "H4", "p from 0 to 1", "built"),
    ("hybrid", "H5", "cap conventions (a) dynamic only, (b) K - 1", "built"),
    ("menu", "M7", "the seven study menus", "built"),
    ("menu", "M85", "85-menu grid: all 2- and 3-part subsets of {5, 6, 10, 15, 20, 30, 45, 60} plus {10, 15, 20, 30}", "built"),
    ("menu", "MR", "range menus [min, max] (arithmetic relaxation and range lever)", "built"),
    ("menu", "MX", "4- and 5-part menus; long durations 90 and 120 s", "planned"),
    ("menu", "MW", "menus implied by 15/30-dominant demand (via weights)", "built"),
    ("cap", "C3-12", "h = 3..12 and uncapped", "built"),
    ("cap", "C1-2", "h = 1, 2", "built"),
    ("cap", "C13-20", "h = 13..20", "built"),
    ("demand", "D1", "Poisson pools, fixed per-duration means over the union, five weight schemes", "built"),
    ("demand", "D2", "lambda {2, 4, 8, 16, 64, unlimited}", "built"),
    ("demand", "D3", "lambda fine grid 1 to 256, log2 steps, every weight scheme (xd)", "built"),
    ("demand", "D4", "negative binomial pools, dispersion k in {1, 4}, same means (xd, exact)", "built"),
    ("demand", "D5", "correlated pools across durations", "extension"),
    ("demand", "D6", "time-of-day or quarter-end demand shifts", "extension"),
    ("value", "V1", "lognormal per-second value, flat across durations, no floor", "built"),
    ("value", "V2", "duration premium: per-second value x (a/30)^-0.3 (synthetic; X6)", "built"),
    ("value", "V3", "mincpmpersec floor sweep, 3 levels (X6)", "built"),
    ("value", "V4", "durfloors range schedule 1-15/16-30/31+ (X6)", "built"),
    ("separation", "G1", "creative dedupe c_a <= n_a", "built"),
    ("separation", "G2", "advertiser-domain dedupe and competitive separation", "extension"),
    ("policy", "P1", "seconds-max exact", "built"),
    ("policy", "P2", "revenue-max exact (X6, sampled)", "built"),
    ("policy", "P3", "greedy by price per second, longer first on ties; P3d longest first (X6)", "built"),
    ("policy", "P4", "first-come in bid arrival order (X6)", "built"),
    ("readiness", "R1", "independent, rho {1, 0.99, 0.95, 0.90}", "built"),
    ("readiness", "R2", "share s of creatives new, rho_new < rho_old, age independent of selection: exact closed form at rho_eff (xd)", "built"),
    ("readiness", "R3", "seller anticipates readiness", "extension"),
    ("units", "J1", "integer seconds", "built"),
    ("units", "J2", "90 kHz ticks, eps sweep, systematic and random perturbations (X7)", "built"),
    ("fate", "K1", "zero pod revenue, any fate", "built"),
    ("fate", "K2", "promo backfill with a promo length menu", "extension"),
    ("fate", "K3", "clutter cost per ad (X5)", "built"),
]

SCHEMES = ("balanced", "w30", "w15", "short", "d1530")
LAMS = (2, 4, 8, 16, 64)
X7_EPS = (("1 frame (3003 ticks)", 3003), ("15 ms", 1350), ("50 ms", 4500), ("100 ms", 9000), ("0.5 s", 45000))

NARROW_LAWS = [("L1", "a"), ("L2", "a"), ("L2", "b"), ("L3u", "a"), ("L3s", "a"), ("L4u5", "a"), ("L4u15", "a"),
               ("L4s5", "a"), ("L4s15", "a")]
NEW_LAWS = [("L8q25", "a"), ("L8q50", "a"), ("L8q75", "a"),
            ("L2s1530", "a"), ("L2s1530", "b"), ("L2s510", "a"), ("L2s510", "b"),
            ("L2s7812", "a"), ("L2s7812", "b"), ("L2s60", "a"), ("L2s60", "b"), ("L2two", "a"), ("L2two", "b")]
FULL_LAWS = NARROW_LAWS + [("L5", "a"), ("L6", "a"), ("L7", "a")] + NEW_LAWS
QUICK_NEW_LAWS = [("L8q50", "a"), ("L2s7812", "b"), ("L2two", "b")]
HYBRID_LAWS = ("L2", "L2s1530", "L2s510", "L2s7812", "L2s60", "L2two")

MENU_SAMPLE_SEED = "menu-sample-v1"
MENU_SAMPLE_N = 24


def menu_sample():
    """X5 and X6 full-tier menus: the seven study menus plus a deterministic sample of 24 menus from the rest
    of the 85-menu grid (random.Random(MENU_SAMPLE_SEED).sample over the sorted remainder; string seeding is
    identical across platforms and Python 3 versions). The list is also written to each tier's catalog."""
    import random
    rest = sorted((m for m in m85() if m not in M7), key=lambda m: (len(m), m))
    pick = random.Random(MENU_SAMPLE_SEED).sample(rest, MENU_SAMPLE_N)
    return list(M7) + sorted(pick, key=lambda m: (len(m), m))


def lawkey(l, c):
    """Law label with the convention for hybrid laws (convention matters only when a structured spot exists)."""
    return l + c if l in HYBRID_LAWS else l


TIERS = {
    "quick": dict(
        tmax=240, menus=[(15, 30), (6, 15, 30)], laws=[("L1", "a"), ("L2", "a"), ("L2", "b"), ("L3u", "a")] + QUICK_NEW_LAWS,
        caps=[3, 4, 6, 8, None], schemes=("balanced", "d1530"), lams=(8, 64), rhos=(1.0, 0.95),
        x3_menus=[(15, 30), (6, 15, 30)], x3_caps=[3, 4, 6, 8, 12], x3b=True,
        x2_menus=[(15, 30), (6, 15, 30)], x2_add=(5, 6, 10, 15, 20, 30, 45, 60), range_n=200, xd_range_n=100,
        verify=[("L2", "a", (15, 30), 8, "balanced")], verify_n=2000, verify_caps=[3, 4, 6, 8],
        x7_menus=[(15, 30), (6, 15, 30)], x7_laws=[("L3u", "a"), ("L2two", "b")], x7_caps=[4, 6, None], x7_eps=X7_EPS[:2],
        x7_n=300, x7_lam=16, summaries=False,
        xd_menus=[(15, 30), (6, 15, 30)], xd_laws=[("L3u", "a"), ("L8q50", "a"), ("L2s7812", "b"), ("L2two", "b")],
        xd_caps=[3, 4, 6, None], xd_schemes=("balanced", "d1530"), xd_lams=(1, 16, 256), xd_ks=(1, 4),
        xd_r2_scen=[("poisson", "balanced", 16)]),
    "narrow": dict(
        tmax=240, menus=M7, laws=NARROW_LAWS, caps=list(range(3, 13)) + [None], schemes=SCHEMES, lams=LAMS,
        rhos=(1.0, 0.95), x3_menus=M7, x3_caps=list(range(3, 13)), x3b=True,
        x2_menus=M7, x2_add=(5, 6, 10, 15, 20, 30, 45, 60), range_n=4000,
        verify=[("L2", "a", (15, 30), 8, "balanced"), ("L2", "b", (6, 15, 30), 8, "balanced"),
                ("L3u", "a", (10, 15, 30), 4, "d1530"), ("L3s", "a", (15, 20, 30, 45, 60), 16, "w30"),
                ("L1", "a", (5, 15, 30), 2, "short"), ("L4u5", "a", (10, 15, 20, 30), 64, "w15")],
        verify_n=100000, verify_caps=[3, 4, 6, 8, 12],
        x7_menus=M7, x7_laws=[("L1", "a"), ("L2", "a"), ("L3u", "a")], x7_caps=[4, 6, 8, None], x7_eps=X7_EPS,
        x7_n=10000, x7_lam=16, summaries=True),
    "full": dict(
        tmax=360, menus=None, laws=FULL_LAWS, caps=list(range(1, 21)) + [None], schemes=SCHEMES, lams=LAMS,
        rhos=(1.0, 0.99, 0.95, 0.90), x3_menus=None, x3_caps=list(range(1, 21)), x3b=True,
        x2_menus=None, x2_add=(5, 6, 10, 15, 20, 30, 45, 60), range_n=2000, xd_range_n=1000,
        verify=None, verify_n=100000, verify_caps=[3, 4, 6, 8, 12],
        x7_menus=None, x7_laws=FULL_LAWS,
        x7_caps=list(range(1, 21)) + [None], x7_eps=X7_EPS, x7_n=10000, x7_lam=16, summaries=False,
        xd_menus=None, xd_laws=FULL_LAWS, xd_caps=list(range(1, 21)) + [None], xd_schemes=SCHEMES,
        xd_lams=(1, 2, 4, 8, 16, 32, 64, 128, 256), xd_ks=(1, 4),
        xd_r2_scen=[("poisson", "balanced", 16), ("poisson", "d1530", 16), ("poisson", "balanced", 64),
                    ("nb1", "d1530", 16)]),
}

# fullsmoke: the full tier's code paths (TMAX 360, gzipped tables, streamed assembly, every built law and both
# conventions, the menu-sample machinery) on a tiny grid, so they are tested on any machine in minutes. Not a
# result tier.
TIERS["fullsmoke"] = dict(TIERS["full"], menus=[(15, 30), (5, 6, 60)], caps=[2, 4, 12, None],
                          schemes=("d1530",), lams=(16,), rhos=(1.0, 0.95), x3_menus=[(15, 30)], x3_caps=[2, 8],
                          x2_menus=[(15, 30)], x2_add=(5, 60), range_n=40, xd_range_n=20, verify=[("L7", "a", (15, 30), 8, "balanced")],
                          verify_n=200, verify_caps=[3, 12], x7_menus=[(15, 30)], x7_caps=[3, None],
                          x7_eps=X7_EPS[:1], x7_n=100, xd_menus=[(15, 30)], xd_caps=[2, None], xd_schemes=("balanced",),
                          xd_lams=(4,), xd_ks=(1,), xd_r2_scen=[("nb1", "balanced", 4)])
BIG_TIERS = ("full", "fullsmoke")


def big(tier=None):
    """True for tiers that use the full tier's storage and assembly paths (gzipped tables, streaming)."""
    return (tier or tier_name()) in BIG_TIERS


# Steps whose grid differs by tier and the axes each tier exercises (for the catalog).
FULL_SKIPPED = [
    "Markdown summaries (x1, x3, x2, d3, x7 summary.md): the full tables are too large to summarize in memory "
    "with the narrow-tier report code; the full tier writes tables, metadata, and the catalog.",
    "Registered extensions, not built: L10 (break length revised after pod construction: needs a second "
    "decision stage and a revision law), D5 (correlated pools across durations: breaks the per-duration "
    "independence that makes the demand sums exact; needs a joint count law), D6 (time-of-day or quarter-end "
    "demand shifts: no public shape to anchor it), G2 (advertiser-domain dedupe and competitive separation: needs "
    "an advertiser layer over creatives), R3 (seller anticipates readiness: a different selection problem, "
    "readiness enters the objective), K2 (promo backfill with a promo length menu: changes the fate of unfilled "
    "time, not the floor; needs a promo menu source).",
    "Planned, not built: MX (4- and 5-part menus, 90 and 120 s durations).",
    "X5 (clutter frontier) and X6 (revenue-max, floors, greedy) run on 31 menus (the seven study menus plus a "
    "deterministic sample of 24 from the 85-menu grid, catalog/menu_sample.csv), not all 86, on every built law "
    "and caps 3 to 12 and uncapped, with lambda in {8, 64} (X6) or {16, 64} (X5) and weights balanced and "
    "15/30-dominant; X6 at N = 4,000 breaks per block and X5 at 2,000 breaks per scenario (narrow: 20,000 and "
    "4,000), so the full tier is broader but its per-cell standard errors are about 2.2 and 1.4 times the "
    "narrow ones.",
    "X1 sampled verifier and X7 part B (Monte Carlo) run at narrow size and on the narrow menus and laws, not "
    "crossed with the full grid (both verify exact tables that the full tier computes exactly).",
    "X3 and X3b (hybrid probability p) use B from L1 and S from the spot set {5, 10, 15, 20, 45}, as in the narrow tier; H2 and H3 "
    "enter X1, X2, X4, X5, X6, X7 and the demand sweep at p = 1.",
    "R2 (readiness by creative age) is exact only under independence of age from selection; it is reported on "
    "four demand scenarios per cell (xd/xd_r2 table), not crossed with every demand scenario.",
]


def tier_name():
    t = os.environ.get("PODSIM_TIER", "narrow")
    if t not in TIERS:
        raise SystemExit("unknown tier %r (expected one of: %s)" % (t, ", ".join(sorted(TIERS))))
    return t


def config(tier=None):
    t = tier or tier_name()
    c = dict(TIERS[t])
    c["tier"] = t
    if c["menus"] is None:
        c["menus"] = menus_m7_m85()
    for k in ("x3_menus", "x2_menus", "x7_menus", "xd_menus"):
        if k in c and c[k] is None:
            c[k] = menus_m7_m85()
    if c["verify"] is None:
        c["verify"] = TIERS["narrow"]["verify"]
    return c


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def out_root():
    return os.environ.get("PODSIM_OUT") or os.path.join(repo_root(), "data", "results")


def out_dir(name):
    d = os.path.join(out_root(), name)
    os.makedirs(d, exist_ok=True)
    return d


def jobs():
    return int(os.environ.get("PODSIM_JOBS", "2"))


def pool(n=None):
    """Process pool that fails instead of hanging when a worker dies (SIGKILL, out-of-memory kill):
    concurrent.futures raises BrokenProcessPool, whereas multiprocessing.Pool waits forever for the lost task."""
    from concurrent.futures import ProcessPoolExecutor
    ctx = multiprocessing.get_context(os.environ.get("PODSIM_MP_START") or None)
    return ProcessPoolExecutor(max_workers=n or jobs(), mp_context=ctx)


# ---------------------------------------------------------------------------- deterministic writers

FLOAT_DIGITS = 9


def canon(x):
    """Deterministic, platform-independent rendering: floats rounded to FLOAT_DIGITS decimals (negative zero
    folded to zero), Fractions as 'p/q' strings, tuples as lists, dict keys as strings (sorted on output)."""
    if isinstance(x, bool) or x is None or isinstance(x, (int, str)):
        return x
    if isinstance(x, float):
        if x != x:
            return "nan"
        v = round(x, FLOAT_DIGITS)
        return 0.0 if v == 0 else v
    if isinstance(x, Fraction):
        return str(x)
    if isinstance(x, dict):
        return {str(k): canon(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [canon(v) for v in x]
    return str(x)


def write_json(path, obj):
    txt = json.dumps(canon(obj), sort_keys=True, indent=None, separators=(",", ":"))
    _write_text(path, txt + "\n")


def cell(v):
    v = canon(v)
    if isinstance(v, float):
        s = ("%." + str(FLOAT_DIGITS) + "f") % v
        s = s.rstrip("0").rstrip(".") if "." in s else s
        return "0" if s in ("-0", "") else s
    return "" if v is None else str(v)


def write_csv(path, rows, fields=None):
    fields = fields or list(rows[0].keys())
    buf = io.StringIO()
    wr = csv.writer(buf, lineterminator="\n")
    wr.writerow(fields)
    for r in rows:
        wr.writerow([cell(r.get(f)) for f in fields])
    _write_text(path, buf.getvalue())


def _write_text(path, txt):
    data = txt.encode("utf-8")
    if path.endswith(".gz"):
        bio = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=bio, mtime=0, compresslevel=6) as gz:
            gz.write(data)
        data = bio.getvalue()
    tmp = _tmp_name(path)
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _tmp_name(path):
    """Temporary file next to path, unique per process, so concurrent writers never share a temp file."""
    import socket
    return "%s.%s.%d.tmp" % (path, socket.gethostname().split(".")[0], os.getpid())


def write_text(path, txt):
    _write_text(path, txt)


def table_name(base):
    """CSV file name for a big table: gzip in the full tier."""
    return base + (".csv.gz" if big() else ".csv")


def write_code_record(d):
    """Bind an output folder to the code that produced it: the code hash (current_code_hash()), its file count and
    the whole-tree digest (tree_digest()) go into the folder's timing.json, which manifests exclude, so the
    expected manifests do not depend on the code version."""
    path = os.path.join(d, "timing.json")
    cur = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                cur = json.load(f)
        except ValueError:
            cur = {}
    cur["code_sha256"] = current_code_hash()
    cur["code_files"] = len(code_files())
    cur["tree_sha256"], cur["tree_files"] = tree_digest()
    os.makedirs(d, exist_ok=True)
    _write_text(path, json.dumps(cur, sort_keys=True, indent=1))


def write_timing(d, name, seconds):
    """Timing goes only to timing.json files, which manifests exclude."""
    path = os.path.join(d, "timing.json")
    cur = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                cur = json.load(f)
        except ValueError:
            cur = {}
    cur[name] = round(seconds, 3)
    cur["code_sha256"] = current_code_hash()
    cur["tree_sha256"], cur["tree_files"] = tree_digest()
    _write_text(path, json.dumps(cur, sort_keys=True, indent=1))


def catalog_rows():
    return [dict(axis=a, id=i, description=d, status=s) for a, i, d, s in AXES]


def _conv(v):
    if v == "":
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def read_csv(path):
    """Rows of a CSV written by write_csv (plain or .gz), numeric strings converted back to int or float."""
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", newline="") as fh:
        rd = csv.DictReader(fh)
        return [{k: _conv(v) for k, v in r.items()} for r in rd]


def iter_csv(path):
    """Stream rows of a CSV written by write_csv (plain or .gz), numeric strings converted as in read_csv."""
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", newline="") as fh:
        for r in csv.DictReader(fh):
            yield {k: _conv(v) for k, v in r.items()}


class CsvStream(object):
    """Write a CSV incrementally with the deterministic cell format (header from the first row)."""

    def __init__(self, path, fields=None):
        self.path = path
        self.tmp = _tmp_name(path)
        self.fh = gzip.GzipFile(filename="", mode="wb", fileobj=open(self.tmp, "wb"), mtime=0) if path.endswith(".gz") \
            else open(self.tmp, "wb")
        self.fields = list(fields) if fields else None
        self.n = 0
        self.closed = False
        import atexit
        atexit.register(self._discard)  # a run that stops before close() leaves no temp file behind
        if self.fields:
            buf = io.StringIO()
            csv.writer(buf, lineterminator="\n").writerow(self.fields)
            self.fh.write(buf.getvalue().encode("utf-8"))

    def write(self, rows):
        buf = io.StringIO()
        wr = csv.writer(buf, lineterminator="\n")
        for r in rows:
            if self.fields is None:
                self.fields = list(r.keys())
                wr.writerow(self.fields)
            wr.writerow([cell(r.get(f)) for f in self.fields])
            self.n += 1
        self.fh.write(buf.getvalue().encode("utf-8"))

    def _discard(self):
        if not self.closed:
            try:
                self.fh.close()
            except Exception:
                pass
            try:
                os.remove(self.tmp)
            except OSError:
                pass

    def close(self):
        self.closed = True
        f = self.fh
        if isinstance(f, gzip.GzipFile):
            raw = f.fileobj
            f.close()
            raw.close()
        else:
            f.close()
        os.replace(self.tmp, self.path)


# ------------------------------------------------------------------------------ resumable unit cache

# The code whose edits can change a cached unit result: the simulator package, the scripts that compute units
# (each also defines its unit functions) and the vendored engines. Not hashed: the report and summary
# scripts (make_summaries.py, run_x7_report.py), run_x0.py, run_checks.py,
# run_x2_split.py, run_tier.py, cluster/, tests/ and documentation. Those steps read cached or written results
# but never feed a unit cache, so editing them does not invalidate a long run's cache.
UNIT_SCRIPTS = ("run_x1.py", "run_x2.py", "run_x3.py", "run_x3b.py", "run_x4.py", "run_x5.py", "run_x6.py",
                "run_x7.py", "run_xd.py")
CODE_FILES_GLOBS = ("podsim/*.py",) + UNIT_SCRIPTS + ("vendor/sumset-undershoot/ENGINES.sha256",
                                                      "vendor/sumset-undershoot/undershoot/*.py")


def code_files(here=None):
    """Sorted relative paths (with '/' separators) of the files code_hash() covers."""
    import glob
    here = here or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = set()
    for g in CODE_FILES_GLOBS:
        hits = glob.glob(os.path.join(here, g))
        if not hits and not any(ch in g for ch in "*?["):
            raise RuntimeError("code_hash: expected file %s is missing" % g)
        files.update(hits)
    return sorted(os.path.relpath(p, here).replace(os.sep, "/") for p in files)


def code_hash(here=None):
    """sha256 over the code that determines cached unit results (code_files(): the package, the unit-computing
    run_x*.py scripts and the vendored engines), plus an interpreter tag. Recorded in every cache entry; a cache
    entry from different code is refused, never silently reused. Float totals use math.fsum (podsim/numeric.py),
    so the change of the builtin float sum in Python 3.12 does not reach them; the tag (Python before or from
    3.12) is a guard, so units from different interpreter generations are never mixed in one merge."""
    import hashlib
    import sys
    here = here or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    h = hashlib.sha256()
    h.update(("python-sum-%s\n" % ("new" if sys.version_info >= (3, 12) else "old")).encode("ascii"))
    for rel in code_files(here):
        with open(os.path.join(here, *rel.split("/")), "rb") as f:
            data = f.read()
        h.update(rel.encode("utf-8") + b"\0" + hashlib.sha256(data).hexdigest().encode("ascii") + b"\n")
    return h.hexdigest()


_CODE_HASH = None
_TREE = None
TREE_DIRS = ("cluster", "expected", "podsim", "tests", "vendor")


def tree_digest(here=None):
    """(sha256, file count) over the code tree: the top-level files (scripts, documentation, licenses, citation)
    and the folders in TREE_DIRS (package, tests, cluster runner, vendored engines, expected manifests), without
    caches; data and output folders beside them are not included. Binds an output folder to the whole
    release that produced it, unlike code_hash(), which covers only the code that can change a cached unit."""
    global _TREE
    default = here is None
    if default and _TREE is not None:
        return _TREE
    import hashlib
    here = here or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = []
    for root, dirs, fs in os.walk(here):
        if root == here:  # only the code tree: top-level files and these folders, never data or outputs
            dirs[:] = sorted(x for x in dirs if x in TREE_DIRS)
        else:
            dirs[:] = sorted(x for x in dirs if x not in ("__pycache__", ".pytest_cache"))
        for f in fs:
            if f.endswith((".pyc", ".pyo")) or f == ".DS_Store":
                continue
            files.append(os.path.relpath(os.path.join(root, f), here).replace(os.sep, "/"))
    h = hashlib.sha256()
    for rel in sorted(files):
        with open(os.path.join(here, rel), "rb") as fh:
            h.update(rel.encode("utf-8") + b"\0" + hashlib.sha256(fh.read()).digest())
    out = (h.hexdigest(), len(files))
    if default:
        _TREE = out
    return out


def current_code_hash():
    global _CODE_HASH
    if _CODE_HASH is None:
        _CODE_HASH = code_hash()
    return _CODE_HASH


class StaleCacheError(RuntimeError):
    pass


def cache_path(step, key):
    d = os.path.join(out_root(), ".cache", tier_name(), step)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, key + ".json.gz")


def args_signature(args):
    """sha256 of a unit's arguments (canonical JSON; anything not JSON-native by repr). Stored with the cache
    entry, so an entry computed for a different grid under the same key is refused."""
    import hashlib

    def norm(x):
        if isinstance(x, dict):
            return {"__dict__": sorted(([repr(k), norm(v)] for k, v in x.items()), key=lambda kv: kv[0]),
                    "__type__": type(x).__name__, "__attrs__": norm(getattr(x, "k", None))}
        if isinstance(x, (list, tuple)):
            return [norm(v) for v in x]
        if isinstance(x, float):
            return repr(x)
        if x is None or isinstance(x, (bool, int, str)):
            return x
        return repr(x)
    return hashlib.sha256(json.dumps(norm(args), sort_keys=True).encode("utf-8")).hexdigest()


def cache_load(p, sig=None):
    """Value stored at p, or None if absent. Raises StaleCacheError if p was written by different code or for
    different unit arguments (sig), and ValueError (naming the file) if it is not a cache entry."""
    if not os.path.exists(p):
        return None
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            obj = json.load(f)
    except (ValueError, OSError, EOFError):
        raise ValueError("corrupt cache file %s: delete it and rerun its unit" % p)
    if not isinstance(obj, dict) or "code" not in obj or "value" not in obj:
        raise ValueError("%s is not a cache entry of this code (no code hash): delete it and rerun" % p)
    if obj["code"] != current_code_hash():
        raise StaleCacheError("cache file %s was produced by a different code version (%s, current %s); "
                              "refusing to mix versions. Delete %s/.cache (and any per-step .cache folders) "
                              "or use a new output directory, then rerun."
                              % (p, obj["code"][:12], current_code_hash()[:12], out_root()))
    if sig is not None and obj.get("args") != sig:
        raise StaleCacheError("cache file %s was computed for different unit arguments (another grid or tier under "
                              "the same key); refusing to reuse it. Use a separate output directory per tier." % p)
    return obj["value"]


def cache_store(p, value, sig=None):
    """Atomic write of a cache entry (temp file then rename), so a stopped run never leaves a partial entry."""
    # key order is kept (not sorted): rows written from cached dicts take their CSV column order from it
    txt = json.dumps(dict(code=current_code_hash(), args=sig, value=value))
    tmp = _tmp_name(p)
    try:
        with gzip.GzipFile(tmp, "wb", compresslevel=3, mtime=0) as f:
            f.write(txt.encode("utf-8"))
        os.replace(tmp, p)
    except BaseException:
        try:
            os.remove(tmp)  # disk full or killed mid-write: leave no temp file behind
        except OSError:
            pass
        raise


def cached(step, key, fn, raw=False, sig=None):
    """Resume cache for per-item work: result of fn() stored as gzipped JSON under <out>/.cache/<tier>/<step>/<key>.json.gz
    with the code hash; excluded from manifests. The value returned is always the JSON round trip of the stored
    value (canon(fn()), or fn() itself when raw is True, which keeps full float precision), so a fresh and a
    cached result are identical."""
    p = cache_path(step, key)
    v = cache_load(p, sig)
    if v is not None:
        return v
    if require_cached():
        raise MissingUnitsError("unit %s/%s is not cached (merge mode): run it first" % (step, key))
    v = fn()
    v = json.loads(json.dumps(v if raw else canon(v)))
    cache_store(p, v, sig)
    return v


class MissingUnitsError(RuntimeError):
    pass


def require_cached():
    """Merge mode (PODSIM_REQUIRE_CACHED=1, set by the cluster merge): every unit must come from the cache."""
    return os.environ.get("PODSIM_REQUIRE_CACHED", "") == "1"


def only_unit():
    """Unit mode (PODSIM_ONLY_UNIT=<step>/<key>, set by the cluster unit runner): compute that one unit only."""
    v = os.environ.get("PODSIM_ONLY_UNIT", "")
    return tuple(v.split("/", 1)) if v else None


class _UnitCall(object):
    """Picklable wrapper: (key, args) -> cached value (works with fork and spawn start methods)."""

    def __init__(self, step, fn, raw):
        self.step, self.fn, self.raw = step, fn, raw

    def __call__(self, item):
        key, args = item
        return cached(self.step, key, lambda: self.fn(args), raw=self.raw, sig=args_signature(args))


def check_unit_keys(step, items):
    keys = [k for k, _ in items]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate unit keys in step %s" % step)
    for k in keys:
        if not k or "/" in k or k.startswith("."):
            raise ValueError("bad unit key %r in step %s" % (k, step))


def iter_units(step, items, fn, raw=False, n_jobs=None):
    """Yield fn(args) for every (key, args) in items through the unit cache, in item order, using a process pool
    (streaming: only a few results are held at once). In merge mode, missing units are listed and the run stops
    before computing anything."""
    check_unit_keys(step, items)
    if require_cached():
        missing = [k for k, _ in items if not os.path.exists(cache_path(step, k))]
        if missing:
            raise MissingUnitsError("merge refused: %d unit(s) of step %s missing, for example %s"
                                    % (len(missing), step, ", ".join(missing[:5])))
    call = _UnitCall(step, fn, raw)
    nj = n_jobs or jobs()
    if nj > 1 and len(items) > 1 and not require_cached():
        # bounded window: at most 2 * nj results in flight, so a resumed run (every unit cached, workers far
        # faster than the parent's CSV writing) cannot pile all results up in the parent's memory
        from collections import deque
        with pool(nj) as p:
            it = iter(items)
            win = deque()
            for x in it:
                win.append(p.submit(call, x))
                if len(win) >= 2 * nj:
                    break
            while win:
                v = win.popleft().result()
                for x in it:
                    win.append(p.submit(call, x))
                    break
                yield v
    else:
        for it in items:
            yield call(it)


def map_units(step, items, fn, raw=False, n_jobs=None):
    return list(iter_units(step, items, fn, raw=raw, n_jobs=n_jobs))


def run_one_unit(step, items, fn, key, raw=False):
    """Compute (or confirm cached) the single unit `key` of a step. Returns True if computed now."""
    check_unit_keys(step, items)
    d = dict(items)
    if key not in d:
        raise KeyError("no unit %r in step %s" % (key, step))
    p = cache_path(step, key)
    sig = args_signature(d[key])
    if cache_load(p, sig) is not None:
        return False
    cached(step, key, lambda: fn(d[key]), raw=raw, sig=sig)
    return True


def list_units_path():
    """Unit listing mode (PODSIM_LIST_UNITS=<file>, set by `cluster/units.py make`): scripts append their units."""
    return os.environ.get("PODSIM_LIST_UNITS", "")


def units_only(specs):
    """specs: [(step, items, fn, raw)]. In listing mode append 'step key' lines to the listing file; in unit
    mode compute the one requested unit if it belongs to these steps. Returns True when the caller must stop
    (listing or unit mode), False for a normal run."""
    lp = list_units_path()
    if lp:
        lines = []
        for step, items, fn, raw in specs:
            check_unit_keys(step, items)
            lines.extend("%s %s" % (step, k) for k, _ in items)
        with open(lp, "a") as f:
            for ln in lines:
                f.write(ln + "\n")
        return True
    ou = only_unit()
    if ou:
        for step, items, fn, raw in specs:
            if step == ou[0]:
                run_one_unit(step, items, fn, ou[1], raw=raw)
        return True
    return False
