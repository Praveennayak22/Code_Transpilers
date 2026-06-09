import sys; sys.path.insert(0,'.')
from pipeline.registry import build_registry
from pipeline.runner import PipelineRunner

r = PipelineRunner(build_registry())

# Test 1: docstring in class + __init__ + self
code1 = (
    "class Menu:\n"
    "    \"Module for menu. Supports file loading.\"\n"
    "    def __init__(self, master, GV):\n"
    "        self.master = master\n"
    "        self.create_menu()\n"
    "    def create_menu(self):\n"
    "        print('menu created')\n"
)

# Test 2: variable named char (C keyword)
code2 = (
    "def histogram(text, keyword, char, value):\n"
    "    for key in keyword:\n"
    "        char.append(key)\n"
    "        value.append(text.count(key))\n"
)

for code, label in [(code1,'OOP+docstring+self'), (code2,'keyword rename + arr_append')]:
    res = r.transpile(code, 'Python', 'C++')
    print(f'--- {label} ---')
    if res.transpile_success:
        print(res.transpiled_code[:500])
    else:
        print('FAIL:', res.transpile_error[:150])
    print()
