import sys
sys.path.insert(0, '.')
from pipeline.registry import build_registry
from pipeline.runner import PipelineRunner

r = PipelineRunner(build_registry())

tests = [
    ('Python', 'Java',       'def add(a, b):\n    print(a + b)\n    return a + b\n'),
    ('Python', 'JavaScript', 'def greet(name):\n    print("Hello", name)\n    x = 5\n'),
    ('JavaScript', 'Python', 'function foo() {\n    console.log("hi");\n}\n'),
    ('Python', 'C',          'import math\ndef area(r):\n    return math.sqrt(r)\n'),
    ('Python', 'C++',        'def add(a, b):\n    for i in range(5):\n        print(i)\n    return a+b\n'),
    ('C++',    'Python',     '#include <iostream>\nusing namespace std;\nint main(){\n    cout<<"hi"<<endl;\n    return 0;\n}\n'),
]

print("Pair                   canonical==transformed   Success")
print('-' * 58)
for src, tgt, code in tests:
    res = r.transpile(code, src, tgt)
    same = res.canonical_ir_repr == res.transformed_ir_repr
    label = "SAME(BAD)" if same else "DIFFERENT(GOOD)"
    status = "OK" if res.transpile_success else "FAIL"
    print(f"{src}->{tgt:<15}  {label:<22}  {status}")
    if not res.transpile_success:
        print(f"   Error: {str(res.transpile_error)[:100]}")
    else:
        print(f"   Output: {res.transpiled_code[:80].strip()}")
