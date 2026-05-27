# Requirements Review Checklist
## Everything Discussed — Confirmed Before Implementation

---

## 1. Original Project Requirements

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| R1 | Input = dataset rows, each row has its own code content | ✅ Confirmed | StarCoder2 `content` column |
| R2 | Languages: Python, Java, JavaScript, C, C++ | ✅ Confirmed | Verified in parquet schema |
| R3 | Generic pipeline — not separate pipelines per language pair | ✅ Confirmed | Hub-and-spoke architecture |
| R4 | Parallel processing support | ✅ Confirmed | SLURM job arrays on cluster |
| R5 | Many-to-many language conversion | ✅ Confirmed | See mapping table below |
| R6 | Easy to add new languages | ✅ Confirmed | Registry + BaseGenerator pattern |

---

## 2. Language Pair Mapping (Final)

| Source | Targets | Direction |
|--------|---------|-----------|
| Python | Java, JavaScript, C, C++ | Python → 4 targets |
| Java | Python, JavaScript | Java → 2 targets |
| JavaScript | Java, Python | JavaScript → 2 targets |

> **Total unique language pairs: 8** ✅ FINAL
> Python→Java, Python→JS, Python→C, Python→C++,
> Java→Python, Java→JS,
> JS→Java, JS→Python

> **C and C++ are TARGET-ONLY languages** — no C→X or C++→X transpilation needed.

### Implication on Components Needed

| Component | Languages | Count |
|-----------|-----------|-------|
| **Parsers + Lifters** (source langs only) | Python, Java, JavaScript | **3** |
| **Generators** (target langs) | Python, Java, JavaScript, C, C++ | **5** |

This removes `c_lifter.py` and `cpp_lifter.py` entirely — C and C++ are never sources.

---

## 3. Dataset Requirements

| # | Requirement | Status | Detail |
|---|-------------|--------|--------|
| D1 | Dataset: StarCoder2 | ✅ Confirmed | Instructor specified |
| D2 | Path on cluster | ✅ Confirmed | `/projects/data/datasets/code_data/codeLLM_data/codeLLM_datasets_starcoder2/main_pretraining_corpus/bigcode_starcoder2_train_full_corpus_EXPLODED_w_CHARS_METADATA/` |
| D3 | Format: Parquet, 262 files | ✅ Confirmed | Verified on cluster |
| D4 | Language strings (Title Case) | ✅ Confirmed | `"Python"`, `"Java"`, `"JavaScript"`, `"C"`, `"C++"` |
| D5 | Input column for code | ✅ Confirmed | `content` column |
| D6 | Input column for language | ✅ Confirmed | `language` column |
| D7 | Quality filters applied | ✅ Confirmed | num_lines 5–300, alphanum≥0.25, avg_line≤150, is_generated=False |
| D8 | Initial filter sample (100K per lang) | ✅ Done | Job 123782 completed in 28s |
| D9 | Output of filter | ✅ Done | `/projects/.../iitgn_pt_transpiler/input/starcoder2_filtered_sample.parquet` (500K rows) |
| D10 | Scale-up strategy | ✅ Agreed | Dev=100K/lang → Validation=1M/lang → Full=all rows |

---

## 4. Architecture Decisions

### 4.1 What We Keep (4 repos only)

| Pattern | From Repo | What We Use It For |
|---------|----------|-------------------|
| Hub-and-spoke Canonical IR | SQLGlot | `ir/nodes.py` — language-neutral AST, eliminates N×M |
| GenBase → GenXxx hierarchy | Cito | `codegen/base_generator.py` → target generators |
| Backend plugin registry + Visitor | py2many | `pipeline/registry.py` — maps lang → (parser, lifter, generator) |
| Composable pass pipeline | Babel | `transforms/engine.py` — list of functions over IR |

### 4.2 What We Removed (9 repos — over-engineering)

| Pattern | Was From | Why Removed |
|---------|----------|-------------|
| SSA IR / three-tier IR | Dart SDK | Compiler-level. We do source-to-source only |
| Tree shaking | Dart SDK | Shrinks bundles. We transpile ALL code |
| Global type inference | Dart SDK | Whole-program analysis. Our snippets are self-contained |
| HXB binary IR format | Haxe | JSON is sufficient for our cache |
| CBOR cross-language bridge | c2rust | We stay in Python. No cross-language process needed |
| Fragment + source maps | Opal | Source maps needed for browser debugging. Not needed here |
| Handle dispatch table | Opal | Visitor pattern from py2many already covers this |
| NimVM / macros / nimcache | Nim | Compile-time features. Not applicable |
| TypeScript full symbol table | TypeScript | IDE-level. Our snippets don't have cross-file references |
| Brython IndexedDB cache | Brython | Browser-specific |
| Emscripten LLVM driver | Emscripten | WASM-specific toolchain. Not applicable |

---

## 5. Pipeline Stages (Final — 5 Stages)

| Stage | What It Does | Key Component |
|-------|-------------|---------------|
| **1. Preprocessing** | Normalize whitespace, encoding, strip BOM/shebangs | `preprocessing.py` |
| **2. Parsing** | Parse source code → CST using tree-sitter | `parsing/` — one parser per language |
| **3. Lifting** | CST → CanonicalNode IR | `lifting/` — one lifter per source language |
| **4. Transform Passes** | Apply language-agnostic + target-specific transforms | `transforms/` — composable functions |
| **5. Code Generation** | CanonicalNode → target source string | `codegen/` — BaseGenerator + subclasses |

> **Removed from previous 7-stage plan**: "IR Optimization" and "Target Normalization" are merged into Stage 4 (Transform Passes). "Post-Processing & Validation" is optional within Stage 5.

> **Stage 6 (Post-Processing / Formatters)**: ✅ SKIPPED FOR NOW — will decide after all 5 stages are working.

---

## 6. Cluster Setup

| # | Item | Status | Detail |
|---|------|--------|--------|
| C1 | Cluster | ✅ Confirmed | SoketLab — `slurm.dev.soket.ai` |
| C2 | OS | ✅ Confirmed | Ubuntu 22.04.5 LTS |
| C3 | SLURM partition | ✅ Confirmed | `rl` — 22 idle nodes available |
| C4 | Conda | ✅ Confirmed | `/home/iitgn_pt_data/miniconda3/` v26.1.1 |
| C5 | Conda env | ✅ Created | `transpiler_env` (Python 3.10) |
| C6 | Code directory | ✅ Created | `~/transpiler/` |
| C7 | Data directory | ✅ Created | `/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/` |
| C8 | Parallelism model | ✅ Confirmed | SLURM job arrays (NOT ProcessPoolExecutor) |
| C9 | pyarrow installed | ✅ Confirmed | Works with StarCoder2 parquet |

---

## 7. Folder Structure (Final)

```
~/transpiler/
│
├── code/
│   └── code_transpiler/        ← Pipeline Python source code
│       ├── pipeline/
│       │   ├── runner.py       # Orchestrates all 5 stages for one chunk
│       │   ├── registry.py     # Maps lang → (parser, lifter, generator)
│       │   └── cache.py        # SHA256-keyed result cache (filelock for SLURM)
│       │
│       ├── parsing/
│       │   ├── base_parser.py
│       │   ├── treesitter_parser.py    # Java, JS, C, C++
│       │   └── python_parser.py        # Uses ast module (richer than tree-sitter for Python)
│       │
│       ├── ir/
│       │   ├── nodes.py        # CanonicalNode dataclasses
│       │   └── visitor.py      # IRVisitor base class
│       │
│       ├── lifting/
│       │   ├── base_lifter.py
│       │   ├── python_lifter.py
│       │   ├── java_lifter.py
│       │   ├── javascript_lifter.py
│       │   ├── c_lifter.py
│       │   └── cpp_lifter.py
│       │
│       ├── transforms/
│       │   ├── engine.py       # run_passes(ir, pass_list) → ir
│       │   ├── common/         # Language-agnostic transforms
│       │   └── targets/        # Target-specific transforms
│       │       ├── to_java.py
│       │       ├── to_javascript.py
│       │       ├── to_python.py
│       │       ├── to_c.py
│       │       └── to_cpp.py
│       │
│       ├── codegen/
│       │   ├── base_generator.py
│       │   ├── java_generator.py
│       │   ├── javascript_generator.py
│       │   ├── python_generator.py
│       │   ├── c_generator.py
│       │   └── cpp_generator.py
│       │
│       ├── data/
│       │   ├── loader.py       # Read JSONL chunk
│       │   └── writer.py       # Write output JSONL chunk
│       │
│       ├── tests/
│       │   ├── unit/
│       │   ├── integration/
│       │   └── fixtures/       # Sample code in each language
│       │
│       ├── main.py             # Entry point: --input chunk --output result
│       └── requirements.txt
│
├── scripts/
│   ├── filter_starcoder2.py    ✅ DONE
│   └── prepare_chunks.py       ← Next step
│
└── slurm/
    ├── run_filter.sh           ✅ DONE (job 123782)
    └── transpile_job.sh        ← Next step

/projects/data/.../iitgn_pt_transpiler/
├── input/
│   ├── starcoder2_filtered_sample.parquet   ✅ DONE (500K rows)
│   └── chunks/                              ← After prepare_chunks.py
├── output/
│   └── chunks/                              ← After SLURM job array
├── cache/                                   ← SHA256 transpilation cache
└── logs/
```

---

## 8. Libraries (Final Minimal Set)

### Required (must install)
| Library | Purpose |
|---------|---------|
| `tree-sitter` | Parse Java, JS, C, C++ source code |
| `tree-sitter-java` | Java grammar |
| `tree-sitter-javascript` | JavaScript grammar |
| `tree-sitter-c` | C grammar |
| `tree-sitter-cpp` | C++ grammar |
| `pyarrow` | ✅ Already installed — read parquet |
| `pandas` | ✅ Already installed — data manipulation |
| `filelock` | Shared cache locking across SLURM tasks |
| `tqdm` | Progress bar within each task |
| `pytest` | Testing |

### Not needed (removed)
| Library | Why Removed |
|---------|-------------|
| `msgpack` | JSON is sufficient for cache |
| `hypothesis` | Adds complexity, not needed for V1 |
| `jsonschema` | Over-engineering |
| `pyarrow` for IR | Only needed for dataset I/O (already covered) |

> **tree-sitter grammar installation**: Will verify on cluster when setting up. May need `gcc`/`build-essential`.

---

## 9. Output Schema (Final)

The output JSONL per chunk will have all original StarCoder2 columns plus:

| Column | Type | Description |
|--------|------|-------------|
| `source_lang` | string | Same as `language` column |
| `target_lang` | string | The assigned target language |
| `transpiled_code` | string | Generated code (null if failed) |
| `transpile_success` | bool | True if all 5 stages completed |
| `transpile_error` | string | Error message + stage if failed |
| `transpile_time_ms` | int | Wall clock time in ms |

---

## 10. All Questions — RESOLVED ✅

| Q | Question | Answer |
|---|----------|--------|
| Q1 | Reverse mappings for C/C++? | ❌ Not needed. C and C++ are targets only. Final pairs = 8. |
| Q2 | Post-processing formatters? | ⏸ Skip for now. Add after all 5 stages work. |
| Q3 | Python ast or tree-sitter for Python? | ✅ Python `ast` module for Python source. tree-sitter for Java, JS, C, C++. |
| Q4 | Chunk size? | 🧪 Testing mode — use small chunks (50 rows) for now. Scale up later. |
| Q5 | Unit tests first or test on fixtures? | 🧪 Build incrementally — test on small fixture programs as we go. |

---

## 11. What's Done vs. What's Next

| Phase | Task | Status |
|-------|------|--------|
| Setup | SSH into cluster | ✅ Done |
| Setup | Verify StarCoder2 path + schema | ✅ Done |
| Setup | Create directory structure | ✅ Done |
| Setup | Create conda environment | ✅ Done |
| Data | Filter StarCoder2 (100K/lang, 500K total) | ✅ Done |
| Data | Run prepare_chunks.py | ⬜ Next |
| Core | Build `ir/nodes.py` (CanonicalNode) | ⬜ Pending |
| Core | Build `parsing/` (tree-sitter setup) | ⬜ Pending |
| Core | Build `lifting/python_lifter.py` | ⬜ Pending |
| Core | Build `codegen/base_generator.py` | ⬜ Pending |
| Core | Build `codegen/java_generator.py` | ⬜ Pending |
| Core | Build `codegen/javascript_generator.py` | ⬜ Pending |
| Core | Build `transforms/` | ⬜ Pending |
| Core | Build `pipeline/runner.py` + `main.py` | ⬜ Pending |
| Core | Build `lifting/java_lifter.py` | ⬜ Pending |
| Core | Build `lifting/javascript_lifter.py` | ⬜ Pending |
| Core | Build `codegen/c_generator.py` + `cpp_generator.py` | ⬜ Pending |
| Core | Build `lifting/c_lifter.py` + `cpp_lifter.py` | ⬜ Pending |
| SLURM | Write `transpile_job.sh` | ⬜ Pending |
| SLURM | Submit job array + monitor | ⬜ Pending |
| Output | Merge chunks → final dataset | ⬜ Pending |
