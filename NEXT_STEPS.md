# Test Completion & Production Deployment Plan

## 1. WHEN TEST COMPLETES

### Check Completion Status
```bash
# SSH to cluster
ssh iitgn_pt_data@slurm.dev.soket.ai

# Verify all 5,000 files processed
ls /projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/test_output_v3/chunks/ | wc -l
# Expected: 5000

# Verify test script finished
ps aux | grep test_5k_direct.sh | grep -v grep
# Expected: (empty - process complete)

# Check for completion message
tail -5 ~/test_5k.log
# Expected: "Test transpilation complete!"
```

### Run Analysis
```bash
# Execute comparison analysis
cd ~/
python3 compare_before_after.py

# Output will show:
# - Total rows processed
# - Transpilation success rate
# - Compilation failures BEFORE LLM repair
# - Compilation failures AFTER LLM repair  
# - Repair success rate
# - Improvement by language pair
```

## 2. INTERPRETING RESULTS

### Key Metrics to Check
1. **Transpilation Success Rate** (should be >90%)
   - Current baseline: 74.3% pre-repair failure rate in batches 1-2
   - Need: High transpilation success before LLM can repair

2. **Pre-LLM Compilation Failures** (baseline metric)
   - Batches 1-2 had 74.3% post-generation compilation failures
   - Test should show similar ~70-75% pre-repair failure rate

3. **Post-LLM Compilation Failures** (improvement metric)
   - Target: ≥30% of failures fixed by LLM
   - Example: 70% → 49% = 30% of failures eliminated
   - Calculation: (pre - post) / pre ≥ 0.30

4. **LLM Repair Success Rate**
   - Should be >80% (test showed 100% on 5-sample)
   - Indicates reliability of repair loop

5. **By Language Pair**
   - Check which pairs benefit most from LLM
   - Python↔Java, Python↔JavaScript typically have highest failure rates
   - Some pairs may need targeted fixes

### Decision Criteria
**PROCEED TO FULL BATCH if:**
- ✅ Transpilation success >80%
- ✅ ≥30% of compilation failures fixed
- ✅ LLM repair success >75%
- ✅ No critical errors in log

**INVESTIGATE if:**
- ❌ Transpilation success <80% (parsing issues)
- ❌ <30% failures fixed (LLM ineffective)
- ❌ LLM repair success <75% (API issues)
- ❌ Errors visible in analysis output

## 3. PROCEEDING TO FULL BATCH (12,956 FILES)

### If Results Support Production Run:

#### Option A: Sequential Processing (Safer)
```bash
# Create production script
cat > ~/batch_full_direct.sh << 'EOF'
#!/bin/bash
cd ~/transpiler/code/code_transpiler

for i in {0..12955}; do
    FILE_NUM=$(printf "%04d" $i)
    INPUT="/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/output/chunks/out_${FILE_NUM}.jsonl"
    OUTPUT="/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/v3/chunks/out_${FILE_NUM}.jsonl"
    
    if [ -f "$INPUT" ]; then
        python3 main.py --input "$INPUT" --output "$OUTPUT" --use-llm-repair --repair-max-attempts 2
    fi
    
    if [ $((($i + 1) % 1000)) -eq 0 ]; then
        echo "$(date '+%a %b %d %I:%M:%S %p %Z %Y'): Processed $(($i + 1)) files"
    fi
done

echo "Full batch transpilation complete!"
echo "Output files: $(ls /projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/v3/chunks/ | wc -l)"
EOF

chmod +x ~/batch_full_direct.sh

# Run in background
nohup ~/batch_full_direct.sh > ~/batch_full.log 2>&1 &

# Monitor progress
tail -f ~/batch_full.log
```

#### Option B: SLURM Batch Job (Faster)
```bash
# Submit to job queue
sbatch << 'EOF'
#!/bin/bash
#SBATCH --partition=rl
#SBATCH --time=48:00:00
#SBATCH --job-name=transpiler_v3_full

cd ~/transpiler/code/code_transpiler

for i in {0..12955}; do
    FILE_NUM=$(printf "%04d" $i)
    INPUT="/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/output/chunks/out_${FILE_NUM}.jsonl"
    OUTPUT="/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/v3/chunks/out_${FILE_NUM}.jsonl"
    
    python3 main.py --input "$INPUT" --output "$OUTPUT" --use-llm-repair --repair-max-attempts 2
    
    if [ $((($i + 1) % 1000)) -eq 0 ]; then
        echo "Processed $(($i + 1)) files - $(date)"
    fi
done

echo "Full batch complete: $(ls /projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/v3/chunks/ | wc -l) files"
EOF
```

#### Output Verification
```bash
# Check output directory exists
mkdir -p /projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/v3/chunks/

# Monitor progress
ls /projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/v3/chunks/ | wc -l

# Rough time estimate:
# - 5,000 files took ~83 minutes
# - 12,956 files ≈ ~217 minutes (3.6 hours)
```

## 4. FINAL ANALYSIS (After Full Batch)

### Comprehensive Comparison
```bash
# Run final analysis with full batch output
python3 compare_before_after.py /projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/v3/chunks/

# Results will show:
# - Overall improvement statistics
# - Language pair performance
# - Repair statistics (attempts, success rate, tokens used)
```

### Generate Report
```bash
# Create summary report
cat > ~/final_report.txt << 'EOF'
TEST PHASE (5k files):
- Input: out_0000.jsonl through out_4999.jsonl
- Output: test_output_v3/chunks/
- Metrics: [INSERT_TEST_RESULTS]

FULL BATCH (12,956 files):
- Input: All out_0000.jsonl through out_12955.jsonl
- Output: v3/chunks/
- Metrics: [INSERT_FULL_RESULTS]

IMPROVEMENT:
- Compilation failure reduction: [X]%
- Repair success rate: [Y]%
- Average tokens per repair: [Z]
- Total cost estimate: [N] * $0.27/1M tokens

RECOMMENDATION:
[Proceed with next phase / Investigate further / Deploy to production]
EOF
```

## 5. CLUSTER SYNC CHECKLIST

After test completes, if proceeding to full batch, verify:

- [ ] All fixes deployed (Python parser, Java lifter, JS lifter)
- [ ] LLM repair modules present (llm_client.py, repair_engine.py, etc.)
- [ ] Main.py has --use-llm-repair flag
- [ ] Output directory exists: `/projects/data/.../v3/chunks/`
- [ ] Comparison script deployed: `~/compare_before_after.py`

### Quick Verification
```bash
ssh iitgn_pt_data@slurm.dev.soket.ai << 'EOF'
echo "=== Parser Fixes ==="
grep -q "_normalize_indentation" ~/transpiler/code/code_transpiler/parsing/python_parser.py && echo "✓ Python parser" || echo "✗ Python parser"
grep -q "_parse_number" ~/transpiler/code/code_transpiler/lifting/java_lifter.py && echo "✓ Java lifter" || echo "✗ Java lifter"
grep -q "int(text, 0)" ~/transpiler/code/code_transpiler/lifting/javascript_lifter.py && echo "✓ JS lifter" || echo "✗ JS lifter"

echo "=== LLM Integration ==="
grep -q "use-llm-repair" ~/transpiler/code/code_transpiler/main.py && echo "✓ Main.py flags" || echo "✗ Main.py flags"
[ -f ~/compare_before_after.py ] && echo "✓ Analysis script" || echo "✗ Analysis script"

echo "=== Output Directory ==="
mkdir -p /projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/v3/chunks/
echo "✓ Output dir ready"
EOF
```

## 6. TROUBLESHOOTING

### If Test Results Show <30% Improvement
1. Check LLM endpoint is accessible: `curl http://soketlab-node060:30000/v1/models`
2. Review sample failed repairs: Look for patterns in compilation errors
3. Adjust repair prompt engineering (in repair_engine.py)
4. Check token limits aren't being hit

### If Transpilation Success <80%
1. Run parser validation: `python3 -c "from parsing.python_parser import PythonParser; p = PythonParser(); print(p.parse('print \"test\"'))"`
2. Check for uncaught edge cases
3. May need additional parser fixes before LLM repair is effective

### If LLM Endpoint Slow/Unavailable
1. Check endpoint: `ssh iitgn_pt_data@slurm.dev.soket.ai "curl -s http://soketlab-node060:30000/v1/models | head -c 100"`
2. Fall back to sequential timeout handling
3. Consider batching repairs to reduce API calls

---

**Timeline Estimate:**
- Test completion: ~1:23 PM (started 1:35 PM, ~83 min runtime)
- Analysis: ~2 min
- Full batch execution: ~3.6 hours
- Final analysis: ~2 min

**Total project duration:** ~4 hours from test start to final results
