"""
codegen/cpp_generator.py
=========================
Generates C++ source code from Canonical IR.

Extends CGenerator — C++ is a superset of C with:
- Classes with methods
- std::cout instead of printf
- std::vector instead of arrays
- std::string instead of char*
- namespace std
- References and const references
"""

from __future__ import annotations
from typing import Optional
from ir.nodes import *
from codegen.c_generator import CGenerator, _c_type


PYTHON_TO_CPP_TYPE = {
    "int": "int", "float": "double", "str": "std::string",
    "bool": "bool", "None": "void", "list": "std::vector<int>",
    "dict": "std::map<std::string, int>",
    "set": "std::set<int>", "string": "std::string",
}


def _cpp_type(t: Optional[str]) -> str:
    if t is None:
        return "auto"
    return PYTHON_TO_CPP_TYPE.get(t, t)


class CppGenerator(CGenerator):
    LANGUAGE_NAME = "C++"
    NULL_LITERAL = "nullptr"
    TRUE_LITERAL = "true"
    FALSE_LITERAL = "false"

    def generate_Module(self, node: Module) -> None:
        hardcoded = {"iostream", "vector", "string", "map", "cmath"}
        self._write("#include <iostream>")
        self._write("#include <vector>")
        self._write("#include <string>")
        self._write("#include <map>")
        self._write("#include <cmath>")
        # Extra headers injected by transform (e.g. algorithm, set, stack)
        for imp in node.imports:
            hdr = imp.module.strip()
            if hdr and hdr not in hardcoded:
                self._write(f"#include <{hdr}>")
        self._blank()
        self._write("using namespace std;")
        self._blank()
        for stmt in node.body:
            self._gen(stmt)
            self._blank()
        # Add main() if no main function exists
        has_main = any(
            isinstance(s, FunctionDef) and s.name == "main"
            for s in node.body
        )
        if not has_main:
            # Only put simple statements (not ClassDefs) inside main()
            non_funcs = [s for s in node.body
                         if not isinstance(s, (FunctionDef, ClassDef, Comment))]
            if non_funcs:
                self._write("int main() {")
                self._indent()
                for stmt in non_funcs:
                    self._gen(stmt)
                self._write("return 0;")
                self._dedent()
                self._write("}")

    def _format_param(self, param: Param) -> str:
        cpp_type = _cpp_type(param.type_annotation)
        return f"{cpp_type} {param.name}"

    def _format_return_type(self, return_type: Optional[str]) -> str:
        return _cpp_type(return_type) if return_type else "void"

    def generate_ClassDef(self, node: ClassDef) -> None:
        # Track current class name so generate_FunctionDef can detect constructors
        self._current_class_name = node.name
        extends = f" : public {node.bases[0]}" if node.bases else ""
        self._write(f"class {node.name}{extends} {{")
        self._write("public:")
        self._indent()
        self._gen_body(node.body)
        self._dedent()
        self._write("};")  
        self._current_class_name = None

    def generate_VarDecl(self, node: VarDecl) -> None:
        cpp_type = _cpp_type(node.type_annotation)
        const = "const " if node.is_const else ""
        val = f" = {self._gen_expr(node.value)}" if node.value else ""
        self._write(f"{const}{cpp_type} {node.name}{val};")

    def generate_Assignment(self, node: Assignment) -> None:
        target = self._gen_expr(node.target)
        value = self._gen_expr(node.value)
        if node.type_annotation:
            cpp_type = _cpp_type(node.type_annotation)
            self._write(f"{cpp_type} {target} = {value};")
        else:
            self._write(f"{target} = {value};")

    def generate_PrintStmt(self, node: PrintStmt) -> None:
        if not node.args:
            self._write('cout << endl;')
            return
        parts = " << \" \" << ".join(self._gen_expr(a) for a in node.args)
        self._write(f'cout << {parts} << endl;')

    def generate_ForEachLoop(self, node: ForEachLoop) -> None:
        iterable = self._gen_expr(node.iterable)
        self._write(f"for (auto {node.target} : {iterable}) {{")
        self._indent()
        self._gen_body(node.body)
        self._dedent()
        self._write("}")

    def generate_TryExcept(self, node: TryExcept) -> None:
        self._write("try {")
        self._indent()
        self._gen_body(node.try_body)
        self._dedent()
        self._write("}")
        for handler in node.handlers:
            exc = handler.exception_type or "exception"
            name = handler.name or "e"
            self._write(f"catch (const {exc}& {name}) {{")
            self._indent()
            self._gen_body(handler.body)
            self._dedent()
            self._write("}")
        if node.finally_body:
            self._write("/* finally */")
            self._gen_body(node.finally_body)

    def generate_Raise(self, node: Raise) -> None:
        if node.exception:
            exc = self._gen_expr(node.exception)
            self._write(f"throw runtime_error({exc});")
        else:
            self._write("throw runtime_error(\"error\");")

    def generate_Import(self, node: Import) -> None:
        self._write(f"/* include: {node.module} */")

    # ── Expressions ───────────────────────────────────────────────────────

    def expr_ListLiteral(self, node: ListLiteral) -> str:
        elems = ", ".join(self._gen_expr(e) for e in node.elements)
        return "{" + elems + "}"

    # ── Constructor fix ────────────────────────────────────────────────────

    def generate_FunctionDef(self, node: FunctionDef) -> None:
        """
        Override to omit return type for C++ constructors.
        A constructor is a method whose name matches the enclosing class name.
        """
        params_str = self._gen_params(node.params)
        class_name = getattr(self, '_current_class_name', None)
        if class_name and node.name == class_name:
            # Constructor: no return type in C++
            self._write(f"{node.name}({params_str}) {{")
        else:
            ret = self._format_return_type(node.return_type)
            self._write(f"{ret} {node.name}({params_str}) {{")
        self._indent()
        self._gen_body(node.body)
        self._dedent()
        self._write("}")

    # ── this-> for self references ─────────────────────────────────────────

    def expr_Attribute(self, node: Attribute) -> str:
        """Emit this->attr when the object is the renamed _this_cpp_ref sentinel."""
        obj = self._gen_expr(node.obj)
        if obj == "_this_cpp_ref":
            return f"this->{node.attr}"
        return f"{obj}.{node.attr}"

    # ── len(x) → x.size() ─────────────────────────────────────────────────

    def expr_Call(self, node: Call) -> str:
        """Intercept len(x) → x.size() for C++."""
        if (isinstance(node.func, Name) and node.func.id == "len"
                and len(node.args) == 1):
            container = self._gen_expr(node.args[0])
            return f"{container}.size()"
        return super().expr_Call(node)

    # ── x in y → std::find ────────────────────────────────────────────────

    def expr_CompareOp(self, node: CompareOp) -> str:
        """Handle Python 'in' / 'not in' membership tests in C++ via std::find."""
        if node.op == "in":
            left = self._gen_expr(node.left)
            right = self._gen_expr(node.right)
            return (f"(std::find({right}.begin(), {right}.end(), {left})"
                    f" != {right}.end())")
        elif node.op == "not in":
            left = self._gen_expr(node.left)
            right = self._gen_expr(node.right)
            return (f"(std::find({right}.begin(), {right}.end(), {left})"
                    f" == {right}.end())")
        left = self._gen_expr(node.left)
        right = self._gen_expr(node.right)
        op = self._map_compare_op(node.op)
        return f"({left} {op} {right})"

    # ── List comprehension fallback → {} ──────────────────────────────────

    def expr_ListComp(self, node: ListComp) -> str:
        # C++ has no native list comprehensions; emit empty init so it's
        # at least syntactically valid (compiles, though semantics are lost).
        return "{}"

    def expr_BinaryOp(self, node: BinaryOp) -> str:
        if node.op == "**":
            left = self._gen_expr(node.left)
            right = self._gen_expr(node.right)
            return f"pow({left}, {right})"
        left = self._gen_expr(node.left)
        right = self._gen_expr(node.right)
        return f"({left} {node.op} {right})"

    def expr_DictLiteral(self, node: DictLiteral) -> str:
        """Emit C++ std::map initializer list."""
        if not node.keys:
            return "std::map<std::string, int>{}"
        pairs = ", ".join(
            f"{{{self._gen_expr(k)}, {self._gen_expr(v)}}}"
            for k, v in zip(node.keys, node.values)
        )
        # Infer key/value types from first pair
        first_k = node.keys[0]
        first_v = node.values[0]
        k_type = "int" if (isinstance(first_k, Literal) and first_k.kind == "int") else "std::string"
        v_type = "int" if (isinstance(first_v, Literal) and first_v.kind == "int") else "std::string"
        return f"std::map<{k_type}, {v_type}>{{{{{pairs}}}}}"
