#!/bin/bash
# Phase 2: Error Analysis Test (Stages 1-5 ONLY - No LLM Repair)
# Purpose: Collect detailed error information to understand which stages fail

set -e

cd ~/transpiler/code/code_transpiler

INPUT_DIR="/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/input/chunks"
OUTPUT_DIR="/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/error_analysis_output/chunks"

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "Starting Phase 2: Error Analysis (Stages 1-5 Only)"
echo "=================================================="
echo "Input:  $INPUT_DIR"
echo "Output: $OUTPUT_DIR"
echo "Mode:   Stages 1-5 only (NO LLM REPAIR)"
echo ""

ERROR_COUNT=0
SUCCESS_COUNT=0
START_TIME=$(date +%s)

# Process first 500 files for error analysis
for i in {0..499}; do
    FILE_NUM=$(printf "%04d" $i)
    INPUT_FILE="$INPUT_DIR/chunk_${FILE_NUM}.jsonl"
    OUTPUT_FILE="$OUTPUT_DIR/chunk_${FILE_NUM}.jsonl"
    
    if [ ! -f "$INPUT_FILE" ]; then
        echo "Warning: $INPUT_FILE not found, skipping"
        continue
    fi
    
    # Run with LLM repair DISABLED (--use-llm-repair=false doesn't exist, so we omit the flag)
    if python3 main.py --input "$INPUT_FILE" --output "$OUTPUT_FILE" 2>/dev/null; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        ERROR_COUNT=$((ERROR_COUNT + 1))
    fi
    
    # Progress logging
    if [ $((($i + 1) % 50)) -eq 0 ]; then
        ELAPSED=$(($(date +%s) - START_TIME))
        echo "$(date '+%a %b %d %I:%M:%S %p %Z %Y'): Processed $(($i + 1)) files (Success: $SUCCESS_COUNT, Errors: $ERROR_COUNT)"
    fi
done

echo ""
echo "Phase 2 Error Analysis Complete!"
echo "Output files: $(ls $OUTPUT_DIR | wc -l)"
echo "=================================="
echo ""
echo "Next: Run error_analysis.py to categorize errors by stage"
echo "Command: python3 error_analysis.py"
