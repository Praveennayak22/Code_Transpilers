"""
filter_starcoder2.py
====================
Step 1 of the transpiler pipeline.

Reads StarCoder2 parquet files from the Yotta cluster,
filters to our 5 target languages with quality filters,
samples N rows per language, and saves a clean filtered dataset.

Run on the cluster (NOT locally):
    python3 scripts/filter_starcoder2.py

Expected output:
    /shared/transpiler/data/input/starcoder2_filtered/filtered_sample.parquet
"""

import pyarrow.dataset as ds
import pyarrow.compute as pc
import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd
from pathlib import Path
import json
import time

# ─────────────────────────────────────────────────────────────────────────────
# PATHS  (confirmed from cluster exploration)
# ─────────────────────────────────────────────────────────────────────────────
STARCODER2_PATH = (
    "/projects/data/datasets/code_data/codeLLM_data/"
    "codeLLM_datasets_starcoder2/main_pretraining_corpus/"
    "bigcode_starcoder2_train_full_corpus_EXPLODED_w_CHARS_METADATA/"
)

OUTPUT_DIR = Path("/shared/transpiler/data/input/starcoder2_filtered/")
OUTPUT_FILE = OUTPUT_DIR / "filtered_sample.parquet"

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

# Exact language strings as they appear in the parquet 'language' column
TARGET_LANGUAGES = ["Python", "Java", "JavaScript", "C", "C++"]

# How many rows to sample per language for the dev run
# Full dataset counts: JS=54M, Java=50M, Python=46M, C++=34M, C=15M
# For dev/testing use 100_000; for full run use None (no limit)
SAMPLE_PER_LANGUAGE = 100_000   # Set to None for full dataset

# Quality filters — removes junk, minified, and auto-generated code
QUALITY_FILTERS = {
    "min_lines":            5,      # Skip trivially short snippets
    "max_lines":            300,    # Skip huge files (slow + likely library code)
    "min_alphanum_fraction": 0.25,  # Skip binary/encoded content
    "max_avg_line_length":  150,    # Skip minified code (long lines)
    "exclude_generated":    True,   # Skip AI-generated files
}

# Columns to keep in the output (drop nothing we need, skip bulk we don't)
KEEP_COLUMNS = [
    "repo_name",
    "repo_url",
    "blob_id",           # For exact deduplication
    "path",
    "language",
    "is_generated",
    "content",           # The actual code — this is our model input
    "num_lines",
    "avg_line_length",
    "alphanum_fraction",
    "total_chars",
]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"StarCoder2 path : {STARCODER2_PATH}")
    print(f"Output path     : {OUTPUT_FILE}")
    print(f"Target languages: {TARGET_LANGUAGES}")
    print(f"Sample per lang : {SAMPLE_PER_LANGUAGE or 'ALL'}")
    print()

    # ── Build pyarrow predicate filter (pushdown into parquet reader) ──────
    # This means pyarrow filters INSIDE the file — never loads unwanted rows
    filter_expr = (
        pc.field("language").isin(TARGET_LANGUAGES)
        & (pc.field("num_lines") >= QUALITY_FILTERS["min_lines"])
        & (pc.field("num_lines") <= QUALITY_FILTERS["max_lines"])
        & (pc.field("alphanum_fraction") >= QUALITY_FILTERS["min_alphanum_fraction"])
        & (pc.field("avg_line_length") <= QUALITY_FILTERS["max_avg_line_length"])
    )
    if QUALITY_FILTERS["exclude_generated"]:
        filter_expr = filter_expr & (pc.field("is_generated") == False)

    # ── Open dataset (lazy — does NOT load data yet) ───────────────────────
    print("Opening dataset (lazy)...")
    dataset = ds.dataset(STARCODER2_PATH, format="parquet")
    print(f"Found {len(dataset.files)} parquet files\n")

    # ── Stream through batches, collect samples per language ──────────────
    from collections import defaultdict
    samples = defaultdict(list)          # lang → list of DataFrames
    counts  = defaultdict(int)           # lang → total rows collected
    done    = set()

    start = time.time()

    print("Streaming filtered batches...")
    for i, batch in enumerate(
        dataset.to_batches(
            filter=filter_expr,
            columns=KEEP_COLUMNS,
            batch_size=50_000,           # Process 50K rows at a time
        )
    ):
        if len(done) == len(TARGET_LANGUAGES):
            break  # All languages have enough samples

        df = batch.to_pandas()

        for lang in TARGET_LANGUAGES:
            if lang in done:
                continue

            lang_df = df[df["language"] == lang]
            if lang_df.empty:
                continue

            if SAMPLE_PER_LANGUAGE is not None:
                needed  = SAMPLE_PER_LANGUAGE - counts[lang]
                lang_df = lang_df.head(needed)

            samples[lang].append(lang_df)
            counts[lang] += len(lang_df)

            if SAMPLE_PER_LANGUAGE is not None and counts[lang] >= SAMPLE_PER_LANGUAGE:
                done.add(lang)
                elapsed = time.time() - start
                print(f"  ✓ {lang}: {counts[lang]:,} rows collected [{elapsed:.0f}s]")

        if i % 20 == 0:
            status = {l: counts[l] for l in TARGET_LANGUAGES}
            print(f"  Batch {i:4d} | Progress: {status}")

    # ── Concatenate and save ───────────────────────────────────────────────
    print("\nConcatenating results...")
    all_dfs = []
    for lang in TARGET_LANGUAGES:
        if samples[lang]:
            lang_combined = pd.concat(samples[lang], ignore_index=True)
            print(f"  {lang}: {len(lang_combined):,} rows")
            all_dfs.append(lang_combined)
        else:
            print(f"  {lang}: 0 rows — check language string or filters!")

    final_df = pd.concat(all_dfs, ignore_index=True)
    print(f"\nTotal rows: {len(final_df):,}")

    # Shuffle so language pairs are interleaved (better for chunking)
    final_df = final_df.sample(frac=1, random_state=42).reset_index(drop=True)

    final_df.to_parquet(OUTPUT_FILE, index=False, compression="snappy")
    print(f"\n✅ Saved filtered dataset to: {OUTPUT_FILE}")
    print(f"   File size: {OUTPUT_FILE.stat().st_size / 1e9:.2f} GB")

    # ── Print summary ──────────────────────────────────────────────────────
    print("\nLanguage distribution in output:")
    for lang, cnt in final_df["language"].value_counts().items():
        print(f"  {lang:15s}: {cnt:,}")

    print("\nContent length stats:")
    print(final_df["total_chars"].describe().to_string())


if __name__ == "__main__":
    main()
