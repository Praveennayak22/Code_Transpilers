"""
scripts/prepare_chunks.py
==========================
Step 2 of the pipeline — run ONCE on the cluster after filtering.

Reads the filtered parquet, assigns target languages per row
based on the 8 language pairs, then splits into small JSONL
chunks for the SLURM job array.

Usage (on cluster):
    python3 ~/transpiler/scripts/prepare_chunks.py

Output:
    /projects/.../iitgn_pt_transpiler/input/chunks/chunk_0000.jsonl
    /projects/.../iitgn_pt_transpiler/input/chunks/chunk_0001.jsonl
    ...
    Prints: sbatch --array=0-N slurm/transpile_job.sh
"""

import pandas as pd
from pathlib import Path
import json, time

# ── Paths ──────────────────────────────────────────────────────────────────────
INPUT_FILE = Path(
    "/projects/data/datasets/code_data/codeLLM_data/"
    "iitgn_pt_transpiler/input/starcoder2_filtered_sample.parquet"
)
OUTPUT_DIR = Path(
    "/projects/data/datasets/code_data/codeLLM_data/"
    "iitgn_pt_transpiler/input/chunks/"
)

# ── Language pairs (8 total, confirmed) ───────────────────────────────────────
LANGUAGE_PAIRS = {
    "Python":     ["Java", "JavaScript", "C", "C++"],
    "Java":       ["Python", "JavaScript"],
    "JavaScript": ["Java", "Python"],
}

# ── Chunk size ─────────────────────────────────────────────────────────────────
# Testing mode: 50 rows per chunk
# Production:   500 rows per chunk
CHUNK_SIZE = 50


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Reading: {INPUT_FILE}")
    df = pd.read_parquet(INPUT_FILE)
    print(f"Loaded  : {len(df):,} rows")
    print(f"Languages: {df['language'].value_counts().to_dict()}")

    # ── Expand: one source row -> one row per valid target language ────────────
    print("\nExpanding language pairs...")
    rows = []
    for _, row in df.iterrows():
        src = row["language"]
        targets = LANGUAGE_PAIRS.get(src, [])
        for tgt in targets:
            r = row.to_dict()
            r["source_lang"] = src
            r["target_lang"] = tgt
            rows.append(r)

    expanded = pd.DataFrame(rows)
    print(f"Total transpilation jobs: {len(expanded):,}")
    print("\nJobs per language pair:")
    for (src, tgt), cnt in expanded.groupby(["source_lang", "target_lang"]).size().items():
        print(f"  {src:12s} -> {tgt:12s}: {cnt:,}")

    # ── Split into chunks and write as JSONL ───────────────────────────────────
    print(f"\nWriting chunks of {CHUNK_SIZE} rows to {OUTPUT_DIR} ...")
    start = time.time()

    total_chunks = (len(expanded) + CHUNK_SIZE - 1) // CHUNK_SIZE
    for i in range(total_chunks):
        chunk = expanded.iloc[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]
        chunk_path = OUTPUT_DIR / f"chunk_{i:04d}.jsonl"
        with open(chunk_path, "w", encoding="utf-8") as f:
            for _, row in chunk.iterrows():
                record = {}
                for k, v in row.items():
                    if isinstance(v, float) and pd.isna(v):
                        record[k] = None
                    else:
                        record[k] = v
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        if i % 200 == 0 or i == total_chunks - 1:
            print(f"  Wrote chunk {i:04d}/{total_chunks - 1}  [{time.time()-start:.0f}s]")

    print(f"\nDone! Created {total_chunks} chunks in {OUTPUT_DIR}")
    print(f"\nTo submit the SLURM job array, run:")
    print(f"  sbatch --array=0-{total_chunks - 1} "
          f"~/transpiler/code/code_transpiler/slurm/transpile_job.sh")


if __name__ == "__main__":
    main()
