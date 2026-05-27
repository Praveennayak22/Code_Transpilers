# Code Transpiler Pipeline — Architecture Explanation

---

## 1. What Are We Building?

A **many-to-many source code transpiler pipeline** that:

- Takes a large dataset (StarCoder2 — 531 million real GitHub code files)
- Filters to 5 programming languages: **Python, Java, JavaScript, C, C++**
- Automatically **translates code from one language to another**
- Runs at scale on a **SLURM HPC cluster** (SoketLab)

**Example**: Take a Python function → automatically generate its equivalent Java version.

---

## 2. The Core Problem: N×M Complexity

Suppose we have **3 source languages** and **5 target languages**.

A naïve approach would be to build a **separate translator for every pair**:

```
Python  → Java          (1 translator)
Python  → JavaScript    (2 translators)
Python  → C             (3 translators)
Python  → C++           (4 translators)
Java    → Python        (5 translators)
Java    → JavaScript    (6 translators)
JavaScript → Java       (7 translators)
JavaScript → Python     (8 translators)
```

That's **8 separate systems**, each built from scratch.
If we add one new language later, we have to build translators for every existing language again.

**This is the N × M problem** — with N sources and M targets, you need N×M systems.

---

## 3. Our Solution: Hub-and-Spoke with Canonical IR

We solve this with a **single shared intermediate representation** called the **Canonical IR** (Intermediate Representation).

```
                    ┌─────────────────────┐
                    │                     │
   Python ──────────►                     ├──────────► Java
                    │                     │
   Java   ──────────►   CANONICAL  IR     ├──────────► JavaScript
                    │  (Language-neutral  │
   JavaScript ──────►    AST tree)        ├──────────► Python
                    │                     │
                    │                     ├──────────► C
                    │                     │
                    └─────────────────────┴──────────► C++

        N Parsers + Lifters          M Code Generators
```

**Instead of N×M translators, we only need:**
- **N components** to convert source code → Canonical IR (called "Lifters")
- **M components** to convert Canonical IR → target code (called "Generators")
- **Total: N + M = 3 + 5 = 8 components** (not 8 separate full systems)

This is the same pattern used by production tools like **SQLGlot** (SQL ↔ 20+ dialects) and **LLVM** (many languages → many hardware targets).

---

## 4. What Is the Canonical IR?

The Canonical IR is a **language-neutral tree structure** that represents code concepts that exist in all programming languages.

```python
# Example: A simple Python function
def add(a, b):
    return a + b
```

Gets converted to this language-neutral tree:

```
FunctionDef(
    name = "add",
    params = [Param("a"), Param("b")],
    body = [
        ReturnStmt(
            value = BinaryOp(
                op   = "+",
                left = Name("a"),
                right = Name("b")
            )
        )
    ]
)
```

This tree has **no Python syntax** — no `def`, no `:`, no indentation.
It just says: "there is a function named `add` that takes `a` and `b` and returns their sum."

From this one tree, any generator can produce:
- **Java**: `public static int add(int a, int b) { return a + b; }`
- **JavaScript**: `function add(a, b) { return a + b; }`
- **C**: `int add(int a, int b) { return a + b; }`

---

## 5. The 5-Stage Pipeline (Per Code Snippet)

Every code snippet in the dataset goes through exactly these 5 stages:

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   INPUT: source_code (string) + source_lang + target_lang           │
│                                                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │  STAGE 1 — PREPROCESSING                                    │   │
│   │                                                             │   │
│   │  • Remove BOM markers, normalize whitespace                 │   │
│   │  • Strip shell shebangs (#!/usr/bin/env python)             │   │
│   │  • Basic sanity check (is this valid text?)                 │   │
│   └──────────────────────────┬──────────────────────────────────┘   │
│                              │                                       │
│   ┌──────────────────────────▼──────────────────────────────────┐   │
│   │  STAGE 2 — PARSING                                          │   │
│   │                                                             │   │
│   │  • Convert source code string → syntax tree (CST)           │   │
│   │  • Python: uses Python's built-in `ast` module              │   │
│   │  • Java, JavaScript: uses `tree-sitter` library             │   │
│   │  • Output: a structured tree of the source code             │   │
│   └──────────────────────────┬──────────────────────────────────┘   │
│                              │                                       │
│   ┌──────────────────────────▼──────────────────────────────────┐   │
│   │  STAGE 3 — LIFTING (Source → Canonical IR)                  │   │
│   │                                                             │   │
│   │  • Walk the source syntax tree node by node                 │   │
│   │  • Convert each language-specific node into a               │   │
│   │    language-neutral CanonicalNode                           │   │
│   │  • Python `def` → CanonicalNode FunctionDef                 │   │
│   │  • Java `for(int i=0; i<n; i++)` → CanonicalNode ForLoop    │   │
│   │  • Output: the Canonical IR tree                            │   │
│   └──────────────────────────┬──────────────────────────────────┘   │
│                              │                                       │
│   ┌──────────────────────────▼──────────────────────────────────┐   │
│   │  STAGE 4 — TRANSFORM PASSES                                 │   │
│   │                                                             │   │
│   │  • Apply a list of transformation rules to the IR           │   │
│   │  • Handle semantic differences between languages            │   │
│   │  • Example: Python list comprehension                       │   │
│   │    [x*2 for x in items]                                     │   │
│   │    → rewrite as a ForLoop node (Java/C don't have list comp)│   │
│   │  • Each transform is an independent, testable function       │   │
│   │  • Output: modified Canonical IR                            │   │
│   └──────────────────────────┬──────────────────────────────────┘   │
│                              │                                       │
│   ┌──────────────────────────▼──────────────────────────────────┐   │
│   │  STAGE 5 — CODE GENERATION                                  │   │
│   │                                                             │   │
│   │  • Walk the Canonical IR tree                               │   │
│   │  • Convert each node to target language syntax              │   │
│   │  • BaseGenerator defines how to generate all node types     │   │
│   │  • JavaGenerator overrides only what is different in Java   │   │
│   │  • Output: target source code string                        │   │
│   └──────────────────────────┬──────────────────────────────────┘   │
│                              │                                       │
│   OUTPUT: transpiled_code (string) + success/error status           │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 6. Key Design Pattern: Generator Hierarchy

All 5 target language generators share a **single base class** called `BaseGenerator`.

```
BaseGenerator
│   generate_function()
│   generate_if_statement()
│   generate_for_loop()
│   generate_assignment()
│   generate_binary_op()
│   generate_return()
│   ... (all ~20 node types)
│
├── JavaGenerator       (overrides: types, class wrapper, semicolons)
├── JavaScriptGenerator (overrides: function keyword, no types)
├── PythonGenerator     (overrides: indentation, no braces)
├── CGenerator          (overrides: pointers, manual memory, main())
└── CppGenerator        (extends CGenerator, adds classes/namespaces)
```

**Why this matters**: Adding a new target language = write **one new class** that overrides only what's different. Everything common (how to generate a loop, an if-statement, etc.) is inherited from `BaseGenerator` automatically.

This is the same pattern used by **Cito** (open-source transpiler that supports 11 target languages from one codebase).

---

## 7. Language Pairs Supported (8 Total)

| Source Language | Target Languages |
|----------------|-----------------|
| **Python** | Java, JavaScript, C, C++ |
| **Java** | Python, JavaScript |
| **JavaScript** | Java, Python |

**Components needed:**
- **3 Parsers + 3 Lifters** — one per source language (Python, Java, JavaScript)
- **5 Generators** — one per target language (Python, Java, JavaScript, C, C++)

> C and C++ are **target-only** — we generate C/C++ code but never transpile FROM C/C++.

---

## 8. Dataset: StarCoder2

| Property | Value |
|----------|-------|
| Dataset | StarCoder2 (BigCode / HuggingFace) |
| Total rows | 531 million |
| Format | Parquet (262 sharded files) |
| Location | Yotta cluster (SoketLab) |
| Key columns | `language` (source lang), `content` (source code) |

**Filtering applied** before transpilation:
- Only rows where `language` ∈ {Python, Java, JavaScript, C, C++}
- No AI-generated code (`is_generated = False`)
- Between 5 and 300 lines of code
- Minimum 25% alphanumeric characters (removes binary/encoded files)

**Result**: ~500K clean rows used for the initial testing run.

---

## 9. Cluster Execution Model (SLURM)

The pipeline runs on the **SoketLab SLURM cluster** (`slurm.dev.soket.ai`).

```
YOUR LAPTOP
    │
    │  1. Filter dataset → 500K rows saved as parquet
    │  2. Assign target language to each row
    │  3. Split into chunks (e.g., 50 rows per chunk)
    │  4. sbatch --array=0-N transpile_job.sh
    │
    ▼
SLURM HEAD NODE
    │
    ├── Task 0   → Node A  (processes chunk_0000: rows 0–49)
    ├── Task 1   → Node B  (processes chunk_0001: rows 50–99)
    ├── Task 2   → Node C  (processes chunk_0002: rows 100–149)
    └── ...      (all tasks run in parallel across nodes)

Each node independently:
    reads its chunk → runs 5-stage pipeline → writes output chunk

AFTER ALL TASKS DONE:
    Merge all output chunks → final dataset
```

**Why SLURM job arrays?**
- Each code snippet is completely independent — perfect for parallelism
- SLURM distributes work across hundreds of nodes automatically
- If one task fails, only that chunk is lost — rest continue
- Failed chunks can be resubmitted individually

---

## 10. Architecture Inspiration (Which Repos We Used)

We studied 13 open-source transpiler repositories and selected patterns from 4:

| Pattern | Taken From | What We Use It For |
|---------|-----------|-------------------|
| **Hub-and-Spoke Canonical IR** | SQLGlot (SQL ↔ 20+ dialects) | Core IR design — eliminates N×M problem |
| **BaseGenerator → TargetGenerator hierarchy** | Cito (1 source → 11 targets) | Code generation layer |
| **Backend plugin registry + Visitor traversal** | py2many (Python → 7 languages) | Registry mapping lang → components |
| **Composable transform pass pipeline** | Babel (JS transpiler) | Transform stage design |

**9 other repos were studied but not used** because they solved different problems:
- Dart SDK, Haxe → SSA IR, tree shaking (for production compilers, not source-to-source)
- Emscripten → LLVM/WASM specific
- TypeScript → Full symbol table (IDE-level, not needed for self-contained snippets)
- Opal → Source maps (browser debugging, not needed here)
- c2rust → CBOR cross-language bridge (we stay in Python)

---

## 11. Full Component Map

```
code_transpiler/
│
├── pipeline/
│   ├── runner.py        ← Orchestrates all 5 stages for one chunk
│   ├── registry.py      ← Maps language name → (parser, lifter, generator)
│   └── cache.py         ← SHA256 cache to skip duplicate snippets
│
├── parsing/             ← STAGE 2: Source code → Syntax Tree
│   ├── python_parser.py    (uses Python ast module)
│   ├── java_parser.py      (uses tree-sitter)
│   └── javascript_parser.py(uses tree-sitter)
│
├── ir/                  ← The Canonical IR definition
│   ├── nodes.py            (FunctionDef, ForLoop, IfStmt, BinaryOp...)
│   └── visitor.py          (base traversal class)
│
├── lifting/             ← STAGE 3: Syntax Tree → Canonical IR
│   ├── python_lifter.py
│   ├── java_lifter.py
│   └── javascript_lifter.py
│
├── transforms/          ← STAGE 4: Canonical IR → modified Canonical IR
│   ├── engine.py           (runs the list of passes)
│   └── targets/
│       ├── to_java.py       (list comp → for loop, etc.)
│       ├── to_javascript.py
│       ├── to_python.py
│       ├── to_c.py
│       └── to_cpp.py
│
├── codegen/             ← STAGE 5: Canonical IR → Target source code
│   ├── base_generator.py   (all generate_* methods)
│   ├── java_generator.py
│   ├── javascript_generator.py
│   ├── python_generator.py
│   ├── c_generator.py
│   └── cpp_generator.py
│
├── slurm/               ← Cluster execution
│   └── transpile_job.sh    (SLURM batch script)
│
├── scripts/             ← Data preparation
│   ├── filter_starcoder2.py  ✅ Done
│   └── prepare_chunks.py
│
└── main.py              ← Entry point called by each SLURM task
```

---

## 12. Summary in One Diagram

```
StarCoder2 Dataset (531M rows, Yotta cluster)
            │
            │  Filter: 5 languages + quality checks
            ▼
    500K clean rows (parquet)
            │
            │  Add target_lang column per our 8 language pairs
            │  Split into chunks of N rows
            ▼
    SLURM Job Array (one task per chunk, parallel across nodes)
            │
            │  Each task runs the 5-stage pipeline per row:
            │
            │  content + source_lang + target_lang
            │       │
            │  [Preprocess] → [Parse] → [Lift to IR] → [Transform] → [Generate]
            │       │
            │  transpiled_code + success/error
            ▼
    Output chunks (one per SLURM task)
            │
            │  Merge all chunks
            ▼
    Final dataset:
    original StarCoder2 columns
    + source_lang + target_lang
    + transpiled_code
    + transpile_success + transpile_error
```
