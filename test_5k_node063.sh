#!/bin/bash
# Test 5k with LLM endpoint on node 063 (kimi.k.2.5)

cd ~/transpiler/code/code_transpiler

INPUT_DIR="/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/output/chunks"
OUTPUT_DIR="/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/test_output_v4/chunks"

mkdir -p "$OUTPUT_DIR"

echo "Starting test transpilation of 5,000 files (0-4999) using node063 LLM endpoint..."

for CHUNK_ID in {0..4999}; do
    INPUT_FILE="$INPUT_DIR/out_$(printf '%04d' $CHUNK_ID).jsonl"
    OUTPUT_FILE="$OUTPUT_DIR/out_$(printf '%04d' $CHUNK_ID).jsonl"
    
    if [ ! -f "$INPUT_FILE" ]; then
        echo "Input file not found: $INPUT_FILE"
        continue
    fi
    
    python3 main.py \
      --input "$INPUT_FILE" \
      --output "$OUTPUT_FILE" \
      --use-llm-repair \
      --llm-endpoint "http://soketlab-node063:30000/v1/chat/completions" \
      --repair-max-attempts 2 > /dev/null 2>&1

    if (( ($CHUNK_ID + 1) % 500 == 0 )); then
        COMPLETE=$(ls "$OUTPUT_DIR"/out_*.jsonl 2>/dev/null | wc -l)
        echo "$(date): Processed $((CHUNK_ID + 1)) files ($COMPLETE output files)"
    fi
done

echo "Test transpilation complete!"
