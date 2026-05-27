"""
pipeline/batch_runner.py
========================
Batch transpilation runner — re-transpiles all source files from the
existing chunk JSONL files with the latest pipeline code.

Usage:
    python3 pipeline/batch_runner.py \
        --input  /path/to/chunks/     \
        --output /path/to/output_v2/  \
        --workers 8

Input format  : JSONL, each row must have: content, source_lang, target_lang
Output format : Same JSONL schema with updated transpiled_code + metadata
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.registry import build_registry
from pipeline.runner   import PipelineRunner


# ── Worker (runs in subprocess) ───────────────────────────────────────────────

def _init_worker():
    """Called once per worker process to build the registry."""
    global _runner
    _runner = PipelineRunner(build_registry())


def _transpile_row(row: dict) -> dict:
    """Transpile a single row and return updated row."""
    src   = row.get("content", "")
    slang = row.get("source_lang", "")
    tlang = row.get("target_lang", "")
    if not src or not slang or not tlang:
        row["transpile_success"] = False
        row["transpile_error"]   = "missing fields"
        return row
    try:
        result = _runner.transpile(src, slang, tlang)
        row["transpiled_code"]   = result.transpiled_code
        row["transpile_success"] = result.transpile_success
        row["transpile_error"]   = result.transpile_error
        row["pipeline_version"]  = "v2"
    except Exception as e:
        row["transpile_success"] = False
        row["transpile_error"]   = str(e)[:200]
    return row


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Batch transpiler runner v2")
    parser.add_argument("--input",   required=True,  help="Directory with input chunk JSONL files")
    parser.add_argument("--output",  required=True,  help="Directory to write output JSONL files")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    parser.add_argument("--limit",   type=int, default=0, help="Max rows per file (0=all, for testing)")
    parser.add_argument("--pattern", default="out_*.jsonl", help="Glob pattern for input files")
    args = parser.parse_args()

    in_dir  = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    chunk_files = sorted(in_dir.glob(args.pattern))
    if not chunk_files:
        print(f"No files matching '{args.pattern}' found in {in_dir}")
        sys.exit(1)

    print(f"Found {len(chunk_files)} chunk files")
    print(f"Workers: {args.workers}")
    print(f"Output:  {out_dir}")
    print("=" * 60)

    total_rows = total_ok = total_fail = 0
    t_start = time.time()

    for chunk_path in chunk_files:
        out_path = out_dir / chunk_path.name
        if out_path.exists():
            print(f"[SKIP] {chunk_path.name} — already exists")
            continue

        # Read all rows
        rows = []
        with open(chunk_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        if args.limit:
            rows = rows[:args.limit]

        if not rows:
            print(f"[EMPTY] {chunk_path.name}")
            continue

        print(f"[RUN] {chunk_path.name}  ({len(rows)} rows) ...", end="", flush=True)
        t0 = time.time()

        # Process in parallel
        results = []
        with ProcessPoolExecutor(max_workers=args.workers,
                                 initializer=_init_worker) as pool:
            futures = {pool.submit(_transpile_row, row): i for i, row in enumerate(rows)}
            for fut in as_completed(futures):
                try:
                    results.append((futures[fut], fut.result()))
                except Exception as e:
                    idx = futures[fut]
                    rows[idx]["transpile_success"] = False
                    rows[idx]["transpile_error"]   = str(e)[:200]
                    results.append((idx, rows[idx]))

        # Sort results back to original order
        results.sort(key=lambda x: x[0])
        ordered = [r for _, r in results]

        # Write output
        ok   = sum(1 for r in ordered if r.get("transpile_success"))
        fail = len(ordered) - ok
        total_rows += len(ordered)
        total_ok   += ok
        total_fail += fail

        with open(out_path, "w", encoding="utf-8") as f:
            for row in ordered:
                try:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                except (UnicodeEncodeError, ValueError):
                    # Fallback: encode surrogates safely as \uXXXX
                    f.write(json.dumps(row, ensure_ascii=True) + "\n")

        elapsed = time.time() - t0
        pct = 100 * ok // len(ordered) if ordered else 0
        print(f"  {ok}/{len(ordered)} ({pct}%)  [{elapsed:.1f}s]")

    total_elapsed = time.time() - t_start
    print("=" * 60)
    print(f"DONE: {total_ok}/{total_rows} succeeded ({100*total_ok//max(total_rows,1)}%)")
    print(f"Total time: {total_elapsed/60:.1f} min")


if __name__ == "__main__":
    main()
