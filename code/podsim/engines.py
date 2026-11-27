"""Load the pinned exact undershoot engines (sumset-undershoot) from their own directory, without copying.

The location defaults to code/vendor/sumset-undershoot (the exact engines of the undershoot companion, the paper on
undershoot of h-fold sumsets, vendored unmodified; the companion's public release restructures the same engines,
and tests/test_engine_equivalence.py compares the two) and can be overridden by the environment variable
UNDERSHOOT_ENGINES. Every imported engine
file is hashed and compared with
vendor/sumset-undershoot/ENGINES.sha256; a mismatch raises, so a run can never silently use different engines.
"""
import hashlib
import importlib
import os
import sys

VENDORED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor", "sumset-undershoot")
UNDERSHOOT_ENGINES = os.environ.get("UNDERSHOOT_ENGINES", VENDORED)
IMPORTED = ["undershoot/__init__.py", "undershoot/common.py", "undershoot/engine_a.py",
            "undershoot/engine_b.py", "undershoot/engine_c.py", "undershoot/fan.py"]


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def pinned_hashes():
    """The pins shipped with this package (vendor/sumset-undershoot/ENGINES.sha256), also when UNDERSHOOT_ENGINES
    points elsewhere: an override must carry byte-identical engines, so it can relocate them but not change them."""
    out = {}
    with open(os.path.join(VENDORED, "ENGINES.sha256")) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            h, p = line.split()
            out[p] = h
    return out


def verify():
    """Return {path: sha256} for every imported file; raise if any differs from the pinned list."""
    pins = pinned_hashes()
    got = {}
    for p in IMPORTED:
        h = _sha256(os.path.join(UNDERSHOOT_ENGINES, p))
        if pins.get(p) != h:
            raise RuntimeError("undershoot engine file %s has sha256 %s, pinned %s" % (p, h, pins.get(p)))
        got[p] = h
    return got


HASHES = verify()
while UNDERSHOOT_ENGINES in sys.path:
    sys.path.remove(UNDERSHOOT_ENGINES)
sys.path.insert(0, UNDERSHOOT_ENGINES)  # first on the path, so no other package named undershoot shadows it
engine_a = importlib.import_module("undershoot.engine_a")
engine_b = importlib.import_module("undershoot.engine_b")
engine_c = importlib.import_module("undershoot.engine_c")
fan = importlib.import_module("undershoot.fan")
common = importlib.import_module("undershoot.common")
for _m in (engine_a, engine_b, engine_c, fan, common):
    if not os.path.realpath(_m.__file__).startswith(os.path.realpath(UNDERSHOOT_ENGINES) + os.sep):
        raise RuntimeError("undershoot engine module %s imported from %s, not from the verified folder %s"
                           % (_m.__name__, _m.__file__, UNDERSHOOT_ENGINES))
