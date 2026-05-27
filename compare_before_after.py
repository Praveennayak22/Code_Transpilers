#!/usr/bin/env python3
"""
Analyze LLM repair improvement on 5,000 test files.
Compares transpilation success and compilation metrics before/after LLM repair.
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# Metrics to track
metrics = {
    'total_rows': 0,
    'total_transpiled': 0,
    'transpile_failures': 0,
    'compilation_failures_pre_repair': 0,
    'compilation_failures_post_repair': 0,
    'repair_attempted': 0,
    'repair_success': 0,
    'repair_failed': 0,
    
    # Error categorization (for debugging which stage failed)
    'error_types': defaultdict(int),  # e.g., "NameError", "TypeError", "ImportError"
    'transpile_errors': defaultdict(int),  # Errors from parsing/lifting/transform stages
    'compilation_errors': defaultdict(int),  # Errors from real compilation
    'repair_still_failed': [],  # Samples where LLM couldn't fix
    
    'by_language_pair': defaultdict(lambda: {
        'rows': 0,
        'transpiled': 0,
        'compiled_pre': 0,
        'compiled_post': 0,
        'repair_attempted': 0,
        'repair_success': 0,
        'transpile_errors_count': 0,
        'compilation_errors_count': 0,
    })
}

def analyze_output_files(output_dir):
    """Scan test output files and collect metrics."""
    
    if not os.path.exists(output_dir):
        print(f"ERROR: Output directory not found: {output_dir}")
        return False
    
    output_files = sorted(Path(output_dir).glob("out_*.jsonl"))
    print(f"Found {len(output_files)} output files")
    
    if not output_files:
        print("WARNING: No output files found!")
        return False
    
    for file_path in output_files:
        with open(file_path) as f:
            for line_num, line in enumerate(f, 1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    print(f"ERROR: Invalid JSON in {file_path}:{line_num}")
                    continue
                
                metrics['total_rows'] += 1
                
                # Language pair
                lang_pair = row.get('language_pair', 'unknown')
                metrics['by_language_pair'][lang_pair]['rows'] += 1
                
                # Transpilation status
                if row.get('transpile_success', False):
                    metrics['total_transpiled'] += 1
                    metrics['by_language_pair'][lang_pair]['transpiled'] += 1
                    
                    # Check compilation before repair
                    if row.get('compilation_failed', False):
                        metrics['compilation_failures_pre_repair'] += 1
                        metrics['by_language_pair'][lang_pair]['compiled_pre'] += 0
                    else:
                        metrics['by_language_pair'][lang_pair]['compiled_pre'] += 1
                    
                    # Check if repair was attempted
                    if row.get('repair_attempted', False):
                        metrics['repair_attempted'] += 1
                        metrics['by_language_pair'][lang_pair]['repair_attempted'] += 1
                        
                        if row.get('repair_success', False):
                            metrics['repair_success'] += 1
                            metrics['by_language_pair'][lang_pair]['repair_success'] += 1
                            metrics['by_language_pair'][lang_pair]['compiled_post'] += 1
                        else:
                            metrics['repair_failed'] += 1
                            metrics['by_language_pair'][lang_pair]['compiled_post'] += 0
                    else:
                        # No repair attempted, use pre-repair status
                        if not row.get('compilation_failed', False):
                            metrics['by_language_pair'][lang_pair]['compiled_post'] += 1
                        else:
                            metrics['compilation_failures_post_repair'] += 1
                else:
                    metrics['transpile_failures'] += 1
    
    return True

def print_report():
    """Print analysis results."""
    
    print("\n" + "="*70)
    print("LLM REPAIR IMPROVEMENT ANALYSIS (5,000 FILES)")
    print("="*70)
    
    print(f"\nOVERALL METRICS:")
    print(f"  Total rows processed:           {metrics['total_rows']:,}")
    print(f"  Successful transpilations:      {metrics['total_transpiled']:,} ({100*metrics['total_transpiled']/max(metrics['total_rows'],1):.1f}%)")
    print(f"  Transpilation failures:         {metrics['transpile_failures']:,}")
    
    print(f"\nCOMPILATION METRICS:")
    pre_failures = metrics['compilation_failures_pre_repair']
    post_failures = metrics['compilation_failures_post_repair'] + (metrics['repair_failed'] or 0)
    
    print(f"  Pre-repair compilation failures: {pre_failures:,}")
    print(f"  Post-repair compilation failures: {post_failures:,}")
    
    if pre_failures > 0:
        improvement = pre_failures - post_failures
        pct = 100 * improvement / pre_failures
        print(f"  Failures fixed by repair:        {improvement:,} ({pct:.1f}%)")
    
    print(f"\nLLM REPAIR LOOP:")
    print(f"  Repair attempts:                {metrics['repair_attempted']:,}")
    print(f"  Successful repairs:             {metrics['repair_success']:,} ({100*metrics['repair_success']/max(metrics['repair_attempted'],1):.1f}%)")
    print(f"  Failed repairs:                 {metrics['repair_failed']:,}")
    
    print(f"\nBY LANGUAGE PAIR:")
    print(f"{'Pair':<15} {'Rows':<8} {'Transpiled':<12} {'Pre-comp':<10} {'Post-comp':<10} {'Improved':<10}")
    print("-" * 70)
    
    for lang_pair in sorted(metrics['by_language_pair'].keys()):
        data = metrics['by_language_pair'][lang_pair]
        rows = data['rows']
        transpiled = data['transpiled']
        pre_comp = data['compiled_pre']
        post_comp = data['compiled_post']
        improvement = post_comp - pre_comp if pre_comp > 0 else 0
        
        pre_fail = transpiled - pre_comp
        if pre_fail > 0:
            improved_pct = 100 * improvement / pre_fail
        else:
            improved_pct = 0
        
        print(f"{lang_pair:<15} {rows:<8} {transpiled:<12} {pre_comp:<10} {post_comp:<10} {improved_pct:>8.1f}%")
    
    print("="*70 + "\n")

if __name__ == "__main__":
    output_dir = "/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/test_output_v3/chunks/"
    
    if len(sys.argv) > 1:
        output_dir = sys.argv[1]
    
    print(f"Analyzing test output from: {output_dir}")
    
    if analyze_output_files(output_dir):
        print_report()
    else:
        sys.exit(1)
