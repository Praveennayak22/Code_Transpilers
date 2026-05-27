# Code Transpiler Pipeline — Complete Explanation

---

## 1. What is the Problem?

We want to **automatically convert code from one programming language to another** at large scale.

For example:
- A Python function → equivalent Java function
- A Java class → equivalent JavaScript class
- A Python script → equivalent C program

This is called **transpilation** (source-to-source compilation).

**Why do we need this?**
- To create large training datasets for LLMs (Large Language Models) that understand multiple languages
- Training an LLM on `(Python code, Java equivalent)` pairs teaches it cross-language understanding
- Manually writing these pairs is impossible at 800,000 scale — we need automation

---

## 2. The Naive Approach (and Why It Fails)

The simplest idea: **write one converter per pair**.

```
Python → Java  (converter 1)
Python → JavaScript  (converter 2)
Python → C  (converter 3)
Python → C++  (converter 4)
Java → Python  (converter 5)
Java → JavaScript  (converter 6)
JavaScript → Java  (converter 7)
JavaScript → Python  (converter 8)
```

**Problem:** 8 language pairs = 8 separate converters.  
If you add 1 more language, you need 6 more converters.  
With N languages: **N × (N-1) converters** needed.

For 5 languages → 20 converters.  
For 10 languages → 90 converters.  

This is called the **N² problem** — it doesn't scale.

---

## 3. The Main Idea: Hub-and-Spoke with Intermediate Representation (IR)

**Inspired by:** How real compilers work (GCC, LLVM, Babel, TypeScript)

Instead of converting directly from language A to language B, we:
1. **Parse** source code into a universal intermediate form (IR)
2. **Lift** the syntax into our IR (hub)  
3. **Generate** target code from the IR (spoke)

```
Source Code
    ↓  Parse
Syntax Tree (AST)
    ↓  Lift
Canonical IR  ← ← ← THE HUB
    ↓  Generate
Target Code
```

**With this approach:**
- 5 languages = 5 parsers + 5 generators = **10 components** (not 20!)
- Adding 1 new language = add 1 parser + 1 generator = **2 components** (not 6!)

This is the **N-problem** instead of N². Linear scaling.

---

## 4. Where Did This Idea Come From?

We studied 10 real-world transpilers before designing our system:

| Project | What it does | What we learned |
|---------|-------------|-----------------|
| **Babel** (JS) | JS → older JS | Plugin-based AST transformations |
| **TypeScript** | TypeScript → JS | AST visitor pattern |
| **SQLGlot** (Python) | SQL ↔ 20 dialects | Pure Python, bidirectional, IR-based |
| **Haxe** | Haxe → 10 languages | Hub-and-spoke with one IR |
| **Cito (Ć)** | Ć → 11 languages | One source, many targets cleanly |
| **py2many** | Python → Rust/C++/Go | Python AST as IR |
| **Emscripten** | C/C++ → WebAssembly | LLVM IR as universal hub |

**Key insight from these projects:**  
> Every professional multi-target transpiler uses an **Intermediate Representation** as the hub. No one writes N² direct converters.

**Most directly relevant:** SQLGlot (pure Python, bidirectional, IR-based) and Haxe/Cito (one-to-many targets).

---

## 5. The Pipeline — 5 Stages

```
┌─────────────────────────────────────────────────────────┐
│                  SOURCE CODE (raw text)                  │
└──────────────────────────┬──────────────────────────────┘
                           │
                    Stage 1: PREPROCESS
                    (clean Unicode, remove BOMs,
                     normalize whitespace)
                           │
                    Stage 2: PARSE
                    (source text → Syntax Tree)
                           │
                    Stage 3: LIFT
                    (Syntax Tree → Canonical IR)
                           │
                    Stage 4: TRANSFORM
                    (IR → IR, with target-specific adjustments)
                           │
                    Stage 5: GENERATE
                    (IR → target language text)
                           │
┌──────────────────────────▼──────────────────────────────┐
│               TRANSPILED CODE (target text)              │
└─────────────────────────────────────────────────────────┘
```

---

### Stage 1: Preprocess

**What:** Clean the raw source code before parsing.

**Why:** Real-world code (from StarCoder2) contains:
- Unicode BOM characters (byte-order marks)
- Lone surrogate characters (broken emoji)
- Mixed line endings (Windows `\r\n` vs Unix `\n`)
- Non-printable control characters

If these aren't cleaned, the parser crashes.

**How:**
```python
def preprocess(source: str) -> str:
    source = source.strip()
    source = source.encode("utf-8", errors="replace").decode("utf-8")
    source = source.replace("\r\n", "\n")  # normalize line endings
    return source
```

---

### Stage 2: Parse

**What:** Convert source text into a Syntax Tree (AST).

**Why:** We can't work with raw text — we need structured data representing the code's structure.

**How (different per language):**

| Language | Parser Used | Why |
|----------|-------------|-----|
| Python | `ast` (built-in) | CPython's own AST, 100% accurate, battle-tested |
| Java | `tree-sitter-java` | Fast, robust, handles incomplete code |
| JavaScript | `tree-sitter-javascript` | Handles JSX, ES6+, modern JS |
| C | N/A (target only) | We only generate C, never parse it |
| C++ | N/A (target only) | We only generate C++, never parse it |

**Result:** A tree structure like:
```
Python: x = a + b
         ↓
    Assignment
    ├── target: Name("x")
    └── value: BinaryOp("+")
               ├── Name("a")
               └── Name("b")
```

---

### Stage 3: Lift

**What:** Convert the language-specific Syntax Tree into our **Canonical IR**.

**Why:** The syntax tree is still language-specific.  
Python's AST looks different from Java's tree-sitter tree.  
We need to unify them into ONE common representation.

**The Canonical IR** is a set of universal nodes:

```python
# Our IR nodes — language-neutral
Module, FunctionDef, ClassDef,
Assignment, VarDecl, Return, IfStmt,
WhileLoop, ForLoop, ForEachLoop,
BinaryOp, UnaryOp, Call, Attribute,
Literal, Name, Import, PrintStmt,
TryExcept, Raise, Break, Continue...
```

Every concept that exists across languages maps to one of these.

**Example — same concept, different source syntax:**

```python
# Python source:
for x in items:
    print(x)
```
```java
// Java source:
for (String x : items) {
    System.out.println(x);
}
```
**Both become the same IR:**
```
ForEachLoop(target="x", iterable=Name("items"),
    body=[PrintStmt(args=[Name("x")])])
```

**Lifters:**
- `PythonLifter` — uses `ast.walk()` over Python AST nodes
- `JavaLifter` — uses `tree-sitter` node types, reads source bytes for text
- `JavaScriptLifter` — same as Java lifter but for JS grammar

---

### Stage 4: Transform

**What:** Apply target-language-specific transformations to the IR.

**Why:** Some concepts don't exist in the target language and need to be adapted before code generation.

**Examples of transforms:**
- Python's `for x in range(10)` → in C, becomes a `ForLoop(init=0, cond<10, update++)`
- Python's `print(x)` → in C, mark it as a `PrintStmt` with C-style format strings
- Java's `static void main(String[] args)` → in Python, becomes `def main(args)`

Currently our pipeline passes IR directly to the generator (transforms are minimal). This is the stage where future ML enhancement would plug in.

---

### Stage 5: Generate

**What:** Convert the Canonical IR back into target language source code.

**Why:** Each language has its own syntax rules.

**How:** We have one Generator class per target language, all inheriting from `BaseGenerator`:

```
BaseGenerator
├── JavaGenerator       → public class ... { }
├── JavaScriptGenerator → function ... { }
├── PythonGenerator     → def ...:
├── CGenerator          → int ... (void) { }
└── CppGenerator        → (extends CGenerator)
```

Each generator only overrides what's **different** from the base. For example, Python's `if` statement:

```python
# PythonGenerator:
def generate_IfStmt(self, node):
    self._write(f"if {condition}:")   # no parentheses, colon at end
    self._indent()
    self._gen_body(node.then_body)
    self._dedent()
```

vs Java's:
```python
# JavaGenerator:
def generate_IfStmt(self, node):
    self._write(f"if ({condition}) {{")  # parentheses, curly braces
    self._indent()
    self._gen_body(node.then_body)
    self._dedent()
    self._write("}")
```

**This is the Visitor Pattern** — the same IR node, different rendering per language.

---

## 6. Full Architecture Diagram

```
                    CANONICAL IR NODES
                   (language-neutral hub)
                          ▲  |
           ┌──────────────┘  └──────────────┐
           │   LIFTERS                       │   GENERATORS
           │   (any lang → IR)              │   (IR → any lang)
           │                                 │
  ┌────────┴──────────┐             ┌────────┴──────────┐
  │  PythonLifter     │             │  JavaGenerator     │
  │  (ast module)     │             │  (Java syntax)     │
  ├───────────────────┤             ├───────────────────┤
  │  JavaLifter       │             │  JSGenerator       │
  │  (tree-sitter)    │             │  (JS syntax)       │
  ├───────────────────┤             ├───────────────────┤
  │  JSLifter         │             │  PythonGenerator   │
  │  (tree-sitter)    │             │  (Python syntax)   │
  └───────────────────┘             ├───────────────────┤
                                    │  CGenerator        │
                                    │  (C syntax)        │
                                    ├───────────────────┤
                                    │  CppGenerator      │
                                    │  (C++ syntax)      │
                                    └───────────────────┘

  3 Lifters + 5 Generators = 8 components → 8 language pairs
  (vs 8 direct converters with no reuse)
```

---

## 7. How the Batch Processing Works (SLURM)

**Dataset:** 500K rows from StarCoder2 (100K each: Python, Java, JavaScript, C, C++)

**Expansion:** Each source row gets one job per target language:
- Python row → 4 jobs (→Java, →JS, →C, →C++)
- Java row → 2 jobs (→Python, →JS)
- JavaScript row → 2 jobs (→Java, →Python)
- C/C++ rows → 0 jobs (target only)

**Total: 800,000 transpilation jobs**

**Chunking:** Jobs split into 16,000 chunks of 50 rows each.

**SLURM Job Array:** Each chunk = one SLURM array task.  
MaxArraySize=10000, so submitted in chained batches with `--dependency=afterany`.

**Idempotency:** Each job checks if output file exists before running.  
Safe to re-submit if jobs fail — no duplicate work.

---

## 8. Results

| Metric | Value |
|--------|-------|
| Total rows processed | 647,752 |
| Pipeline success rate | **94.9%** |
| Clean dataset (valid outputs) | **518,684 rows** |
| Wall-clock time | ~3 hours |

| Language Pair | Success Rate |
|---|---|
| JavaScript → Java | **99.8%** |
| JavaScript → Python | **99.8%** |
| Java → JavaScript | **98.4%** |
| Java → Python | **98.4%** |
| Python → C/C++/Java/JS | **90.6%** |

---

## 9. Limitations and Future Work

| Limitation | Reason | Fix |
|---|---|---|
| JSX/React → Python: 26% valid | JSX has no Python equivalent | Out of scope for rule-based |
| Python → C: 11% compile | Python API calls not mapped | Add stdlib mapping (Level 2) |
| Python → C++: 4% compile | Same + type inference | Type inference system |
| ~152K rows missing | SLURM MaxArraySize limit | Re-submit when scheduler free |

**The 94.9% pipeline success rate means the system doesn't crash.**  
**The lower compilation rates mean output is structurally correct but uses Python API calls that don't exist in C.**

This is expected for **Stage 1 (rule-based baseline)**.  
Stage 2 will use an LLM fine-tuned on this dataset to fix library call translation.

---

## 10. Key Design Decisions Summary

| Decision | Choice | Reason |
|---|---|---|
| IR approach | Hub-and-spoke | Scales as N not N² |
| Python parser | `ast` module | Built-in, 100% accurate |
| Java/JS parser | `tree-sitter` | Fast, handles incomplete code |
| IR nodes | Custom dataclasses | Simple, language-neutral |
| Generator pattern | Inheritance + visitor | Clean override per language |
| Batch processing | SLURM job arrays | Cluster-native, parallel |
| Output format | Parquet | Fast, compressed, schema-preserved |
