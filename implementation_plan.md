# Transpiler Pipeline — StarCoder2 on Yotta Cluster
## Final Architecture Plan (v4)

---

## What Changed With This Instruction

| Before | Now |
|--------|-----|
| Generic CSV/JSONL dataset | **StarCoder2** — 531M rows, 439 GB parquet |
| Unknown cluster | **Yotta cluster** via SoketLab SLURM |
| Source + target lang both specified per row | **Only source lang** is known (the `language` column); target lang is assigned by us |
| Assumed small dataset | Massive scale — must filter first |

---

## Dataset: StarCoder2

| Property | Value |
|----------|-------|
| Name | starcoder2 |
| Synthetic | No (real GitHub code) |
| Total samples | **531 million** |
| Compressed size | **439 GB** (parquet) |
| Format | **Parquet** (partitioned, sharded) |
| Yotta path | `/codeLLM_datasets_starcoder2/main_pretraining_corpus/bigcode_starcoder2_train_full_corpus_EXPLODED/` |
| Base path prefix | `/projects/data/datasets/code_data/codeLLM_data/` |

### Dataset Schema (Columns We Care About)

| Column | Type | Purpose | Keep? |
|--------|------|---------|-------|
| `language` | string | Programming language of the file | ✅ **Use to filter** |
| `content` | string | Actual code content | ✅ **This is our input code** |
| `repo_name` | string | Repository name | ✅ Keep (for traceability) |
| `repo_url` | string | Repository URL | ✅ Keep |
| `blob_id` | string | File blob ID | ✅ Keep (exact deduplication) |
| `path` | string | File path in repo | ✅ Keep |
| `is_generated` | bool | AI-generated? | ✅ Keep (may want to filter out) |
| `num_lines` | int | Lines of code | ✅ Use for quality filtering |
| `avg_line_length` | float | Avg line length | ✅ Use for quality filtering |
| `max_line_length` | float | Max line length | ✅ Use for quality filtering |
| `alphanum_fraction` | float | Fraction of alphanumeric chars | ✅ Use for quality filtering |
| `alpha_fraction` | float | Fraction of alphabets | ✅ Use for quality filtering |
| `total_chars` | int | Total character count | ✅ Use for quality filtering |
| `github_id` | string | GitHub repo ID | ⚪ Optional |

---

## Step 0 — Critical First Step: Filter the Dataset

531 million rows is the **full StarCoder2 corpus** covering hundreds of programming languages. We only need **5 languages**: Python, Java, JavaScript, C, C++.

### Language Values in StarCoder2
The `language` column in StarCoder2 uses these values (from BigCode):
```
"Python", "Java", "JavaScript", "C", "C++"
```

### Estimated Row Count After Language Filter
StarCoder2 is skewed toward popular languages. Approximate breakdown:

| Language | Est. % of dataset | Est. rows | Est. size |
|----------|------------------|-----------|-----------|
| Python | ~12% | ~63M | ~53 GB |
| Java | ~10% | ~53M | ~44 GB |
| JavaScript | ~11% | ~58M | ~49 GB |
| C | ~6% | ~32M | ~27 GB |
| C++ | ~7% | ~37M | ~31 GB |
| **Total (our 5 langs)** | **~46%** | **~243M** | **~204 GB** |

> **This is still enormous.** For initial development and testing, we will work with a **sampled subset** (e.g., 100K rows per language = 500K total).

### Quality Filters to Apply
On top of language filtering, apply these **data quality filters** before transpilation:

```python
filters = [
    ("language", "in", ["Python", "Java", "JavaScript", "C", "C++"]),
    ("is_generated", "==", False),          # Skip AI-generated code
    ("num_lines", ">=", 5),                 # Skip trivially short files
    ("num_lines", "<=", 300),               # Skip huge files (slow to transpile)
    ("alphanum_fraction", ">=", 0.25),      # Skip binary/encoded content
    ("avg_line_length", "<=", 150),         # Skip minified/ugly code
]
```

---

## How We Construct Transpilation Pairs

StarCoder2 only tells us the **source language** of each file. We need to decide the **target language**. Two strategies:

### Strategy A — One-to-All (Recommended for dataset creation)
For each source code file, generate outputs for **all valid target languages**:

```
StarCoder2 Python file → generate Java version + JavaScript version + C version + C++ version
StarCoder2 Java file   → generate Python version + JavaScript version
StarCoder2 JS file     → generate Python version + Java version
```

This maximizes the dataset coverage. One input row → multiple output rows.

### Strategy B — One-to-One (Simpler for initial runs)
Assign each source file a single target language based on the mapping:

| Source | Assigned Target |
|--------|----------------|
| Python | Java |
| Java | Python |
| JavaScript | Python |
| C | Python |
| C++ | Python |

### Recommendation
Start with **Strategy B** for the initial run (simpler). Switch to Strategy A for the full dataset generation.

---

## Updated Pipeline Flow for StarCoder2

```
Yotta Cluster: /codeLLM_datasets_starcoder2/.../*.parquet
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: FILTER & SAMPLE (run once, save filtered dataset)  │
│                                                             │
│  • Read parquet files with predicate pushdown               │
│    (filter by language column at read time = very fast)     │
│  • Apply quality filters (num_lines, alphanum_fraction etc) │
│  • Sample N rows per language (e.g., 100K each)             │
│  • Save filtered dataset to /shared/transpiler/data/        │
│    as smaller parquet files                                  │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: ASSIGN TARGET LANGUAGES                            │
│                                                             │
│  • Add target_lang column based on Strategy A or B          │
│  • Explode multi-target rows (Strategy A)                   │
│  • Save as chunked JSONL files for SLURM                    │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: SLURM JOB ARRAY (one task per chunk)               │
│                                                             │
│  For each row in chunk:                                     │
│    content (str) + source_lang + target_lang                │
│         │                                                   │
│    [5-stage Transpiler Pipeline]                            │
│         │                                                   │
│    output_code (str) + metadata                             │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: MERGE & FINALIZE                                   │
│                                                             │
│  • Merge all output chunks                                  │
│  • Final dataset: original columns + transpiled_code        │
│    + target_lang + transpile_error + transpile_metadata     │
└─────────────────────────────────────────────────────────────┘
```

---

## Step 1 Implementation — Parquet Filtering Script

```python
# scripts/filter_starcoder2.py
# Run this ONCE on the cluster to produce the filtered dataset

import pyarrow.dataset as ds
import pyarrow.compute as pc
import pyarrow as pa
from pathlib import Path

STARCODER2_PATH = "/codeLLM_datasets_starcoder2/main_pretraining_corpus/bigcode_starcoder2_train_full_corpus_EXPLODED/"
OUTPUT_PATH = "/shared/transpiler/data/input/starcoder2_filtered/"
SAMPLE_PER_LANGUAGE = 100_000       # Adjust for full run

TARGET_LANGUAGES = ["Python", "Java", "JavaScript", "C", "C++"]

dataset = ds.dataset(STARCODER2_PATH, format="parquet")

# Predicate pushdown — filters happen at parquet file level (very fast)
filter_expr = (
    pc.field("language").isin(TARGET_LANGUAGES) &
    (pc.field("is_generated") == False) &
    (pc.field("num_lines") >= 5) &
    (pc.field("num_lines") <= 300) &
    (pc.field("alphanum_fraction") >= 0.25) &
    (pc.field("avg_line_length") <= 150)
)

# Columns we need (skip the rest to reduce memory)
columns = [
    "repo_name", "repo_url", "blob_id", "path",
    "language", "content", "is_generated",
    "num_lines", "avg_line_length", "alphanum_fraction", "total_chars"
]

# Read filtered data in batches, sample per language
from collections import defaultdict
import random

samples = defaultdict(list)
DONE = set()

for batch in dataset.to_batches(filter=filter_expr, columns=columns, batch_size=100_000):
    df = batch.to_pandas()
    for lang, group in df.groupby("language"):
        if lang in DONE:
            continue
        needed = SAMPLE_PER_LANGUAGE - len(samples[lang])
        if needed <= 0:
            DONE.add(lang)
            continue
        samples[lang].append(group.head(needed))
        if len(samples[lang]) * 100_000 >= SAMPLE_PER_LANGUAGE:
            DONE.add(lang)
    if len(DONE) == len(TARGET_LANGUAGES):
        break

import pandas as pd
final_df = pd.concat([pd.concat(v) for v in samples.values()], ignore_index=True)
print(f"Filtered dataset: {len(final_df)} rows")
final_df.to_parquet(OUTPUT_PATH + "filtered_sample.parquet", index=False)
print("Saved to", OUTPUT_PATH)
```

---

## Step 2 Implementation — Assign Target Languages + Chunk

```python
# scripts/prepare_chunks.py

import pandas as pd
from pathlib import Path

LANGUAGE_PAIRS = {
    "Python":     ["Java", "JavaScript", "C", "C++"],  # Strategy A
    "Java":       ["Python", "JavaScript"],
    "JavaScript": ["Python", "Java"],
    "C":          ["Python"],
    "C++":        ["Python"],
}

df = pd.read_parquet("/shared/transpiler/data/input/starcoder2_filtered/filtered_sample.parquet")

# Explode: one row → multiple rows (one per target language)
rows = []
for _, row in df.iterrows():
    src_lang = row["language"]
    for tgt_lang in LANGUAGE_PAIRS.get(src_lang, []):
        new_row = row.to_dict()
        new_row["source_lang"] = src_lang
        new_row["target_lang"] = tgt_lang
        rows.append(new_row)

expanded_df = pd.DataFrame(rows)
print(f"Total transpilation jobs: {len(expanded_df)}")

# Split into chunks
CHUNK_SIZE = 500
output_dir = Path("/shared/transpiler/data/input/chunks/")
output_dir.mkdir(parents=True, exist_ok=True)

for i, chunk in enumerate(range(0, len(expanded_df), CHUNK_SIZE)):
    chunk_df = expanded_df.iloc[chunk:chunk+CHUNK_SIZE]
    chunk_df.to_json(output_dir / f"chunk_{i:04d}.jsonl", orient="records", lines=True)

total_chunks = (len(expanded_df) + CHUNK_SIZE - 1) // CHUNK_SIZE
print(f"Created {total_chunks} chunks in {output_dir}")
print(f"Submit: sbatch --array=0-{total_chunks-1} slurm/transpile_job.sh")
```

---

## Output Dataset Schema

The final output dataset will have all original StarCoder2 columns plus:

| New Column | Type | Description |
|-----------|------|-------------|
| `source_lang` | string | Source language (same as `language`) |
| `target_lang` | string | Transpilation target language |
| `transpiled_code` | string | Output of transpiler (null if failed) |
| `transpile_success` | bool | Did transpilation succeed? |
| `transpile_error` | string | Error message if failed (null if success) |
| `transpile_stage` | string | Stage where failure occurred |
| `transpile_time_ms` | int | Time taken in milliseconds |
| `cache_hit` | bool | Was result served from cache? |

---

## Shared Filesystem Layout (Updated)

```
/shared/transpiler/
│
├── code/
│   └── code_transpiler/          ← Pipeline source code
│
├── data/
│   ├── input/
│   │   ├── starcoder2_filtered/
│   │   │   └── filtered_sample.parquet   ← After Step 1
│   │   └── chunks/
│   │       ├── chunk_0000.jsonl           ← After Step 2
│   │       ├── chunk_0001.jsonl
│   │       └── ...
│   │
│   └── output/
│       ├── chunks/
│       │   ├── out_0000.jsonl
│       │   └── ...
│       └── final_dataset.parquet         ← After Step 4 merge
│
├── cache/                         ← SHA256-keyed transpilation cache
├── logs/
│   ├── slurm/                     ← SLURM .out / .err files
│   └── pipeline/                  ← Per-task structured logs
│
└── envs/
    └── transpiler_env/            ← Conda environment
```

> **Note**: The raw StarCoder2 data stays at its original Yotta path. We only write our **filtered sample** to `/shared/transpiler/`.

---

## Updated Requirements

```
# Core pipeline
tree-sitter>=0.20
tree-sitter-python
tree-sitter-java
tree-sitter-javascript
tree-sitter-c
tree-sitter-cpp
pyyaml>=6.0

# StarCoder2 / Parquet reading
pyarrow>=14.0         ← REQUIRED for parquet + predicate pushdown
pandas>=2.0

# SLURM cluster
filelock>=3.12        ← Shared cache file locking

# Progress + UX
tqdm>=4.0

# Testing
pytest>=7.0
```

---

## Updated Implementation Roadmap

### Phase 0 — Cluster Setup + Data Exploration (Week 1)
- [ ] SSH into cluster, verify access to StarCoder2 path
- [ ] Check parquet file structure: `pyarrow.dataset.dataset(STARCODER2_PATH).schema`
- [ ] Check `language` column unique values to confirm StarCoder2 language names
- [ ] Check total row counts per language
- [ ] Set up conda environment at `/shared/transpiler/envs/`
- [ ] Clone pipeline code to `/shared/transpiler/code/`
- [ ] Install tree-sitter + grammars

### Phase 1 — Data Pipeline: Filter + Sample + Chunk (Week 1–2)
- [ ] Run `scripts/filter_starcoder2.py` — produce filtered sample parquet
- [ ] Run `scripts/prepare_chunks.py` — assign target langs + split into JSONL chunks
- [ ] Verify chunk content: spot-check 5 chunks across different language pairs
- [ ] Verify quality: check `num_lines`, `alphanum_fraction` distributions in sample

### Phase 2 — Transpiler Core (Weeks 2–5)
*(same as v3 — Python lifter, Java/JS generators, Java/JS lifters, C/C++ generators)*

### Phase 3 — SLURM End-to-End Test (Week 6)
- [ ] Run 1 SLURM task on 1 chunk (500 rows) manually
- [ ] Check output JSONL for correctness
- [ ] Submit 10-task array; verify parallel execution
- [ ] Check shared cache for race conditions
- [ ] Submit full job array

### Phase 4 — Merge + Final Dataset (Week 7)
- [ ] Run `slurm/merger.py` to combine output chunks
- [ ] Save as `final_dataset.parquet`
- [ ] Compute accuracy metrics per language pair
- [ ] Identify top failure categories

---

## Scale Planning

For the initial development run:

| Language pair | Sample size | Chunks (500/chunk) | SLURM tasks |
|--------------|-------------|---------------------|-------------|
| Python → Java | 100K | 200 | 200 |
| Python → JS | 100K | 200 | 200 |
| Python → C | 100K | 200 | 200 |
| Python → C++ | 100K | 200 | 200 |
| Java → Python | 100K | 200 | 200 |
| Java → JS | 100K | 200 | 200 |
| JS → Python | 100K | 200 | 200 |
| JS → Java | 100K | 200 | 200 |
| **Total** | **800K jobs** | **1600** | **1600** |

> For **full scale** (all filtered rows, ~243M): ~486K SLURM tasks. Submit as multiple job arrays of 1000 tasks each.

---

## First Command to Run on the Cluster

```bash
# SSH in
ssh iitgn_pt_data@slurm.dev.soket.ai

# Check StarCoder2 is accessible
ls /codeLLM_datasets_starcoder2/main_pretraining_corpus/bigcode_starcoder2_train_full_corpus_EXPLODED/ | head -5

# Check how many parquet files
ls /codeLLM_datasets_starcoder2/main_pretraining_corpus/bigcode_starcoder2_train_full_corpus_EXPLODED/*.parquet | wc -l

# Quick schema check (run in Python)
python3 -c "
import pyarrow.dataset as ds
d = ds.dataset('/codeLLM_datasets_starcoder2/main_pretraining_corpus/bigcode_starcoder2_train_full_corpus_EXPLODED/')
print('Schema:', d.schema)
print('Files:', d.count_rows())
"
```
