"""
tests/test_pipeline.py
=======================
Quick end-to-end test of the transpiler pipeline.
Run locally with: python tests/test_pipeline.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.registry import build_registry
from pipeline.runner import PipelineRunner

registry = build_registry()
runner   = PipelineRunner(registry)

TESTS = [
    # (source_lang, target_lang, source_code)
    ("Python", "Java", """
def add(a, b):
    return a + b

def greet(name):
    print("Hello, " + name)
"""),
    ("Python", "JavaScript", """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
"""),
    ("Python", "C", """
def sum_list(numbers):
    total = 0
    for n in numbers:
        total += n
    return total
"""),
    ("Python", "C++", """
def is_even(n):
    if n % 2 == 0:
        return True
    return False
"""),
]


def test_all():
    print("="*60)
    print("Running end-to-end pipeline tests")
    print("="*60)
    passed = 0
    failed = 0
    for i, (src, tgt, code) in enumerate(TESTS):
        result = runner.transpile(code.strip(), src, tgt)
        status = "PASS" if result.transpile_success else "FAIL"
        print(f"\n[Test {i+1}] {src} -> {tgt}  {status}  ({result.transpile_time_ms}ms)")
        if result.transpile_success:
            print("--- Output ---")
            print(result.transpiled_code[:500])
            passed += 1
        else:
            print(f"Error: {result.transpile_error}")
            print(f"Stage: {result.transpile_stage}")
            failed += 1
    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)
    return failed == 0


if __name__ == "__main__":
    ok = test_all()
    sys.exit(0 if ok else 1)
