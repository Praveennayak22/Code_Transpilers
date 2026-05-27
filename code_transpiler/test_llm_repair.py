"""
test_llm_repair.py
===================
Quick test of LLM repair loop on a few samples.

Usage:
    python3 test_llm_repair.py --target-lang C --samples 5 --use-repair
"""

import argparse
import json
from pathlib import Path
from repair_engine import RepairEngine
from compiler_check import get_checker, CompileResult


# Sample failing C code (Python transpiled to C that won't compile)
SAMPLE_BROKEN_C = """
#include <stdio.h>

int main() {
    int x = 5;
    printf("x = %d\\n", x);  // Missing variable declaration
    undefined_func();  // This function doesn't exist
    return 0;
}
"""

SAMPLE_BROKEN_JAVA = """
public class TranspiledCode {
    public static void main(String[] args) {
        int x = 5;
        System.out.println("x = " + x);
        unknownMethod();  // This method doesn't exist
    }
}
"""

SAMPLES = {
    "C": SAMPLE_BROKEN_C,
    "Java": SAMPLE_BROKEN_JAVA,
}


def test_repair_loop():
    """Test the LLM repair loop."""
    parser = argparse.ArgumentParser(description="Test LLM repair loop")
    parser.add_argument("--target-lang", default="C", choices=["C", "Java"])
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--use-repair", action="store_true")
    parser.add_argument("--llm-endpoint", default="http://soketlab-node060:30000/v1/chat/completions")
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"Testing LLM Repair Loop — {args.target_lang}")
    print(f"{'='*60}\n")
    
    if not args.use_repair:
        print("❌ Repair disabled. Use --use-repair to enable LLM repairs.\n")
        return
    
    print(f"LLM Endpoint: {args.llm_endpoint}\n")
    
    target_lang = args.target_lang
    sample_code = SAMPLES.get(target_lang, "")
    
    if not sample_code:
        print(f"No sample for {target_lang}")
        return
    
    # First check: does it compile?
    print("Step 1: Check if original code compiles...")
    checker = get_checker(target_lang)
    initial_check = checker.check(sample_code)
    
    if initial_check.success:
        print("  ✅ Code compiles! No repair needed.\n")
        return
    
    print(f"  ❌ Compilation failed!")
    print(f"  Error: {initial_check.error_message[:150]}\n")
    
    # Create repair engine
    print("Step 2: Initialize LLM repair engine...")
    engine = RepairEngine(
        llm_endpoint=args.llm_endpoint,
        max_attempts=2,
        verbose=True
    )
    print("  ✅ Ready\n")
    
    # Run repair
    print("Step 3: Attempt LLM repair...\n")
    result = engine.repair(sample_code, target_lang, source_lang="Python")
    
    # Results
    print(f"\n{'='*60}")
    print("REPAIR RESULTS")
    print(f"{'='*60}")
    print(f"Success: {result.repair_success}")
    print(f"Attempts: {result.total_attempts}")
    print(f"LLM Tokens Used: {result.llm_tokens_used}")
    print(f"Time: {result.repair_time_ms:.1f}ms")
    
    if result.repair_success:
        print(f"\n✅ FIXED CODE:\n")
        print(result.final_code[:500])
        if len(result.final_code) > 500:
            print(f"... ({len(result.final_code)} total chars)")
    else:
        print(f"\n❌ Could not fix with LLM")
        if result.repair_attempts:
            last_attempt = result.repair_attempts[-1]
            if last_attempt.compile_result:
                print(f"Last error: {last_attempt.compile_result.error_message[:200]}")
    
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    test_repair_loop()
