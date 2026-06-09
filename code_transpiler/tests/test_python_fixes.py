import sys; sys.path.insert(0,'.')
from pipeline.registry import build_registry
from pipeline.runner import PipelineRunner

r = PipelineRunner(build_registry())

# Test 1: C -> Python: C-style block comments + C headers + while condition
# Simulating: "while /* expr:AugAssignment */:" + "/* unsupported: BinaryOp */"
# These come from the C lifter when it encounters unsupported constructs.
# We test them from Java (which is parsed) by using a tricky input.

# Test what happens when Python target receives code with anonymous functions (Sample 2)
# We test directly using the PythonGenerator on a fake IR with empty function name
from ir.nodes import *
from codegen.python_generator import PythonGenerator

gen = PythonGenerator()

# Test 1: Anonymous function (empty name)
mod1 = Module(
    imports=[],
    body=[FunctionDef(name="", params=[], body=[Return(value=None)], return_type="None")]
)
code1 = gen.generate(mod1)
print("--- Test 1: Anonymous function ---")
print(code1)
print()

# Test 2: C/C++ header imports
mod2 = Module(
    imports=[
        Import(module="bits/stdc++.h"),
        Import(module="main.h"),
        Import(module="Human.hpp"),
        Import(module="sys/event.h"),
        Import(module="kvm.h"),
        Import(module="os"),   # valid Python — should be kept
    ],
    body=[]
)
code2 = gen.generate(mod2)
print("--- Test 2: C header imports ---")
print(code2)
print()

# Test 3: Unsupported statement → should become # comment not /* */
from ir.nodes import BinaryOp  # BinaryOp might not have generate_BinaryOp as a stmt
class FakeBadNode(CanonicalNode):  # Simulate an unsupported IR node
    pass

mod3 = Module(imports=[], body=[FakeBadNode()])
code3 = gen.generate(mod3)
print("--- Test 3: Unsupported statement ---")
print(code3)
print()

# Test 4: Check WhileLoop with unsupported condition (AugAssignment as condition)
asg = AugAssignment(target=Name(id="i"), op="+=", value=Literal(value=1, kind="int"))
mod4 = Module(imports=[], body=[WhileLoop(condition=asg, body=[Pass()])])
code4 = gen.generate(mod4)
print("--- Test 4: Unsupported while condition ---")
print(code4)
print()

# Now test full transpile from C source via normal pipeline
code_c = '''
def rgb565(r8, g8, b8):
    b5 = (b8 >> 3) & 1
    g6 = ((g8 >> 2) & 3) << 5
    return r5 | g6 | b5
'''

res = r.transpile(code_c, 'Python', 'Python')
print("--- Test 5: Python roundtrip (identity check) ---")
if res.transpile_success:
    print("compiles:", res.target_compiles)
    print(res.transpiled_code[:200])
else:
    print("FAIL:", res.transpile_error[:100])
