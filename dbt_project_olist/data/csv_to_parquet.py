from pathlib import Path
import pandas as pd

csv_dir = Path("raw")
parquet_dir = Path("parquet")

for csv_file in csv_dir.glob("*.csv"):
    df = pd.read_csv(csv_file)
    df.to_parquet(
        parquet_dir / f"{csv_file.stem}.parquet",
        index=False
    )

    print(f"create parquet file {csv_file.name}")
