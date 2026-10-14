"""Read-only audit of source keys and exact duplicates."""
import csv
from collections import Counter
from pathlib import Path
from pipeline.datasets import DATASETS
from pipeline.ingest import canonical, source_path

for name, (columns, keys) in DATASETS.items():
    keys = keys.split() or columns.split()
    versions = {}
    duplicates = 0
    conflicts = 0
    count = 0
    with source_path(Path('data'), name).open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            key = tuple(row[k] for k in keys)
            value = canonical(row)
            if key in versions:
                if versions[key] == value:
                    duplicates += 1
                else:
                    conflicts += 1
            versions[key] = value
            count += 1
    print(f'{name}: rows={count}, keys={len(versions)}, exact_duplicates={duplicates}, conflicting_keys={conflicts}', flush=True)
