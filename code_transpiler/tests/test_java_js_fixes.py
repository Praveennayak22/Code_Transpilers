import sys; sys.path.insert(0,'.')
from pipeline.registry import build_registry
from pipeline.runner import PipelineRunner

r = PipelineRunner(build_registry())

# --- JAVA TESTS ---
# Test 1: self + __init__ + docstring in Java
code_java1 = (
    "class Menu:\n"
    "    \"Module for menu.\"\n"
    "    def __init__(self, master, GV):\n"
    "        self.master = master\n"
    "        self.GV = GV\n"
    "    def create_menu(self):\n"
    "        print('menu created')\n"
)

# Test 2: variable named char (also Java keyword)
code_java2 = (
    "def histogram(text, keyword, char, value):\n"
    "    for key in keyword:\n"
    "        char.append(key)\n"
    "        value.append(text.count(key))\n"
)

# Test 3: source has a main() function - should not duplicate
code_java3 = (
    "def helper(x):\n"
    "    return x * 2\n"
    "def main():\n"
    "    print(helper(5))\n"
)

print("="*60)
print("JAVA TESTS")
print("="*60)
for code, label in [(code_java1,'OOP+docstring+self'), (code_java2,'keyword char'), (code_java3,'no duplicate main')]:
    res = r.transpile(code, 'Python', 'Java')
    print(f'--- {label} ---')
    if res.transpile_success:
        print(res.transpiled_code[:500])
    else:
        print('FAIL:', res.transpile_error[:150])
    print()

# --- JAVASCRIPT TESTS ---
code_js1 = (
    "class Menu:\n"
    "    \"Module for menu.\"\n"
    "    def __init__(self, master):\n"
    "        self.master = master\n"
    "    def show(self):\n"
    "        print('shown')\n"
)

code_js2 = (
    "def greet(name):\n"
    "    x = 5\n"
    "    print('Hello', name)\n"
    "    return x\n"
)

print("="*60)
print("JAVASCRIPT TESTS")
print("="*60)
for code, label in [(code_js1,'OOP+docstring+class methods'), (code_js2,'function + let')]:
    res = r.transpile(code, 'Python', 'JavaScript')
    print(f'--- {label} ---')
    if res.transpile_success:
        print(res.transpiled_code[:500])
    else:
        print('FAIL:', res.transpile_error[:150])
    print()
