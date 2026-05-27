"""
main.py
=======
CLI entry point for the transpiler pipeline.

Called by each SLURM task:
    python main.py --input chunk_0000.jsonl --output out_0000.jsonl
                   --source-lang Python --target-lang Java

Or in auto mode (source/target lang read from each row):
    python main.py --input chunk_0000.jsonl --output out_0000.jsonl
"""

from __future__ import annotations
import argparse
import json
import sys
import os
import time
from pathlib import Path
from tqdm import tqdm

# Add parent dir to path so imports work when run from any directory
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.registry import build_registry
from pipeline.runner import PipelineRunner
from pipeline.cache import TranspileCache
from llm_repair_integration import RepairEnabledPipelineRunner


def parse_args():
    parser = argparse.ArgumentParser(
        description="Code Transpiler Pipeline — SLURM task entry point with optional LLM repair"
    )
    parser.add_argument(
        "--input", required=True,
        help="Input JSONL file (one JSON object per line)"
    )
    parser.add_argument(
        "--output", required=True,
        help="Output JSONL file"
    )
    parser.add_argument(
        "--source-lang", default=None,
        help="Override source language for all rows (e.g. Python)"
    )
    parser.add_argument(
        "--target-lang", default=None,
        help="Override target language for all rows (e.g. Java)"
    )
    parser.add_argument(
        "--cache-dir", default=None,
        help="Directory for the SHA256 transpilation cache"
    )
    parser.add_argument(
        "--use-llm-repair", action="store_true",
        help="Enable LLM repair loop for failed compilations (requires DeepSeek endpoint)"
    )
    parser.add_argument(
        "--llm-endpoint", default="http://soketlab-node060:30000/v1/chat/completions",
        help="CodeLLM endpoint (default: cluster hosted DeepSeek-v3.2)"
    )
    parser.add_argument(
        "--repair-max-attempts", type=int, default=2,
        help="Maximum LLM repair attempts (1-3, default: 2)"
    )
    parser.add_argument(
        "--dump-ir", action="store_true",
        help="Dump Canonical IR to stderr for debugging"
    )
    parser.add_argument(
        "--max-rows", type=int, default=None,
        help="Maximum rows to process (for testing)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build registry + runner
    print(f"Loading pipeline...", file=sys.stderr)
    registry = build_registry()
    cache    = TranspileCache(args.cache_dir) if args.cache_dir else None
    
    # Use repair-enabled runner if requested
    if args.use_llm_repair:
        print(f"LLM repair enabled (endpoint: {args.llm_endpoint})", file=sys.stderr)
        runner = RepairEnabledPipelineRunner(
            registry,
            cache=cache,
            use_llm_repair=True,
            llm_endpoint=args.llm_endpoint,
            repair_max_attempts=args.repair_max_attempts
        )
    else:
        runner = PipelineRunner(registry, cache=cache)
    
    print(f"Pipeline ready. {registry.summary()}", file=sys.stderr)

    # Count rows
    with open(input_path, "r", encoding="utf-8") as f:
        total_rows = sum(1 for _ in f)

    if args.max_rows:
        total_rows = min(total_rows, args.max_rows)

    # Process
    success_count = 0
    error_count   = 0
    skip_count    = 0
    start_time    = time.monotonic()

    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:

        for i, line in enumerate(tqdm(fin, total=total_rows, desc="Transpiling")):
            if args.max_rows and i >= args.max_rows:
                break

            line = line.strip()
            if not line:
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"JSON error on line {i}: {e}", file=sys.stderr)
                skip_count += 1
                continue

            # Get source/target lang from CLI override or row
            source_lang = args.source_lang or row.get("source_lang") or row.get("language")
            target_lang = args.target_lang or row.get("target_lang")
            source_code = row.get("content", "")

            if not source_lang or not target_lang or not source_code:
                skip_count += 1
                continue

            # Run pipeline
            result = runner.transpile(source_code, source_lang, target_lang)

            # Build output row
            out_row = {
                # Pass through original metadata
                "repo_name":         row.get("repo_name"),
                "repo_url":          row.get("repo_url"),
                "blob_id":           row.get("blob_id"),
                "path":              row.get("path"),
                "source_lang":       source_lang,
                "target_lang":       target_lang,
                "content":           source_code,
                # Transpilation results
                "transpiled_code":   result.transpiled_code,
                "transpile_success": result.transpile_success,
                "transpile_error":   result.transpile_error,
                "transpile_stage":   result.transpile_stage,
                "transpile_time_ms": result.transpile_time_ms,
                "cache_hit":         result.cache_hit,
            }
            
            # Add LLM repair info if available
            if hasattr(result, 'repair_attempted'):
                out_row["repair_attempted"] = result.repair_attempted
                out_row["repair_success"] = result.repair_success
                out_row["repair_attempts"] = result.repair_attempts
                out_row["llm_tokens_used"] = result.llm_tokens_used
                out_row["initial_compile_fail"] = result.initial_compile_fail
            
            fout.write(json.dumps(out_row, ensure_ascii=False) + "\n")

            if result.transpile_success:
                success_count += 1
            else:
                error_count += 1
                if error_count <= 5:  # Print first 5 errors
                    print(
                        f"\n[ERROR row {i}] {source_lang}→{target_lang}: "
                        f"{result.transpile_error[:200]}",
                        file=sys.stderr
                    )

    elapsed = time.monotonic() - start_time

    # Summary
    total = success_count + error_count + skip_count
    print("\n" + "="*50, file=sys.stderr)
    print(f"DONE: {output_path}", file=sys.stderr)
    print(f"  Total rows  : {total}", file=sys.stderr)
    print(f"  Success     : {success_count} ({100*success_count/max(total,1):.1f}%)", file=sys.stderr)
    print(f"  Errors      : {error_count}", file=sys.stderr)
    print(f"  Skipped     : {skip_count}", file=sys.stderr)
    print(f"  Time        : {elapsed:.1f}s", file=sys.stderr)
    print(f"  Throughput  : {total/elapsed:.1f} rows/sec", file=sys.stderr)
    print("="*50, file=sys.stderr)


if __name__ == "__main__":
    main()
