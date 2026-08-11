import re
import random

def norm(s):
    return re.sub(r"[^A-Z0-9]", "", s.upper())

def load(path, has_year=False):
    out = []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            if has_year:
                year, val = line.split("\t", 1)
                out.append((year, val))
            else:
                out.append(line)
    return out

xnhu_raw = load("xnhu_permits.txt")
hbkd_raw = load("hbkd_permits.txt")
insp_raw = load("inspection_permits_sample.txt", has_year=True)

xnhu_norm = set(norm(x) for x in xnhu_raw)
hbkd_norm = set(norm(x) for x in hbkd_raw)

print(f"xnhu-aczu distinct raw={len(xnhu_raw)} distinct normalized={len(xnhu_norm)}")
print(f"hbkd-qubn distinct raw={len(hbkd_raw)} distinct normalized={len(hbkd_norm)}")

overlap_permit_sets = xnhu_norm & hbkd_norm
print(f"\nxnhu ∩ hbkd (normalized permit#) = {len(overlap_permit_sets)}")
print(f"  as % of xnhu: {100*len(overlap_permit_sets)/len(xnhu_norm):.1f}%")
print(f"  as % of hbkd: {100*len(overlap_permit_sets)/len(hbkd_norm):.1f}%")
xnhu_only = list(xnhu_norm - hbkd_norm)[:5]
hbkd_only = list(hbkd_norm - xnhu_norm)[:5]
print(f"  sample in xnhu but not hbkd: {xnhu_only}")
print(f"  sample in hbkd but not xnhu: {hbkd_only}")

# inspections side, by year
print("\n--- inspections sample vs xnhu-aczu / hbkd-qubn, by year ---")
by_year = {}
for year, val in insp_raw:
    by_year.setdefault(year, []).append(val)

print(f"{'year':6} {'n':6} {'match_xnhu':11} {'match_hbkd':11} {'match_either':13}")
totals = {"n":0, "xnhu":0, "hbkd":0, "either":0}
unmatched_examples = []
for year in sorted(by_year):
    vals = by_year[year]
    n = len(vals)
    m_xnhu = 0
    m_hbkd = 0
    m_either = 0
    for v in vals:
        nv = norm(v)
        in_x = nv in xnhu_norm
        in_h = nv in hbkd_norm
        if in_x:
            m_xnhu += 1
        if in_h:
            m_hbkd += 1
        if in_x or in_h:
            m_either += 1
        elif len(unmatched_examples) < 15:
            unmatched_examples.append((year, v))
    print(f"{year:6} {n:6} {m_xnhu:5} ({100*m_xnhu/n:5.1f}%) {m_hbkd:5} ({100*m_hbkd/n:5.1f}%) {m_either:5} ({100*m_either/n:5.1f}%)")
    totals["n"] += n
    totals["xnhu"] += m_xnhu
    totals["hbkd"] += m_hbkd
    totals["either"] += m_either

print(f"\nTOTAL n={totals['n']}")
print(f"  matched xnhu-aczu: {totals['xnhu']} ({100*totals['xnhu']/totals['n']:.1f}%)")
print(f"  matched hbkd-qubn: {totals['hbkd']} ({100*totals['hbkd']/totals['n']:.1f}%)")
print(f"  matched either:    {totals['either']} ({100*totals['either']/totals['n']:.1f}%)")

print("\nExamples of inspection permits matching NEITHER permit dataset:")
for year, v in unmatched_examples:
    print(f"  {year}\t{v!r}\t(normalized={norm(v)!r})")

# reverse direction restricted to xnhu-aczu's own coverage window (2015-11 to 2023-05)
# to avoid penalizing the match rate for permits issued after the dataset went stale
print("\n--- restricting inspections sample to years 2016-2022 (xnhu-aczu's stable coverage window) ---")
core_years = [y for y in by_year if y not in ("2013","2014","2015","2023","2024","2025","2026")]
n2 = sum(len(by_year[y]) for y in core_years)
m2 = 0
for y in core_years:
    for v in by_year[y]:
        if norm(v) in xnhu_norm or norm(v) in hbkd_norm:
            m2 += 1
print(f"n={n2} matched(either)={m2} ({100*m2/n2:.1f}%)")
