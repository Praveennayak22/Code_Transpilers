#!/usr/bin/env python3
"""
Error Analysis Script - Phase 2
Analyzes compilation errors by stage to identify root causes.

Runs Stages 1-5 only (no LLM repair) to categorize where failures occur.
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
import re

# Error categorization patterns
ERROR_PATTERNS = {
    'parsing': {
        'patterns': [
            r'SyntaxError',
            r'IndentationError',
            r'Unexpected indent',
            r'expected an indented block',
            r'invalid syntax',
            r'Unclosed string',
            r'EOFError',
        ],
        'stage': 'Stage 2: Parse',
        'description': 'Source code parsing failed'
    },
    'lifting': {
        'patterns': [
            r'AttributeError.*value',
            r'AttributeError.*body',
            r'TypeError.*IR',
            r'KeyError.*node',
            r'lifting failed',
            r'Cannot lift',
        ],
        'stage': 'Stage 3: Lift',
        'description': 'CST to Canonical IR conversion failed'
    },
    'transform': {
        'patterns': [
            r'Transform.*error',
            r'Semantic transformation',
            r'Transform failed',
            r'Unknown transform',
        ],
        'stage': 'Stage 4: Transform',
        'description': 'Semantic rewriting in IR failed'
    },
    'generation': {
        'patterns': [
            r'Generation failed',
            r'Cannot generate',
            r'Unsupported syntax',
            r'Generate.*error',
        ],
        'stage': 'Stage 5: Generate',
        'description': 'IR to target language generation failed'
    },
    'compilation': {
        'patterns': [
            r'NameError',
            r'ImportError',
            r'ModuleNotFoundError',
            r'AttributeError',
            r'TypeError',
            r'SyntaxError.*\(not in Python 2\)',
            r'IndentationError',
            r'undefined reference',
            r'no suitable constructor',
            r'cannot find symbol',
        ],
        'stage': 'Post-Generation: Compilation',
        'description': 'Generated code does not compile (semantic/library errors)'
    }
}

def classify_error(error_message):
    """Classify error by pattern matching."""
    if not error_message:
        return 'unknown'
    
    error_lower = error_message.lower()
    
    for category, config in ERROR_PATTERNS.items():
        for pattern in config['patterns']:
            if re.search(pattern, error_message, re.IGNORECASE):
                return category
    
    return 'unclassified'

def analyze_output_files(output_dir):
    """Analyze output files and categorize errors."""
    
    errors = defaultdict(lambda: {
        'count': 0,
        'examples': [],
        'files': [],
        'languages': defaultdict(int)
    })
    
    stats = {
        'total_rows': 0,
        'transpile_success': 0,
        'transpile_failed': 0,
        'compilation_success': 0,
        'compilation_failed': 0,
        'repair_attempted': 0,
        'repair_success': 0,
        'errors_by_category': errors,
        'errors_by_language_pair': defaultdict(lambda: defaultdict(int)),
        'language_pair_stats': defaultdict(lambda: {
            'total': 0,
            'transpile_success': 0,
            'compilation_success': 0,
            'failed_by_type': defaultdict(int)
        })
    }
    
    if not os.path.exists(output_dir):
        print(f"ERROR: Output directory not found: {output_dir}")
        return None
    
    output_files = sorted(Path(output_dir).glob("out_*.jsonl"))
    print(f"Analyzing {len(output_files)} output files\n")
    
    if not output_files:
        print("WARNING: No output files found!")
        return None
    
    for file_path in output_files:
        with open(file_path) as f:
            for line_num, line in enumerate(f, 1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    print(f"ERROR: Invalid JSON in {file_path}:{line_num}")
                    continue
                
                stats['total_rows'] += 1
                lang_pair = row.get('language_pair', 'unknown')
                stats['language_pair_stats'][lang_pair]['total'] += 1
                
                # Check transpilation success
                if row.get('transpile_success', False):
                    stats['transpile_success'] += 1
                    stats['language_pair_stats'][lang_pair]['transpile_success'] += 1
                else:
                    stats['transpile_failed'] += 1
                    error_msg = row.get('error_message', 'Unknown transpile error')
                    error_type = classify_error(error_msg)
                    errors[error_type]['count'] += 1
                    errors[error_type]['files'].append(str(file_path.name))
                    errors[error_type]['languages'][lang_pair] += 1
                    stats['language_pair_stats'][lang_pair]['failed_by_type'][error_type] += 1
                    
                    if len(errors[error_type]['examples']) < 3:
                        errors[error_type]['examples'].append({
                            'file': file_path.name,
                            'error': error_msg[:200]
                        })
                    continue
                
                # Check compilation success (post-generation)
                if row.get('compilation_failed', False):
                    stats['compilation_failed'] += 1
                    error_msg = row.get('error_message', 'Compilation error')
                    error_type = classify_error(error_msg)
                    errors[error_type]['count'] += 1
                    errors[error_type]['files'].append(str(file_path.name))
                    errors[error_type]['languages'][lang_pair] += 1
                    stats['language_pair_stats'][lang_pair]['failed_by_type'][error_type] += 1
                    
                    if len(errors[error_type]['examples']) < 3:
                        errors[error_type]['examples'].append({
                            'file': file_path.name,
                            'error': error_msg[:200]
                        })
                else:
                    stats['compilation_success'] += 1
                    stats['language_pair_stats'][lang_pair]['compilation_success'] += 1
                
                # Track LLM repair
                if row.get('repair_attempted', False):
                    stats['repair_attempted'] += 1
                    if row.get('repair_success', False):
                        stats['repair_success'] += 1
    
    return stats

def print_report(stats):
    """Print comprehensive error analysis report."""
    
    if not stats:
        return
    
    print("\n" + "="*80)
    print("ERROR ANALYSIS REPORT - Phase 2 (Stages 1-5 Analysis)")
    print("="*80)
    
    print(f"\nOVERALL STATISTICS")
    print(f"  Total rows analyzed:        {stats['total_rows']:,}")
    print(f"  Transpilation success:      {stats['transpile_success']:,} ({100*stats['transpile_success']/max(stats['total_rows'],1):.1f}%)")
    print(f"  Transpilation failures:     {stats['transpile_failed']:,} ({100*stats['transpile_failed']/max(stats['total_rows'],1):.1f}%)")
    print(f"  Compilation success:        {stats['compilation_success']:,}")
    print(f"  Compilation failures:       {stats['compilation_failed']:,}")
    
    if stats['compilation_failed'] > 0:
        print(f"  Compilation failure rate:   {100*stats['compilation_failed']/(stats['compilation_success']+stats['compilation_failed']):.1f}%")
    
    print(f"\nLLM REPAIR (For Reference)")
    print(f"  Repair attempts:            {stats['repair_attempted']:,}")
    print(f"  Repair success:             {stats['repair_success']:,} ({100*stats['repair_success']/max(stats['repair_attempted'],1):.1f}%)")
    
    print(f"\n" + "-"*80)
    print(f"ERRORS BY CATEGORY (Root Cause Analysis)")
    print(f"-"*80)
    
    # Sort by count
    sorted_errors = sorted(
        stats['errors_by_category'].items(),
        key=lambda x: x[1]['count'],
        reverse=True
    )
    
    for error_type, error_data in sorted_errors:
        if error_data['count'] == 0:
            continue
        
        config = ERROR_PATTERNS.get(error_type, {})
        stage = config.get('stage', 'Unknown Stage')
        description = config.get('description', 'Unknown error')
        
        print(f"\n{error_type.upper()}")
        print(f"  Stage: {stage}")
        print(f"  Description: {description}")
        print(f"  Count: {error_data['count']:,} occurrences")
        print(f"  Percentage of total: {100*error_data['count']/max(stats['total_rows'],1):.1f}%")
        
        if error_data['languages']:
            print(f"  By language pair:")
            for lang_pair, count in sorted(error_data['languages'].items(), key=lambda x: x[1], reverse=True):
                print(f"    {lang_pair}: {count}")
        
        if error_data['examples']:
            print(f"  Example errors:")
            for i, example in enumerate(error_data['examples'][:3], 1):
                print(f"    {i}. [{example['file']}] {example['error'][:100]}")
    
    print(f"\n" + "-"*80)
    print(f"ERROR DISTRIBUTION BY STAGE")
    print(f"-"*80)
    
    stage_stats = defaultdict(int)
    for error_type, error_data in stats['errors_by_category'].items():
        if error_data['count'] > 0:
            config = ERROR_PATTERNS.get(error_type, {})
            stage = config.get('stage', 'Unknown')
            stage_stats[stage] += error_data['count']
    
    total_errors = sum(stage_stats.values())
    for stage in [
        'Stage 2: Parse',
        'Stage 3: Lift',
        'Stage 4: Transform',
        'Stage 5: Generate',
        'Post-Generation: Compilation'
    ]:
        count = stage_stats.get(stage, 0)
        if total_errors > 0:
            pct = 100 * count / total_errors
            print(f"  {stage:<35} {count:>6,} ({pct:>5.1f}%)")
        else:
            print(f"  {stage:<35} {count:>6,} (  0.0%)")
    
    print(f"\n" + "-"*80)
    print(f"LANGUAGE PAIR BREAKDOWN")
    print(f"-"*80)
    print(f"{'Pair':<15} {'Total':<8} {'T.Succ':<8} {'C.Succ':<8} {'C.Fail':<8} {'C.Rate':<8}")
    print(f"{'-'*15} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    
    for lang_pair in sorted(stats['language_pair_stats'].keys()):
        data = stats['language_pair_stats'][lang_pair]
        total = data['total']
        t_succ = data['transpile_success']
        c_succ = data['compilation_success']
        c_fail = data['compilation_failed']
        c_rate = 100 * c_fail / (c_succ + c_fail) if (c_succ + c_fail) > 0 else 0
        
        print(f"{lang_pair:<15} {total:<8} {t_succ:<8} {c_succ:<8} {c_fail:<8} {c_rate:>6.1f}%")
    
    print(f"\n" + "="*80 + "\n")

if __name__ == "__main__":
    output_dir = "/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/test_output_v3/chunks/"
    
    if len(sys.argv) > 1:
        output_dir = sys.argv[1]
    
    print(f"Analyzing errors from: {output_dir}\n")
    
    stats = analyze_output_files(output_dir)
    if stats:
        print_report(stats)
        
        # Save detailed report to file
        with open('error_analysis_report.json', 'w') as f:
            # Convert defaultdict to regular dict for JSON serialization
            report = {
                'total_rows': stats['total_rows'],
                'transpile_success': stats['transpile_success'],
                'transpile_failed': stats['transpile_failed'],
                'compilation_success': stats['compilation_success'],
                'compilation_failed': stats['compilation_failed'],
                'repair_attempted': stats['repair_attempted'],
                'repair_success': stats['repair_success'],
            }
            json.dump(report, f, indent=2)
        
        print(f"✓ Detailed report saved to: error_analysis_report.json")
    else:
        sys.exit(1)
