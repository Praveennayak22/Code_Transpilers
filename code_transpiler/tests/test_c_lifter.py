import sys
sys.path.insert(0, '.')
from pipeline.registry import build_registry
from pipeline.runner import PipelineRunner

r = PipelineRunner(build_registry())

# Test C -> Python
c_code = "#include <stdio.h>\n\nint add(int a, int b) {\n    return a + b;\n}\n\nint main() {\n    int x = 5;\n    int y = 10;\n    printf(\"Result: %d\", add(x, y));\n    return 0;\n}\n"

result = r.transpile(c_code, "C", "Python")
print("C -> Python success:", result.transpile_success)
print("Output:")
print(result.transpiled_code)
if result.transpile_error:
    print("Error:", result.transpile_error)

# Test C++ -> Python
cpp_code = "#include <iostream>\nusing namespace std;\n\nint factorial(int n) {\n    if (n <= 1) return 1;\n    return n * factorial(n - 1);\n}\n\nint main() {\n    cout << factorial(5) << endl;\n    return 0;\n}\n"

result2 = r.transpile(cpp_code, "C++", "Python")
print("\nC++ -> Python success:", result2.transpile_success)
print("Output:")
print(result2.transpiled_code)
if result2.transpile_error:
    print("Error:", result2.transpile_error)
