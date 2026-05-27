"""
LLM REPAIR LOOP — DEEPSEEK-V3.2 INTEGRATION
=============================================

Overview
--------
Stage 6 (post-pipeline): Uses DeepSeek-v3.2 CodeLLM to automatically fix code that 
fails to compile after transpilation. This bridges the gap between "syntactically 
correct" transpilation (94% success) and "actually compiles" (2-55% depending on pair).

Architecture
------------

┌─────────────────────────────────────────────────────┐
│ 1. Standard 5-Stage Pipeline (existing)              │
│    Preprocess → Parse → Lift → Transform → Generate  │
└────────────┬────────────────────────────────────────┘
             │
             ▼ (transpile_success=True but doesn't compile)
┌─────────────────────────────────────────────────────┐
│ 2. LLM Repair Loop (NEW) — Only runs if:             │
│    - Generated code doesn't compile, AND             │
│    - --use-llm-repair flag is set                    │
└────────────┬────────────────────────────────────────┘
             │
             ├─ Attempt 1: Send to LLM with compiler error
             │             ↓
             │             Retry compilation
             │             ✅ Success? Done!
             │             ❌ Failed? Continue...
             │
             ├─ Attempt 2: Send new version to LLM
             │             ↓
             │             Retry compilation
             │             ✅ Success? Done!
             │             ❌ Failed? Continue...
             │
             ├─ Attempt 3: Final attempt
             │             ↓
             │             Give up if still broken
             │
             ▼
┌─────────────────────────────────────────────────────┐
│ 3. Output: Enhanced transpilation result             │
│    - transpiled_code (repaired if successful)        │
│    - repair_attempted: bool                          │
│    - repair_success: bool                            │
│    - repair_attempts: int (1-3)                      │
│    - llm_tokens_used: int                            │
│    - initial_compile_fail: bool                      │
└─────────────────────────────────────────────────────┘


Core Components
---------------

1. llm_client.py — CodeLLMClient
   ├─ Endpoint: http://soketlab-node060:30000/v1/chat/completions
   ├─ Model: deepseek-v3.2
   ├─ Temperature: 0.2 (deterministic for code)
   ├─ Max tokens: 4096
   └─ Handles markdown code blocks + JSON parsing

2. compiler_check.py — Language-specific compilation checkers
   ├─ PythonChecker: ast.parse()
   ├─ JavaScriptChecker: node --check
   ├─ CChecker: gcc -c
   ├─ CppChecker: g++ -c
   └─ JavaChecker: javac

3. repair_engine.py — RepairEngine
   ├─ Orchestrates retry loop
   ├─ Tracks: CompileResult, LLMResponse, RepairAttempt
   ├─ Max 3 attempts per code sample
   └─ Extracts compiler errors for LLM context

4. llm_repair_integration.py — RepairEnabledPipelineRunner
   ├─ Extends PipelineRunner with Stage 6
   ├─ Seamlessly plugs into existing main.py
   ├─ Optional: only runs if --use-llm-repair
   └─ Wraps errors gracefully (doesn't crash pipeline)


Usage
-----

BASIC USAGE (single chunk test):
```bash
cd ~/transpiler/code/code_transpiler

# Without LLM repair (existing behavior)
python3 main.py \
  --input /tmp/test_chunk.jsonl \
  --output /tmp/test_output.jsonl \
  --source-lang Python \
  --target-lang C

# WITH LLM repair (new!)
python3 main.py \
  --input /tmp/test_chunk.jsonl \
  --output /tmp/test_output_repaired.jsonl \
  --source-lang Python \
  --target-lang C \
  --use-llm-repair \
  --llm-endpoint http://soketlab-node060:30000/v1/chat/completions \
  --repair-max-attempts 2
```

SLURM INTEGRATION:
```bash
# For production SLURM runs, add these to slurm/transpile_job.sh:
sbatch --array=0-1599 \
  --job-name=transpile-with-repair \
  ~/transpiler/code/code_transpiler/slurm/transpile_job.sh \
  --use-llm-repair \
  --repair-max-attempts 2
```

TESTING:
```bash
# Test repair loop on sample broken C code
python3 test_llm_repair.py --target-lang C --use-repair

# Test on Java
python3 test_llm_repair.py --target-lang Java --use-repair
```


Expected Impact on Compilation Rates
-------------------------------------

Based on v2 benchmark (200 samples per pair):

Pair                    | Before | With Repair | Improvement
---                     | ---    | ---         | ---
Python → C              | 17%    | ~40-50%     | +23-33 pts
Python → C++            | 2%     | ~30-40%     | +28-38 pts ⭐
Python → Java           | 1%     | ~25-35%     | +24-34 pts ⭐
JavaScript → Java       | 21%    | ~50-65%     | +29-44 pts ⭐
Java → JavaScript       | 22%    | ~45-55%     | +23-33 pts
Java → Python           | 52%    | ~70-80%     | +18-28 pts
JavaScript → Python     | 55%    | ~75-85%     | +20-30 pts
Python → JavaScript     | 30%    | ~50-60%     | +20-30 pts

Overall average: ~20% (current) → ~50%+ (with repair) = 2.5x improvement 🎉


Output Schema (with repair)
---------------------------

Standard fields (unchanged):
  repo_name, repo_url, blob_id, path
  source_lang, target_lang
  content (original source)
  transpile_success, transpile_error, transpile_stage, transpile_time_ms
  cache_hit

NEW fields (if --use-llm-repair enabled):
  repair_attempted: bool          — Was repair attempted?
  repair_success: bool            — Did repair succeed?
  repair_attempts: int (1-3)      — How many LLM attempts?
  llm_tokens_used: int            — Total tokens consumed by DeepSeek
  initial_compile_fail: bool      — Did generated code fail to compile?

Example output row (successful repair):
{
  "source_lang": "Python",
  "target_lang": "C",
  "transpiled_code": "#include <stdio.h>\n...",  ← REPAIRED CODE
  "transpile_success": true,
  "repair_attempted": true,
  "repair_success": true,           ← Repair fixed it!
  "repair_attempts": 1,             ← Fixed on first try
  "llm_tokens_used": 892,           ← ~$0.001 cost
  "initial_compile_fail": true      ← Original didn't compile
}

Example output row (repair failed):
{
  "source_lang": "Python",
  "target_lang": "C++",
  "transpiled_code": "...",        ← Original (not repaired)
  "transpile_success": false,       ← Still broken after repairs
  "repair_attempted": true,
  "repair_success": false,
  "repair_attempts": 2,             ← Tried twice, gave up
  "llm_tokens_used": 1847,
  "initial_compile_fail": true
}


LLM Prompting Strategy
----------------------

System prompt:
  "You are an expert {target_lang} programmer.
   Your task is to fix {target_lang} code that failed to compile.
   Given: code + compiler error message
   Return ONLY the fixed {target_lang} code (no explanations)."

User prompt:
  "Fix this {target_lang} code (transpiled from {source_lang}) that failed:
   
   ```{target_lang}
   [generated code]
   ```
   
   Compiler error:
   ```
   [compiler error from gcc/javac/etc]
   ```
   
   Provide the complete fixed code."

DeepSeek will:
  1. Analyze the error
  2. Identify the issue (undefined reference, type mismatch, etc.)
  3. Fix the code
  4. Return complete, corrected code


Performance Notes
-----------------

Time per repair attempt:
  - LLM call: ~2-5 seconds (network + inference)
  - Compilation check: ~0.5-2 seconds
  - Total per attempt: ~3-7 seconds
  - Max 3 attempts = ~10-20 seconds worst case

Token costs (approximate):
  - Input: ~500-800 tokens (code + error)
  - Output: ~300-500 tokens (fixed code)
  - Total per attempt: ~1000 tokens
  - Per code sample (max 3 attempts): ~3000 tokens

Memory:
  - No significant memory impact (code strings only)
  - LLM endpoint hosted remotely

Recommendations:
  ✅ Use --repair-max-attempts 2 for balance (speed vs accuracy)
  ✅ Use --repair-max-attempts 3 for max accuracy on critical pairs
  ❌ Don't use > 3 (unlikely to fix after 3 tries, wastes LLM calls)


Troubleshooting
---------------

Q: "Connection refused" / "Cannot connect to LLM endpoint"
A: Verify cluster endpoint is reachable:
   curl -X POST http://soketlab-node060:30000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"deepseek-v3.2", "messages":[...]}'

Q: "Repair attempted but code still broken"
A: This can happen for complex semantic issues LLM can't infer.
   Normal for ~40% of cases. Use larger max-attempts or feedback loop.

Q: "Compilation check timeout"
A: Some code takes > 10s to compile (large projects).
   Increase compiler timeout in compiler_check.py

Q: "Node.js not found" / "gcc not found"
A: Ensure all compilers installed in conda environment:
   conda activate transpiler_env
   conda install -c conda-forge gcc g++ openjdk nodejs


Future Enhancements
--------------------

1. Multi-pass feedback loop:
   - Return compiler error to LLM, let it iteratively fix
   - Track "why" repairs fail for pattern learning

2. Semantic type inference:
   - Pre-analyze code for type hints
   - Pass to LLM as context ("x is int, y is string")

3. Cross-language standard library mapping:
   - Build Python→C function mappings (print→printf, etc.)
   - Inject into LLM context

4. Caching LLM responses:
   - Hash (code + error) → cache previous LLM fixes
   - Avoid re-asking for identical issues

5. Batch repair runs:
   - Send 5-10 similar failures to LLM in one batch
   - More efficient than 1-by-1
"""

# Quick ref: CLI flags
"""
--use-llm-repair              Enable Stage 6 LLM repair
--llm-endpoint URL            Custom endpoint (default: cluster DeepSeek)
--repair-max-attempts N       Max repair attempts 1-3 (default: 2)
"""
