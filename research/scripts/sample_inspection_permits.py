"""Pull a stratified sample of distinct permit values from the inspections
dataset (9w5z-rg2h), stratified by inspection_date year, so the sample spans
both the 2015-2023 window (where the permit datasets have coverage) and the
2023-2026 window (where they apparently do not).
"""
import sys
import time
import urllib.request
import urllib.parse
import json

DATASET_ID = "9w5z-rg2h"
OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "inspection_permits_sample.txt"
PER_YEAR = 800

def fetch(year):
    where = f"inspection_date between '{year}-01-01T00:00:00' and '{year}-12-31T23:59:59'"
    params = {
        "$select": "distinct permit",
        "$where": where,
        "$limit": str(PER_YEAR),
    }
    url = f"https://data.lacity.org/resource/{DATASET_ID}.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "permit-stall-finder-profiling/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    years = list(range(2013, 2027))
    total = 0
    with open(OUT_PATH, "w") as f:
        for year in years:
            try:
                rows = fetch(year)
            except Exception as e:
                print(f"year={year} ERROR {e}", file=sys.stderr)
                continue
            for r in rows:
                v = r.get("permit")
                if v:
                    f.write(f"{year}\t{v}\n")
            total += len(rows)
            print(f"year={year} got={len(rows)} total={total}", file=sys.stderr)
            time.sleep(0.2)
    print(f"DONE: {total} rows -> {OUT_PATH}", file=sys.stderr)

if __name__ == "__main__":
    main()
