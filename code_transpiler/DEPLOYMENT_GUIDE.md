"""
DEPLOYMENT GUIDE — LLM Repair Loop
===================================

Quick Start on Cluster
"""

# Step 1: Verify all files are in place
"""
ssh iitgn_pt_data@slurm.dev.soket.ai

cd ~/transpiler/code/code_transpiler

# Should exist:
ls -la llm_client.py compiler_check.py repair_engine.py llm_repair_integration.py test_llm_repair.py
"""

# Step 2: Test repair loop on sample
"""
# Enter environment
conda activate transpiler_env

# Test with sample broken code (no real transpilation)
python3 test_llm_repair.py --target-lang C --use-repair

# Expected output:
# Step 1: Check if original code compiles...
#   ❌ Compilation failed!
#   Error: ...
# 
# Step 2: Initialize LLM repair engine...
#   ✅ Ready
# 
# Step 3: Attempt LLM repair...
#   Repair attempt 1/2...
#   ✅ Fixed on attempt 1
# 
# REPAIR RESULTS
# Success: True
# Attempts: 1
# LLM Tokens Used: 892
# Time: 4823.5ms
"""

# Step 3: Test on real transpilation (5 rows)
"""
# Create test chunk with 5 Python→C transpilations
python3 ~/transpiler/code/code_transpiler/pipeline/batch_runner.py \
  --input ~/transpiler/data/input/chunks/chunk_0000.jsonl \
  --output /tmp/test_chunk_v3.jsonl \
  --workers 1 \
  --max-rows 5

# RUN WITH REPAIR (THIS IS THE NEW PART!)
python3 main.py \
  --input /tmp/test_chunk_v3.jsonl \
  --output /tmp/test_chunk_v3_repaired.jsonl \
  --use-llm-repair \
  --repair-max-attempts 2

# Check output
cat /tmp/test_chunk_v3_repaired.jsonl | python3 -m json.tool | head -100
"""

# Step 4: Benchmark with repair (on 100 samples per pair)
"""
# This will take a while (100 samples × 8 pairs × up to 3 repair attempts)
# But will show real impact

python3 pipeline/batch_runner.py \
  --input ~/transpiler/data/input/chunks/ \
  --output ~/transpiler/output_v3_with_repair/chunks/ \
  --workers 8 \
  --max-samples-per-pair 100 \
  --use-llm-repair

# Then run benchmark
python3 /tmp/benchmark_v3_with_repair.py
"""

# Step 5: Full production run
"""
# Update SLURM script to add repair flags:
# vim ~/transpiler/code/code_transpiler/slurm/transpile_job.sh

# Add these parameters to main.py call:
#   --use-llm-repair \
#   --repair-max-attempts 2

# Submit full job array:
sbatch --array=0-1599 \
  --job-name=transpile-v3-with-repair \
  ~/transpiler/code/code_transpiler/slurm/transpile_job.sh

# Monitor progress
squeue -u iitgn_pt_data | grep transpile-v3

# Check output
ls ~/transpiler/output_v3_with_repair/chunks/ | wc -l  # Should have 1600 files
"""

# Validation Checklist
"""
✅ All 4 new .py files exist and importable
✅ main.py has --use-llm-repair flag
✅ DeepSeek endpoint reachable: curl http://soketlab-node060:30000/v1/chat/completions
✅ Compilers available: gcc, g++, javac, node
✅ Test repair loop works on sample code
✅ Test repair loop works on real transpiled code
✅ Output includes repair_* fields
✅ SLURM script updated with repair flags
✅ Output directory writable and has space
"""

# Costs & Performance
"""
Estimated costs for full 800K run with repair:
- LLM tokens: 800K samples × 1000 tokens/attempt avg ≈ 800M tokens
- At $0.0001/1K tokens ≈ $80 total
- Time: ~72 hours with 8 parallel workers (vs 4.7 min for v2 base)

Breakdown by stage:
- Base transpilation: 4.7 min (v2 baseline)
- Repair loop (optional): +70 hours if enabled on all
  - But only runs on ~50% of samples (ones that don't compile)
  - Actual: ~35 hours additional
- Total with repair: ~36 hours
- Cost: ~$80

ROI:
- Compilation rate: 20% → 50% (2.5x improvement)
- Cost per 1% improvement: $80/30 = $2.67
- Worth it for production dataset
"""

# Troubleshooting
"""
ERROR: Cannot connect to LLM endpoint
→ Check if soketlab-node060 is up
→ Verify network access from login node
→ curl -v http://soketlab-node060:30000/health

ERROR: ImportError: No module named 'requests'
→ pip install requests (should be in transpiler_env)
→ conda install requests

ERROR: 'gcc' not found
→ conda activate transpiler_env
→ conda install -c conda-forge gcc

ERROR: LLM responses are empty
→ Check endpoint returns valid JSON
→ Check model name 'deepseek-v3.2' exists

ERROR: Repair loop hangs
→ Check network connectivity to node060
→ Increase timeout in llm_client.py (default 30s)
→ Set --repair-max-attempts 1 (faster, less accurate)
"""

print(__doc__)
