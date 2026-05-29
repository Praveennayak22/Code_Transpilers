"""
source_audit.py
================
Audits the raw SOURCE CODE in the input dataset BEFORE transpilation.
Reports:
  1. Source code compilation/syntax error rate per language
  2. Per-language breakdown of the most common errors
  3. Throughput per language

Uses parallel workers per language so javac/gcc don't bottleneck.

Usage:
    python3 source_audit.py \
        --input /path/to/chunks/ \
        --samples 200 \
        --pattern "chunk_*.jsonl" \
        --workers 16
"""

from __future__ import annotations
import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


# ── Per-language compile checkers ─────────────────────────────────────────────

def check_python(code: str) -> tuple[bool, str]:
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def check_javascript(code: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w",
                                     delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        r = subprocess.run(["node", "--check", tmp],
                           capture_output=True, timeout=5, text=True)
        if r.returncode == 0:
            return True, ""
        err = next((l for l in r.stderr.splitlines() if l.strip()), r.stderr[:200])
        return False, err
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except FileNotFoundError:
        return False, "node not found"
    except Exception as e:
        return False, str(e)
    finally:
        try: os.unlink(tmp)
        except: pass


def check_java(code: str) -> tuple[bool, str]:
    import re
    m = re.search(r'(?:public\s+)?class\s+(\w+)', code)
    class_name = m.group(1) if m else "TranspiledCode"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, f"{class_name}.java")
        open(p, "w", encoding="utf-8").write(code)
        try:
            r = subprocess.run(["javac", p],
                               capture_output=True, timeout=15, text=True)
            if r.returncode == 0:
                return True, ""
            err = next((l for l in r.stderr.splitlines()
                        if "error:" in l), r.stderr[:200])
            return False, err
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except FileNotFoundError:
            return False, "javac not found"
        except Exception as e:
            return False, str(e)


def check_c(code: str) -> tuple[bool, str]:
    return _gcc_check(code, "gcc", ".c")


def check_cpp(code: str) -> tuple[bool, str]:
    return _gcc_check(code, "g++", ".cpp")


def _gcc_check(code: str, compiler: str, ext: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(suffix=ext, mode="w",
                                     delete=False, encoding="utf-8") as f:
        f.write(code)
        src = f.name
    try:
        r = subprocess.run([compiler, "-fsyntax-only", "-w", src],
                           capture_output=True, timeout=10, text=True)
        if r.returncode == 0:
            return True, ""
        err = next((l for l in r.stderr.splitlines()
                    if "error:" in l), r.stderr[:200])
        return False, err
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except FileNotFoundError:
        return False, f"{compiler} not found"
    except Exception as e:
        return False, str(e)
    finally:
        try: os.unlink(src)
        except: pass


CHECKERS = {
    "Python":     check_python,
    "JavaScript": check_javascript,
    "Java":       check_java,
    "C":          check_c,
    "C++":        check_cpp,
}


# ── Parallel worker ───────────────────────────────────────────────────────────

def _check_one(args):
    """Worker function: (lang, code) → (ok, err_msg)"""
    lang, code = args
    checker = CHECKERS.get(lang)
    if checker is None:
        return False, f"unsupported language: {lang}"
    return checker(code)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Source code compilation audit")
    parser.add_argument("--input",   required=True,
                        help="Directory with input JSONL chunk files")
    parser.add_argument("--samples", type=int, default=200,
                        help="Max samples per language to check (0 = all)")
    parser.add_argument("--pattern", default="chunk_*.jsonl",
                        help="Glob pattern for chunk files")
    parser.add_argument("--workers", type=int, default=16,
                        help="Number of parallel workers per language")
    args = parser.parse_args()

    in_dir = Path(args.input)
    chunk_files = sorted(in_dir.glob(args.pattern))
    if not chunk_files:
        print(f"No files found matching '{args.pattern}' in {in_dir}")
        sys.exit(1)

    print(f"Found {len(chunk_files)} chunk files in {in_dir}")
    if args.samples:
        print(f"Sampling up to {args.samples} rows per language")
    else:
        print("Full audit — all rows")
    print(f"Workers: {args.workers}")
    print("=" * 60)

    # ── Collect samples per language (deduplicated) ───────────────────────
    samples: dict[str, list[str]] = defaultdict(list)
    seen: set[tuple[str, int]] = set()   # (lang, hash) to avoid duplicate source files

    for chunk_path in chunk_files:
        with open(chunk_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue

                lang = row.get("language") or row.get("source_lang", "")
                code = row.get("content", "")

                if not lang or not code:
                    continue
                if lang not in CHECKERS:
                    continue
                if args.samples and len(samples[lang]) >= args.samples:
                    continue

                # Deduplicate: skip if we've already queued this exact file
                key = (lang, hash(code))
                if key in seen:
                    continue
                seen.add(key)

                samples[lang].append(code)

        # Stop early once all languages are saturated
        if args.samples and all(
            len(samples[l]) >= args.samples for l in CHECKERS
        ):
            break

    if not samples:
        print("No rows found — check column names (need 'language'/'source_lang' + 'content')")
        sys.exit(1)

    # ── Run parallel compilation per language ─────────────────────────────
    print(f"\n{'Language':<15} {'Total':>7} {'OK':>7} {'Fail':>7} {'Error %':>9}  Throughput")
    print("-" * 70)

    error_buckets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for lang, codes in sorted(samples.items()):
        t0  = time.time()
        ok  = 0
        fail = 0

        # Submit all codes for this language in parallel
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_check_one, (lang, code)): code
                       for code in codes}
            for fut in as_completed(futures):
                try:
                    success, err_msg = fut.result()
                except Exception as e:
                    success, err_msg = False, str(e)

                if success:
                    ok += 1
                else:
                    fail += 1
                    # Bucket the error
                    if "error:" in err_msg:
                        bucket = err_msg.split("error:")[-1].strip()[:60]
                    elif "SyntaxError" in err_msg:
                        bucket = err_msg.split(":")[0].strip()[:60]
                    else:
                        bucket = err_msg.strip()[:60]
                    error_buckets[lang][bucket] += 1

        elapsed = time.time() - t0
        total   = ok + fail
        err_pct = 100 * fail / total if total else 0
        tput    = total / elapsed if elapsed > 0 else 0
        print(f"{lang:<15} {total:>7} {ok:>7} {fail:>7}  {err_pct:>7.1f}%   {tput:.1f} rows/s")

    # ── Top errors per language ───────────────────────────────────────────
    print("\n")
    for lang, buckets in sorted(error_buckets.items()):
        if not buckets:
            continue
        print(f"Top errors in {lang} source code:")
        for msg, count in sorted(buckets.items(), key=lambda x: -x[1])[:8]:
            print(f"  [{count:4d}] {msg}")
        print()


if __name__ == "__main__":
    main()
