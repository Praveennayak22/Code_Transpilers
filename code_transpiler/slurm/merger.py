"""
slurm/merger.py
================
Merges all output chunks into a single final parquet dataset.

Run AFTER all SLURM tasks complete:
    python3 ~/transpiler/code/code_transpiler/slurm/merger.py

Output:
    /projects/.../iitgn_pt_transpiler/output/final_dataset.parquet
"""

import pandas as pd
from pathlib import Path
import json, time

OUTPUT_DIR   = Path("/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/output")
CHUNKS_DIR   = OUTPUT_DIR / "chunks"
FINAL_OUTPUT = OUTPUT_DIR / "final_dataset.parquet"


def main():
    chunk_files = sorted(CHUNKS_DIR.glob("out_*.jsonl"))
    print(f"Found {len(chunk_files)} output chunks")

    if not chunk_files:
        print("No output chunks found. Have the SLURM jobs finished?")
        return

    all_rows = []
    errors = 0
    start = time.time()

    for i, f in enumerate(chunk_files):
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    all_rows.append(json.loads(line))
                except json.JSONDecodeError:
                    errors += 1
        if i % 100 == 0 or i == len(chunk_files) - 1:
            print(f"  Read {i+1}/{len(chunk_files)} chunks  [{time.time()-start:.0f}s]")

    print(f"\nTotal rows: {len(all_rows):,}  ({errors} JSON errors)")

    df = pd.DataFrame(all_rows)
    print(f"\nSchema:\n{df.dtypes}")
    print(f"\nSuccess rate: {df['transpile_success'].mean()*100:.1f}%")
    print(f"\nPer language pair success rate:")
    for (src, tgt), grp in df.groupby(["source_lang", "target_lang"]):
        rate = grp["transpile_success"].mean() * 100
        print(f"  {src:12s} -> {tgt:12s}: {rate:.1f}%  ({len(grp):,} rows)")

    df.to_parquet(FINAL_OUTPUT, index=False, compression="snappy")
    size_gb = FINAL_OUTPUT.stat().st_size / 1e9
    print(f"\nSaved: {FINAL_OUTPUT}  ({size_gb:.2f} GB)")


if __name__ == "__main__":
    main()
