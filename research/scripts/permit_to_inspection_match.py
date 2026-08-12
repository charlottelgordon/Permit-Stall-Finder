"""For a stratified sample of permits drawn from xnhu-aczu, query the
inspections dataset directly (batched IN clauses, both dash and space
separator variants) to measure what fraction have >=1 inspection record.
This is the reverse direction of the earlier inspections->permits check.
"""
import random
import re
import sys
import time
import urllib.request
import urllib.parse
import json

random.seed(42)

def load_permits(path):
    return [l.strip() for l in open(path) if l.strip()]

def to_space(p):
    return p.replace("-", " ")

def to_dash(p):
    return p.replace(" ", "-")

def query_batch(variants):
    # variants: list of permit strings (either format) to check existence for
    quoted = ",".join("'" + v.replace("'", "''") + "'" for v in variants)
    where = f"permit in({quoted})"
    params = {"$select": "distinct permit", "$where": where, "$limit": "5000"}
    url = "https://data.lacity.org/resource/9w5z-rg2h.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "permit-stall-finder-profiling/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    return set(r["permit"] for r in rows)

def main():
    permits = load_permits("xnhu_permits.txt")
    sample = random.sample(permits, 1500)

    batch_size = 40
    found_norm = set()
    matched_permits = set()
    for i in range(0, len(sample), batch_size):
        chunk = sample[i:i+batch_size]
        variants = []
        for p in chunk:
            variants.append(to_space(p))
            variants.append(to_dash(p))
        try:
            hits = query_batch(variants)
        except Exception as e:
            print(f"batch {i} error: {e}", file=sys.stderr)
            continue
        hit_norm = set(re.sub(r"[^A-Z0-9]", "", h.upper()) for h in hits)
        for p in chunk:
            pn = re.sub(r"[^A-Z0-9]", "", p.upper())
            if pn in hit_norm:
                matched_permits.add(p)
        print(f"batch {i//batch_size}: cumulative matched={len(matched_permits)} / {min(i+batch_size, len(sample))}", file=sys.stderr)
        time.sleep(0.15)

    n = len(sample)
    m = len(matched_permits)
    print(f"\nRESULT: {m} / {n} sampled xnhu-aczu permits ({100*m/n:.1f}%) have >=1 matching inspection record")

if __name__ == "__main__":
    main()
