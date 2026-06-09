"""
pipeline/batch_runner.py
========================
Batch transpilation runner — processes all source chunk JSONL files
through the full 5-stage pipeline.

Usage:
    python3 pipeline/batch_runner.py \\
        --input  /path/to/input/chunks/  \\
        --output /path/to/output/chunks/ \\
        --workers 8

Input format  : JSONL, each row must have: content, source_lang, target_lang
Output format : JSONL with the 11-column supervisor-approved schema

Compilation check toggle:
    Set ENABLE_COMPILATION_CHECK = True  to run javac/gcc/node on every row
    Set ENABLE_COMPILATION_CHECK = False to skip it (faster, for large runs)
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

# ─────────────────────────────────────────────────────────────────────────────
# TOGGLE: Set to True to run real compiler checks on source + target code.
#         Set to False to skip compilation checks (much faster for large runs).
# ─────────────────────────────────────────────────────────────────────────────
ENABLE_COMPILATION_CHECK = True


# ── Worker (runs in subprocess) ───────────────────────────────────────────────

def _init_worker():
    """Called once per worker process to build the registry."""
    global _runner
    _runner = PipelineRunner(build_registry())


def _transpile_row(row: dict) -> dict:
    """
    Transpile a single row and return the strict 11-column output schema.

    Output columns (supervisor-approved):
        repo_name, repo_url, github_id, blob_id, path,
        source_language, source_code,
        canonical_IR, transformed_IR,
        target_code, target_language

    Additional tracking fields (kept in JSONL, dropped in Parquet):
        source_compiles, target_compiles,
        transpile_success, transpile_error, transpile_time_ms
    """
    src   = row.get("content", "")
    slang = row.get("source_lang", "")
    tlang = row.get("target_lang", "")

    if not src or not slang or not tlang:
        return {
            "repo_name":        row.get("repo_name", ""),
            "repo_url":         row.get("repo_url", ""),
            "github_id":        row.get("github_id", ""),
            "blob_id":          row.get("blob_id", ""),
            "path":             row.get("path", ""),
            "source_language":  slang,
            "source_code":      src,
            "canonical_IR":     "",
            "transformed_IR":   "",
            "target_code":      "",
            "target_language":  tlang,
            "source_char_count": len(src),
            "target_char_count": 0,
            "source_compiles":  None,
            "target_compiles":  None,
            "transpile_success": False,
            "transpile_error":  "missing fields: content/source_lang/target_lang",
            "transpile_time_ms": 0,
        }

    # ── Source compilation check (before transpilation) ────────────────────
    source_compiles = None
    source_compile_error = ""
    if ENABLE_COMPILATION_CHECK:
        from pipeline.compiler_check import check_compiles
        source_compiles, source_compile_error = check_compiles(src, slang)

    try:
        result = _runner.transpile(src, slang, tlang)

        # ── Target compilation check (after transpilation) ─────────────────
        target_compiles = None
        if ENABLE_COMPILATION_CHECK and result.transpile_success and result.transpiled_code:
            from pipeline.compiler_check import check_compiles
            target_compiles, _ = check_compiles(result.transpiled_code, tlang)

        # ── Build the strict output row ────────────────────────────────────
        target_code = result.transpiled_code or ""
        return {
            # Provenance metadata (from StarCoder2)
            "repo_name":        row.get("repo_name", ""),
            "repo_url":         row.get("repo_url", ""),
            "github_id":        row.get("github_id", ""),
            "blob_id":          row.get("blob_id", ""),
            "path":             row.get("path", ""),
            # Core pipeline columns
            "source_language":  slang,
            "source_code":      result.source_code,
            "canonical_IR":     result.canonical_ir_repr or "",
            "transformed_IR":   result.transformed_ir_repr or "",
            "target_code":      target_code,
            "target_language":  tlang,
            # Character counts
            "source_char_count": len(result.source_code) if result.source_code else 0,
            "target_char_count": len(target_code),
            # Tracking metrics
            "source_compiles":  source_compiles,
            "target_compiles":  target_compiles,
            "transpile_success": result.transpile_success,
            "transpile_error":  result.transpile_error or "",
            "transpile_time_ms": result.transpile_time_ms,
        }

    except Exception as e:
        return {
            "repo_name":        row.get("repo_name", ""),
            "repo_url":         row.get("repo_url", ""),
            "github_id":        row.get("github_id", ""),
            "blob_id":          row.get("blob_id", ""),
            "path":             row.get("path", ""),
            "source_language":  slang,
            "source_code":      src,
            "canonical_IR":     "",
            "transformed_IR":   "",
            "target_code":      "",
            "target_language":  tlang,
            "source_char_count": len(src),
            "target_char_count": 0,
            "source_compiles":  source_compiles,
            "target_compiles":  None,
            "transpile_success": False,
            "transpile_error":  str(e)[:300],
            "transpile_time_ms": 0,
        }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Batch transpiler runner v4")
    parser.add_argument("--input",   required=True,  help="Directory with input chunk JSONL files")
    parser.add_argument("--output",  required=True,  help="Directory to write output JSONL files")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    parser.add_argument("--limit",   type=int, default=0, help="Max rows per chunk (0=all, for testing)")
    parser.add_argument("--pattern", default="chunk_*.jsonl", help="Glob pattern for input files")
    parser.add_argument("--no-compile-check", action="store_true",
                        help="Disable compilation checking (overrides ENABLE_COMPILATION_CHECK)")
    args = parser.parse_args()

    # Allow CLI override of the toggle
    global ENABLE_COMPILATION_CHECK
    if args.no_compile_check:
        ENABLE_COMPILATION_CHECK = False

    in_dir  = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    chunk_files = sorted(in_dir.glob(args.pattern))
    if not chunk_files:
        print(f"No files matching '{args.pattern}' found in {in_dir}")
        sys.exit(1)

    print(f"Found {len(chunk_files)} chunk files")
    print(f"Workers:              {args.workers}")
    print(f"Output:               {out_dir}")
    print(f"Compilation check:    {'ON' if ENABLE_COMPILATION_CHECK else 'OFF'}")
    print("=" * 60)

    total_rows = total_ok = total_fail = 0
    total_src_ok = total_src_fail = 0
    total_tgt_ok = total_tgt_fail = 0
    t_start = time.time()

    # Per-pair stats across all chunks
    pair_times:       dict[str, list] = {}
    pair_src_compile: dict[str, list] = {}
    pair_tgt_compile: dict[str, list] = {}

    for chunk_path in chunk_files:
        out_path = out_dir / chunk_path.name
        if out_path.exists():
            print(f"[SKIP] {chunk_path.name} — already exists")
            continue

        # Read rows
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
                idx = futures[fut]
                try:
                    results.append((idx, fut.result()))
                except Exception as e:
                    results.append((idx, {
                        **rows[idx],
                        "transpile_success": False,
                        "transpile_error": str(e)[:200],
                        "transpile_time_ms": 0,
                    }))

        # Sort back to original order
        results.sort(key=lambda x: x[0])
        ordered = [r for _, r in results]

        # ── Aggregate stats ───────────────────────────────────────────────
        ok   = sum(1 for r in ordered if r.get("transpile_success"))
        fail = len(ordered) - ok
        total_rows += len(ordered)
        total_ok   += ok
        total_fail += fail

        for r in ordered:
            pair = f"{r.get('source_language','?')} -> {r.get('target_language','?')}"
            pair_times.setdefault(pair, []).append(r.get("transpile_time_ms", 0))

            if ENABLE_COMPILATION_CHECK:
                sc = r.get("source_compiles")
                if sc is True:
                    pair_src_compile.setdefault(pair, [0, 0])
                    pair_src_compile[pair][0] += 1
                elif sc is False:
                    pair_src_compile.setdefault(pair, [0, 0])
                    pair_src_compile[pair][1] += 1
                    total_src_fail += 1
                else:
                    pass
                if sc is True: total_src_ok += 1

                tc = r.get("target_compiles")
                if tc is True:
                    pair_tgt_compile.setdefault(pair, [0, 0])
                    pair_tgt_compile[pair][0] += 1
                    total_tgt_ok += 1
                elif tc is False:
                    pair_tgt_compile.setdefault(pair, [0, 0])
                    pair_tgt_compile[pair][1] += 1
                    total_tgt_fail += 1

        # Write output JSONL
        with open(out_path, "w", encoding="utf-8") as f:
            for row in ordered:
                try:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                except (UnicodeEncodeError, ValueError):
                    f.write(json.dumps(row, ensure_ascii=True) + "\n")

        elapsed = time.time() - t0
        throughput = len(ordered) / elapsed if elapsed > 0 else 0
        pct = 100 * ok // len(ordered) if ordered else 0
        print(f"  {ok}/{len(ordered)} ({pct}%)  [{elapsed:.1f}s | {throughput:.1f} rows/s]")

    # ── Final summary ─────────────────────────────────────────────────────
    total_elapsed = time.time() - t_start
    overall_tp = total_rows / total_elapsed if total_elapsed > 0 else 0

    print("=" * 60)
    print(f"DONE: {total_ok}/{total_rows} transpiled successfully ({100*total_ok//max(total_rows,1)}%)")
    print(f"Overall throughput: {overall_tp:.1f} rows/sec")
    print(f"Total time: {total_elapsed/60:.1f} min")

    # Throughput per language pair
    if pair_times:
        print("\nThroughput by language pair:")
        for pair, times in sorted(pair_times.items()):
            avg_ms = sum(times) / len(times) if times else 0
            tput   = (1000 / avg_ms) if avg_ms > 0 else 0
            print(f"  {pair:30s}  avg {avg_ms:.0f}ms/row  ({tput:.1f} rows/s)")

    # Compilation stats
    if ENABLE_COMPILATION_CHECK:
        print(f"\nSource code compilation (raw input quality):")
        print(f"  Total checked:  {total_src_ok + total_src_fail}")
        print(f"  Passed:         {total_src_ok}  ({100*total_src_ok//max(total_src_ok+total_src_fail,1)}%)")
        print(f"  Failed:         {total_src_fail}  ({100*total_src_fail//max(total_src_ok+total_src_fail,1)}%)")

        print(f"\nTarget code compilation (transpilation output quality):")
        print(f"  Total checked:  {total_tgt_ok + total_tgt_fail}")
        print(f"  Passed:         {total_tgt_ok}  ({100*total_tgt_ok//max(total_tgt_ok+total_tgt_fail,1)}%)")
        print(f"  Failed:         {total_tgt_fail}  ({100*total_tgt_fail//max(total_tgt_ok+total_tgt_fail,1)}%)")


if __name__ == "__main__":
    main()
