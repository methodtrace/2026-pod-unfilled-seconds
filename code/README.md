# Pod simulator for structural unfilled seconds in live CTV ad pods

Standard-library Python, 3.9 or newer (results were identical on the platforms listed under Python versions below). Computes the structural floor of unfilled pod seconds exactly (duration menu, maximum ads per pod, break length), computes demand and readiness losses exactly where the seconds-max fill allows it (and samples the rest under common random numbers), and decomposes unfilled seconds by an exact accounting identity into structural, demand and readiness parts, with the structural floor split into arithmetic and cap parts at unlimited demand.

Companion papers cited in the code by short names: the undershoot companion is the paper on undershoot of h-fold sumsets, whose exact engines are vendored here; the knapsack companion is the paper on two-capacity knapsack conditions for value-cardinality hulls, whose necessary conditions X5 checks on every simulated hull pair (it also defines cap convention b); the regularity companion is the paper on regularity of sumsets, whose non-CM bound `run_checks.py` checks; the DAI timing companion is the paper on trigger timing and deadline readiness in dynamic ad insertion, whose readiness definition the simulator uses. The paper's reference list gives the full citations.

- `podsim/`: the package (structural floor, exact pod construction, break-length laws, pools, decomposition, checks; `numeric.py` for version-independent sums).
- `vendor/sumset-undershoot/`: the development engines of the undershoot companion, used as an exact oracle and vendored unmodified from its development code; the companion's public release (cited in `vendor/sumset-undershoot/CITATION.cff`) restructures the same engines, and `tests/test_engine_equivalence.py` compares the two when that package is installed. File hashes are checked at import against `ENGINES.sha256`. Another copy can be used by setting `UNDERSHOOT_ENGINES` to its folder; its six `undershoot/*.py` files must have the same hashes.
- `tests/`: `python3 -m unittest tests.test_podsim tests.test_x4 tests.test_x5 tests.test_x6 tests.test_new_axes tests.test_units tests.test_numeric tests.test_decomposition tests.test_engine_equivalence tests.test_review_fixes tests.test_round5` (from `code/`), or `python3 -m unittest -q` to discover all.
- `run_x0.py`, `run_checks.py`: regression checks against two tables of fixed reference values (computed independently of the dynamic program) and the consistency checks.
- `run_all.sh`: one command for a whole tier (`sh code/run_all.sh --tier quick|narrow|full [--out DIR] [--check] [--jobs N]`); see DESIGN.md. `PYTHON=/path/to/python3 sh code/run_all.sh ...` picks the interpreter.
- `run_x1.py`, `run_x3.py`, `run_x3b.py`, `run_x2.py`, `run_x4.py`, `run_x5.py`, `run_x6.py`, `run_x7.py`, `run_xd.py`: the experiments (exact where possible; `run_xd.py` is the demand sweep: fine lambda grid, negative binomial pools, readiness by creative age).
- `analysis_rules.py`: exact coverage of the configuration rules on a full-tier output (recomputes every structural value and checks it against the tier's table); `figures.py`: the four figures from a full-tier output's extracts (needs matplotlib, the only non-standard-library dependency, used for figures only); `extract.py`: the subsets of the large tables the figures need (last step of the full tier).
- `cluster/`: run a tier on Grid Engine (a few multi-core lanes and a held merge job, `cluster/submit.sh`) or as a SLURM job array (submitted in batches of at most 1,000 tasks), and merge the units into the same files (`cluster/README.md`).
- `make_summaries.py`, `run_x7_report.py`: the markdown summaries.
- `expected/MANIFEST-quick.sha256`, `expected/MANIFEST-narrow.sha256`: sha256 of every result file of the quick and narrow tiers; `--check` compares a run against them. For `.gz` files the hash is of the decompressed content, so manifests do not depend on the zlib build.
- `DESIGN.md`: the model as implemented, every design choice with its source (cited specification, industry figure or synthetic), and the implementation choices.

## Python versions

Python 3.12 changed the builtin `sum()` of floats (it now compensates rounding error), so a float total could differ in its last bits between 3.11 and 3.12. Sums are evaluated in a fixed order, and float totals over a collection, where the order of the terms could vary, go through `podsim.numeric.xsum`: `math.fsum` (correctly rounded, the same on every version and in any order) when a term is a float, and the exact builtin sum for integers and Fractions. Running totals accumulated with `+=` (for example in `podsim/exact.py`, `podsim/pools.py` and `podsim/levers.py`) add their terms in a fixed order, which gives the same IEEE result on every version. Results were identical on macOS with Python 3.15 and on Linux with Python 3.11, 3.12 and 3.13, with the stock zlib and with zlib-ng (manifests hash the decompressed content of `.gz` files, so the zlib build does not enter them). The unit cache still records whether a unit ran on Python before or from 3.12, so a merge never mixes the two.

## Environment variables

| Variable | Meaning |
| --- | --- |
| `PODSIM_TIER` | tier for a single script (default narrow); set by `run_tier.py` |
| `PODSIM_OUT` | output root (default the repository's `data/results`); set by `run_tier.py` |
| `PODSIM_JOBS` | worker processes (default 2) |
| `PODSIM_MP_START` | multiprocessing start method (default the platform's) |
| `PODSIM_TMAX` | largest target in seconds of the exact engines (240, or 360 for the full tier); set by `run_tier.py` |
| `UNDERSHOOT_ENGINES` | folder of the undershoot engines (default `vendor/sumset-undershoot`) |

`PODSIM_REQUIRE_CACHED`, `PODSIM_ONLY_UNIT` and `PODSIM_LIST_UNITS` are set by the cluster runner (merge, unit and listing modes).

## Unit cache and code hash

Each unit's result is cached under `OUT/.cache/<tier>/<step>/<key>.json.gz` with `registry.code_hash()`, a sha256 over exactly the code that can change a cached unit: the `podsim` package, the unit-computing scripts (`run_x1.py`, `run_x2.py`, `run_x3.py`, `run_x3b.py`, `run_x4.py`, `run_x5.py`, `run_x6.py`, `run_x7.py`, `run_xd.py`) and the vendored engines, plus the interpreter tag above. Editing the report and summary scripts, `run_tier.py`, the cluster scripts, the tests or the documentation leaves the hash, and so a long run's cache, valid (`tests.test_units`, `test_code_hash_scope`). An entry written by other code is refused, never reused.

License: Apache-2.0 for the code (`LICENSE`), CC BY 4.0 for the data (`LICENSE-data.md`). Cite as in `CITATION.cff`.
