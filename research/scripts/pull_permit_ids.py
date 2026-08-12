"""Pull the full distinct pcis_permit set from a Socrata dataset, paginated.
Writes one raw permit string per line to the given output file.
"""
import sys
import time
import urllib.request
import urllib.parse
import json

DATASET_ID = sys.argv[1]
OUT_PATH = sys.argv[2]
PAGE_SIZE = 50000

def fetch_page(offset):
    params = {
        "$select": "distinct pcis_permit",
        "$limit": str(PAGE_SIZE),
        "$offset": str(offset),
    }
    url = f"https://data.lacity.org/resource/{DATASET_ID}.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "permit-stall-finder-profiling/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    offset = 0
    total = 0
    with open(OUT_PATH, "w") as f:
        while True:
            rows = fetch_page(offset)
            if not rows:
                break
            for r in rows:
                v = r.get("pcis_permit")
                if v:
                    f.write(v + "\n")
            total += len(rows)
            print(f"{DATASET_ID}: offset={offset} got={len(rows)} total={total}", file=sys.stderr)
            if len(rows) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
            time.sleep(0.2)
    print(f"DONE {DATASET_ID}: {total} rows -> {OUT_PATH}", file=sys.stderr)

if __name__ == "__main__":
    main()
