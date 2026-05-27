# Error Storage & Analysis Guide - Phase 2

## Overview

Phase 2 runs the transpiler through **Stages 1-5 only** (without LLM repair) to understand where errors originate.

```
INPUT → Stage 1 (Preprocess)
       ↓
       Stage 2 (Parse) ← ERRORS CAUGHT HERE
       ↓
       Stage 3 (Lift) ← ERRORS CAUGHT HERE
       ↓
       Stage 4 (Transform) ← ERRORS CAUGHT HERE
       ↓
       Stage 5 (Generate) ← ERRORS CAUGHT HERE
       ↓
       Compile Check ← COMPILATION ERRORS CAUGHT HERE
       ↓
       OUTPUT (no LLM repair)
```

---

## Error Categories & What They Tell Us

### 1. **PARSING ERRORS** (Stage 2: Parse)
**Root Cause**: Source code syntax is invalid or not recognized

**Typical Errors**:
```
SyntaxError: invalid syntax
IndentationError: unexpected indent
EOFError: unexpected EOF while parsing
Unclosed string literal
```

**What it means**:
- Input source code has syntax issues
- Usually language-specific problems (Python 2 vs 3, tabs vs spaces)
- Our parser fixes address some of these (8.5% of code)

**Example**:
```python
# This will cause parsing error:
def foo():
  print "hello"  # Python 2 print statement in Python 3 code
```

**Fix Strategy**:
- Improve Python parser (Python 2→3 conversion)
- Add more language-specific syntax handling

---

### 2. **LIFTING ERRORS** (Stage 3: Lift)
**Root Cause**: Cannot convert CST (syntax tree) to Canonical IR

**Typical Errors**:
```
AttributeError: 'Node' object has no attribute 'value'
KeyError: unexpected node type 'X'
TypeError: Cannot lift expression type
```

**What it means**:
- Syntax is valid but structure isn't recognized by lifter
- Lifter doesn't handle specific language constructs
- Our Java/JS lifter fixes help here

**Example**:
```java
// This causes lifting error if _parse_number not fixed:
long value = 0xFFFFFFFF_L;  // Hex with underscore and L suffix
```

**Fix Strategy**:
- Improve lifter methods (we fixed Java suffixes and JS hex/octal)
- Handle more edge cases in number parsing
- Add support for newer language features

---

### 3. **TRANSFORM ERRORS** (Stage 4: Transform)
**Root Cause**: Semantic rewriting in IR fails

**Typical Errors**:
```
Transform failed: Unknown operation 'X'
Semantic transformation error
Cannot apply transform to IR node
```

**What it means**:
- Code structure is understood but transformation rules don't apply
- Semantic analysis hits unsupported patterns
- May need more sophisticated rewriting rules

**Fix Strategy**:
- Extend transform rules for more patterns
- Add pattern matching for edge cases
- Improve semantic analysis

---

### 4. **GENERATION ERRORS** (Stage 5: Generate)
**Root Cause**: Cannot convert IR back to target language

**Typical Errors**:
```
Generation failed: Cannot generate X
Unsupported syntax in target language
Invalid IR structure for generation
```

**What it means**:
- IR is valid but target language code cannot be generated
- Target language doesn't support source language construct
- Code generation templates incomplete

**Fix Strategy**:
- Improve code generation templates
- Handle language-specific limitations
- Add fallback generation strategies

---

### 5. **COMPILATION ERRORS** (Post-Generation: Compilation Check)
**Root Cause**: Generated code syntactically valid but has semantic/logic errors

**Typical Errors**:
```
NameError: name 'undefined_function' is not defined
ImportError: No module named 'requests'
AttributeError: 'str' object has no attribute 'push'
TypeError: function() takes 2 positional arguments but 3 were given
```

**What it means**:
- Transpilation succeeded BUT generated code doesn't compile
- Issues: Wrong library calls, incorrect API usage, type mismatches
- **This is what LLM repair fixes!**

**Example**:
```python
# Transpiled to Java but uses wrong API:
result = my_list.push(value)  # Python has .append(), Java has .add()
```

**Fix Strategy**:
- **LLM repair** (Stage 6) - Sends error + code to LLM
- Better semantic mapping in transform stage
- Improved code generation for language idioms

---

## How to Interpret the Error Report

### Report Format

```
ERROR ANALYSIS REPORT - Phase 2 (Stages 1-5 Analysis)

OVERALL STATISTICS
  Total rows analyzed:        5,000
  Transpilation success:      4,500 (90.0%)
  Transpilation failures:     500 (10.0%)
  Compilation success:        1,200
  Compilation failures:       3,300 (73.3%)

ERRORS BY CATEGORY (Root Cause Analysis)

PARSING
  Stage: Stage 2: Parse
  Description: Source code parsing failed
  Count: 250 occurrences
  Percentage of total: 5.0%
  By language pair:
    Python→Java: 150
    Python→C: 100
  Example errors:
    1. [out_0001.jsonl] SyntaxError: invalid syntax
    2. [out_0005.jsonl] IndentationError: unexpected indent
```

### Key Metrics to Watch

| Metric | Good Value | Warning | Critical |
|--------|-----------|---------|----------|
| **Parsing errors** | <5% | 5-10% | >10% |
| **Lifting errors** | <5% | 5-10% | >10% |
| **Compilation failures** | <50% | 50-70% | >70% |

---

## Phase 2 Workflow

### Step 1: Run Error Analysis
```bash
ssh iitgn_pt_data@slurm.dev.soket.ai
cd ~/transpiler/code/code_transpiler
nohup ~/phase2_error_analysis.sh > ~/phase2_analysis.log 2>&1 &

# Monitor
tail -f ~/phase2_analysis.log
```

### Step 2: Generate Error Report
```bash
# After Phase 2 completes:
python3 ~/error_analysis.py

# Output shows errors by stage and category
```

### Step 3: Identify Bottlenecks
```
If Stage 2 (Parsing) errors >10%:
  → Need more robust Python/Java/JS parsers

If Stage 3 (Lifting) errors >10%:
  → Need better CST→IR conversion
  → Fix numeric literals, language idioms

If Stage 5 (Generation) errors >10%:
  → Need better code generation templates

If Compilation failures >70%:
  → LLM repair should fix these (expected)
  → Stage 6 is where LLM helps
```

---

## What We Learn From Each Stage

### From Parsing Errors
- **Source**: Which languages/constructs are problematic
- **Action**: Target parser improvements
- **Examples**: Python 2 syntax, mixed indentation, unclosed strings

### From Lifting Errors
- **Source**: AST→IR conversion gaps
- **Action**: Improve lifter methods
- **Examples**: Numeric suffixes (1L, 0xFF), special operators

### From Generation Errors
- **Source**: IR→Code generation limitations
- **Action**: Enhance code generation templates
- **Examples**: Unsupported constructs, language limitations

### From Compilation Errors
- **Source**: Semantic/API mapping issues
- **Action**: LLM repair + better semantic analysis
- **Examples**: Wrong function names, type mismatches, library calls

---

## Integration with Phase 1 (LLM Repair)

**Phase 1**: Full pipeline with LLM repair
- Shows: Overall improvement % from LLM
- Answers: Does Stage 6 help?

**Phase 2**: Stages 1-5 only (no LLM)
- Shows: Where errors originate
- Answers: Which stages need fixing?

**Combined Insight**:
```
Phase 1 shows: 74.3% pre-repair failures → 50% post-repair (26.3% fixed by LLM)
Phase 2 shows: 30% Stage 3 errors + 40% Stage 5 errors + 30% Compilation errors

Conclusion: 
- Stage 3 lifting needs fix (~30%)
- Stage 5 generation needs improvement (~40%) 
- Remaining issues are semantic (LLM handles ~100% of these)
```

---

## Commands Reference

### Run Phase 2 Error Analysis
```bash
ssh iitgn_pt_data@slurm.dev.soket.ai "nohup ~/phase2_error_analysis.sh > ~/phase2.log 2>&1 & echo 'Phase 2 started'"
```

### Generate Error Report
```bash
ssh iitgn_pt_data@slurm.dev.soket.ai "cd ~ && python3 error_analysis.py"
```

### View Detailed Errors
```bash
ssh iitgn_pt_data@slurm.dev.soket.ai "cat error_analysis_report.json | jq '.'"
```

### Check Specific Language Pair Errors
```bash
ssh iitgn_pt_data@slurm.dev.soket.ai << 'EOF'
cd ~/
python3 -c "
import json
with open('error_analysis/chunks/out_0000.jsonl') as f:
    for line in f:
        row = json.loads(line)
        if not row.get('transpile_success'):
            print(f'{row[\"language_pair\"]}: {row[\"error_message\"][:100]}')
"
EOF
```

---

## Expected Outcomes

### Optimistic Scenario
- **Parsing errors**: <3%
- **Lifting errors**: <3%
- **Generation errors**: <5%
- **Compilation failures**: ~70% (all semantic - LLM fixes these)
- **Conclusion**: Pipeline is good, LLM repair effective

### Realistic Scenario
- **Parsing errors**: 5-8% (Python 2, indentation)
- **Lifting errors**: 5-10% (numeric literals, language constructs)
- **Generation errors**: 10-15% (unsupported patterns)
- **Compilation failures**: 65-75% (semantic - LLM repair domain)
- **Conclusion**: Some parser/lifter improvements possible, LLM handles majority

### Problem Scenario
- **Parsing errors**: >15% (too many syntax issues)
- **Lifting errors**: >15% (lifter can't handle source code)
- **Generation errors**: >20% (generation templates insufficient)
- **Conclusion**: Need deeper pipeline fixes before LLM can help effectively

---

**Phase 2 Goal**: Understand where errors come from so we can target improvements effectively.
