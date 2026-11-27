"""Analysis extracts of a full-tier output: the subsets of the large tables that the coverage tables and figures
need, small enough to travel with the results while the full tables stay where the tier ran.

Usage: python3 extract.py [--out DIR]   (DIR defaults to the current directory, where the tier runner starts it)
Writes DIR/extracts/*.csv.gz and DIR/extracts/README.md. Deterministic (rows in table order, gzip mtime 0).
Reads only files the tier wrote; computes nothing new. Not part of the code hash (feeds no unit cache).

Extracts (study menus = the seven menus of the narrow grid):
  x1_structural   X1 rows at demand unlimited and rho = 1, every menu, law and cap (the structural floor and its
                  split: rules 1 to 6, figures 1 and 2)
  x1_m7           X1 rows of the study menus at rho 1 and 0.95, every demand scenario (the identity across demand)
  xd_m7           demand-sweep rows of the study menus (figure 3: the decomposition across demand depth)
  x2_m7           X2 rows of the study menus (levers, including the sampled range lever and its sweep)
  x7a_m7          X7 part A rows of the study menus (integer seconds versus ticks)
  x7a_l3          X7 part A rows of every menu on L1, L2 (a) and L3u (a), the three laws the tick study reports
  x5_frontier_m7  X5 frontier rows of the study menus (figure 4: the clutter frontier)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from podsim import registry as REG  # noqa: E402

M7 = {" ".join(map(str, m)) for m in REG.M7}
X7_LAWS = {("L1", "a"), ("L2", "a"), ("L3u", "a")}   # the three laws the tick study reports, every menu


def find(d, base):
    for ext in (".csv.gz", ".csv"):
        p = os.path.join(d, base + ext)
        if os.path.exists(p):
            return p
    return None


def menu_of(r):
    m = r.get("menu")
    if m is None:
        return None
    m = str(m).strip("{}").replace(",", " ")
    return " ".join(m.split())


SPECS = [
    ("x1_structural", "x1", "x1_table", lambda r: r["weights"] == "unlimited" and float(r["rho"]) == 1.0),
    ("x1_m7", "x1", "x1_table", lambda r: menu_of(r) in M7 and float(r["rho"]) in (1.0, 0.95)),
    ("xd_m7", "xd", "xd_table", lambda r: menu_of(r) in M7),
    ("x2_m7", "x2", "x2_table", lambda r: menu_of(r) in M7),
    ("x7a_m7", "x7", "x7_partA", lambda r: menu_of(r) in M7),
    ("x7a_l3", "x7", "x7_partA", lambda r: (r["law"], r["conv"]) in X7_LAWS),
    ("x5_frontier_m7", "x5", "frontier", lambda r: menu_of(r) in M7),
]


def raw_rows(path):
    """Rows as the CSV holds them (strings), so extracts keep every value byte for byte."""
    import csv
    import gzip
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8", newline="") as f:
        rd = csv.reader(f)
        head = next(rd)
        for row in rd:
            yield head, row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    d = os.path.join(out, "extracts")
    os.makedirs(d, exist_ok=True)
    lines = ["# Analysis extracts", "", "Subsets of the large tables of this tier output (code/extract.py); values are "
             "copied unchanged. Study menus: %s." % ", ".join("{%s}" % m.replace(" ", ", ") for m in
                                                               sorted(M7, key=lambda s: [int(x) for x in s.split()])),
             "", "| Extract | From | Rows |", "| --- | --- | --- |"]
    for name, step, base, keep in SPECS:
        src = find(os.path.join(out, step), base)
        if src is None:
            lines.append("| %s | %s/%s | not written (source missing) |" % (name, step, base))
            continue
        st = None
        n = 0
        for head, row in raw_rows(src):
            r = dict(zip(head, row))
            if not keep(r):
                continue
            if st is None:
                st = REG.CsvStream(os.path.join(d, name + ".csv.gz"), fields=head)
            st.write([r])
            n += 1
        if st is not None:
            st.close()
        lines.append("| %s | %s | %d |" % (name, os.path.relpath(src, out), n))
        print("extract %s: %d rows" % (name, n))
    REG.write_text(os.path.join(d, "README.md"), "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
