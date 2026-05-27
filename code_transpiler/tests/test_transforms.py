"""tests/test_transforms.py — validates all Stage 4 transform passes"""
import sys, ast
sys.path.insert(0, ".")
from pipeline.registry import build_registry
from pipeline.runner import PipelineRunner

runner = PipelineRunner(build_registry())
passed = failed = 0


def check(title, code, src_lang, tgt_lang, must_contain=(), must_not_contain=()):
    global passed, failed
    r = runner.transpile(code, src_lang, tgt_lang)
    out = r.transpiled_code or ""
    ok = True
    for s in must_contain:
        if s not in out:
            print(f"  MISSING '{s}'")
            ok = False
    for s in must_not_contain:
        if s in out:
            print(f"  SHOULD NOT CONTAIN '{s}'")
            ok = False
    if not r.transpile_success:
        print(f"  PIPELINE FAILED: {r.transpile_error}")
        ok = False
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {title}")
    if not ok:
        print(f"  Output:\n{out[:300]}")
    passed += ok
    failed += (not ok)


print("=" * 60)
print("Stage 4 Transform Tests")
print("=" * 60)

# Pass 1: range() -> ForLoop
check(
    "range(n) -> for(int i=0;i<n;i+=1)",
    "for i in range(10):\n    print(i)\n",
    "Python", "C",
    must_contain=["for (int i = 0", "i < 10", "i += 1"],
    must_not_contain=["range(10)"],
)

check(
    "range(start,stop) -> for with start",
    "for i in range(5, 15):\n    print(i)\n",
    "Python", "C",
    must_contain=["for (int i = 5", "i < 15"],
)

check(
    "range(start,stop,step) -> for with step",
    "for i in range(0, 20, 2):\n    print(i)\n",
    "Python", "C",
    must_contain=["for (int i = 0", "i < 20", "i += 2"],
)

# Pass 2: input() -> scanf
check(
    "input() -> printf + char buf + scanf",
    'name = input("Enter: ")\nprint(name)\n',
    "Python", "C",
    must_contain=["printf", "char name", "scanf", "%s"],
    must_not_contain=["= input("],
)

# Pass 3: string methods -> C helpers
check(
    "s.lower() -> str_lower(s)",
    's = "hello"\nr = s.lower()\n',
    "Python", "C",
    must_contain=["str_lower(s)"],
    must_not_contain=["s.lower()"],
)

check(
    "s.replace(a,b) -> str_replace(s,a,b)",
    's = "hi"\nr = s.replace("h", "H")\n',
    "Python", "C",
    must_contain=["str_replace(s"],
    must_not_contain=[".replace("],
)

check(
    "s.upper() -> str_upper(s)",
    's = "hi"\nr = s.upper()\n',
    "Python", "C",
    must_contain=["str_upper(s)"],
)

# Pass 4: Java type cleanup for Python target
check(
    "String[] param -> no annotation",
    "def main(args, count):\n    pass\n",
    "Python", "Python",
    must_not_contain=["String[]"],
)

print("=" * 60)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 60)
