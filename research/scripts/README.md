# Profiling scripts

Stdlib-only (no `requests`, no Socrata app token needed for these sample
sizes). Used to produce `../DATASET_VALIDATION.md`. Re-run from this
directory; each writes its own output file, which is gitignored (large,
regenerable — not committed).

```bash
# full distinct permit-number pull for a given Socrata dataset id
python3 pull_permit_ids.py xnhu-aczu xnhu_permits.txt
python3 pull_permit_ids.py hbkd-qubn hbkd_permits.txt

# stratified sample of inspection permit numbers, 2013-2026
python3 sample_inspection_permits.py inspection_permits_sample.txt

# set-overlap analysis between the two permit pulls + the inspection sample
python3 analyze_overlap.py

# reverse-direction join check: sample permits -> do they have inspections?
python3 permit_to_inspection_match.py
```
