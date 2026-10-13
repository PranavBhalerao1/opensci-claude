
import os, pathlib

# Quick peek at the raw file before pandas
csv_path = pathlib.Path("data/metrics_seed123_noaug.csv")
if csv_path.exists():
    lines = csv_path.read_text().splitlines()
    print(f"Total lines in file : {len(lines)}")
    print("--- first 4 lines ---")
    for l in lines[:4]:
        print(repr(l))
    print("--- last 2 lines ---")
    for l in lines[-2:]:
        print(repr(l))
else:
    print("FILE NOT FOUND")
