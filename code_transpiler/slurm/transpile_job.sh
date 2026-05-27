#!/bin/bash
#SBATCH --job-name=transpile
#SBATCH --partition=rl
#SBATCH --output=/home/iitgn_pt_data/transpiler/logs/slurm/transpile_%A_%a.out
#SBATCH --error=/home/iitgn_pt_data/transpiler/logs/slurm/transpile_%A_%a.err
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --nodes=1

# ── Environment ───────────────────────────────────────────────────────────────
TASK_ID=$SLURM_ARRAY_TASK_ID
JOB_ID=$SLURM_ARRAY_JOB_ID

CHUNK_DIR="/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/input/chunks"
OUTPUT_DIR="/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/output/chunks"
CACHE_DIR="/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/cache"
CODE_DIR="/home/iitgn_pt_data/transpiler/code/code_transpiler"
LOG_DIR="/home/iitgn_pt_data/transpiler/logs/slurm"

mkdir -p "$OUTPUT_DIR" "$CACHE_DIR" "$LOG_DIR"

CHUNK_FILE=$(printf "%s/chunk_%04d.jsonl" "$CHUNK_DIR" "$TASK_ID")
OUTPUT_FILE=$(printf "%s/out_%04d.jsonl" "$OUTPUT_DIR" "$TASK_ID")

echo "============================="
echo "Job Array ID : $JOB_ID"
echo "Task ID      : $TASK_ID"
echo "Node         : $HOSTNAME"
echo "Started      : $(date)"
echo "Input chunk  : $CHUNK_FILE"
echo "Output file  : $OUTPUT_FILE"
echo "============================="

# ── Skip if already done (idempotent) ────────────────────────────────────────
if [ -f "$OUTPUT_FILE" ]; then
    echo "Output already exists — skipping (idempotent)."
    exit 0
fi

# ── Check input exists ────────────────────────────────────────────────────────
if [ ! -f "$CHUNK_FILE" ]; then
    echo "ERROR: Chunk file not found: $CHUNK_FILE"
    exit 1
fi

# ── Activate conda ────────────────────────────────────────────────────────────
source /home/iitgn_pt_data/miniconda3/etc/profile.d/conda.sh
conda activate transpiler_env

# ── Run transpiler ────────────────────────────────────────────────────────────
python3 "$CODE_DIR/main.py" \
    --input  "$CHUNK_FILE" \
    --output "$OUTPUT_FILE" \
    --cache-dir "$CACHE_DIR"

EXIT_CODE=$?

echo "============================="
echo "Exit code : $EXIT_CODE"
echo "Finished  : $(date)"
echo "============================="

exit $EXIT_CODE
