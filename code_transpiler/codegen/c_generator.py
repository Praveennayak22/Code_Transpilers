"""
codegen/c_generator.py
======================
Generates C source code from Canonical IR.

Key differences:
- All variables must have explicit types
- No classes (procedural only)
- printf() instead of print()
- NULL instead of null/None
- Explicit main() function wrapper
- No garbage collection (manual memory)
- Arrays are fixed-size
"""

from __future__ import annotations
from typing import Optional
from ir.nodes import *
from codegen.base_generator import BaseGenerator


PYTHON_TO_C_TYPE = {
    "int": "int", "float": "double", "str": "char*",
    "bool": "int", "None": "void", "list": "int*",
    "string": "char*",
}


def _c_type(t: Optional[str]) -> str:
    if t is None:
        return "int"
    return PYTHON_TO_C_TYPE.get(t, t)


class CGenerator(BaseGenerator):
    LANGUAGE_NAME = "C"
    STMT_TERMINATOR = ";"
    BLOCK_OPEN = "{"
    BLOCK_CLOSE = "}"
    NULL_LITERAL = "NULL"
    TRUE_LITERAL = "1"
    FALSE_LITERAL = "0"
    AND_OP = "&&"
    OR_OP = "||"
    NOT_OP = "!"
    EQ_OP = "=="
    NEQ_OP = "!="

    def generate_Module(self, node: Module) -> None:
        self._write("#include <stdio.h>")
        self._write("#include <stdlib.h>")
        self._write("#include <string.h>")
        self._blank()
        # Generate all function definitions
        for stmt in node.body:
            if isinstance(stmt, FunctionDef):
                self._gen(stmt)
                self._blank()
        # Generate main() if no main exists
        has_main = any(
            isinstance(s, FunctionDef) and s.name == "main"
            for s in node.body
        )
        if not has_main:
            non_funcs = [s for s in node.body if not isinstance(s, FunctionDef)]
            if non_funcs:
                self._write("int main() {")
                self._indent()
                for stmt in non_funcs:
                    self._gen(stmt)
                self._write("return 0;")
                self._dedent()
                self._write("}")

    def _format_param(self, param: Param) -> str:
        c_type = _c_type(param.type_annotation)
        return f"{c_type} {param.name}"

    def _format_return_type(self, return_type: Optional[str]) -> str:
        return _c_type(return_type) if return_type else "void"

    def _format_function_signature(self, node: FunctionDef,
                                    params_str: str, ret: str) -> str:
        params_str = params_str or "void"
        return f"{ret} {node.name}({params_str}) {{"

    def generate_FunctionDef(self, node: FunctionDef) -> None:
        params_str = self._gen_params(node.params)
        ret = self._format_return_type(node.return_type)
        params_str = params_str or "void"
        self._write(f"{ret} {node.name}({params_str}) {{")
        self._indent()
        if not node.body:
            pass
        else:
            self._gen_body(node.body)
        self._dedent()
        self._write("}")

    def generate_ClassDef(self, node: ClassDef) -> None:
        # C has no classes — generate as a struct
        self._write(f"typedef struct {{")
        self._indent()
        for stmt in node.body:
            if isinstance(stmt, FunctionDef):
                continue  # Skip methods (C structs can't have methods)
            self._gen(stmt)
        self._dedent()
        self._write(f"}} {node.name};")

    def generate_Assignment(self, node: Assignment) -> None:
        target = self._gen_expr(node.target)
        value = self._gen_expr(node.value)
        if node.type_annotation:
            c_type = _c_type(node.type_annotation)
            self._write(f"{c_type} {target} = {value};")
        else:
            self._write(f"{target} = {value};")

    def generate_VarDecl(self, node: VarDecl) -> None:
        c_type = _c_type(node.type_annotation)
        const = "const " if node.is_const else ""
        val = f" = {self._gen_expr(node.value)}" if node.value else ""
        self._write(f"{const}{c_type} {node.name}{val};")

    def generate_IfStmt(self, node: IfStmt) -> None:
        self._write(f"if ({self._gen_expr(node.condition)}) {{")
        self._indent()
        self._gen_body(node.then_body)
        self._dedent()
        self._write("}")
        for elif_clause in node.elif_clauses:
            self._write(f"else if ({self._gen_expr(elif_clause.condition)}) {{")
            self._indent()
            self._gen_body(elif_clause.body)
            self._dedent()
            self._write("}")
        if node.else_body:
            self._write("else {")
            self._indent()
            self._gen_body(node.else_body)
            self._dedent()
            self._write("}")

    def generate_WhileLoop(self, node: WhileLoop) -> None:
        self._write(f"while ({self._gen_expr(node.condition)}) {{")
        self._indent()
        self._gen_body(node.body)
        self._dedent()
        self._write("}")

    def generate_ForEachLoop(self, node: ForEachLoop) -> None:
        # C has no for-each — emit an index loop with a size comment
        iterable = self._gen_expr(node.iterable)
        tgt_type = node.target_type or "int"
        c_tgt_type = _c_type(tgt_type)
        # Use _n_{iterable} as the size variable (caller must set it)
        size_var = f"_n_{node.target}"
        self._write(f"/* for each {node.target} in {iterable}: set {size_var} = length */")
        self._write(f"for (size_t _i = 0; _i < {size_var}; _i++) {{")
        self._indent()
        self._write(f"{c_tgt_type} {node.target} = {iterable}[_i];")
        self._gen_body(node.body)
        self._dedent()
        self._write("}")

    def generate_ForLoop(self, node: ForLoop) -> None:
        init = self._for_init(node.init)   if node.init else ""
        cond = self._gen_expr(node.condition) if node.condition else ""
        upd  = self._for_update(node.update) if node.update else ""
        self._write(f"for ({init}; {cond}; {upd}) {{")
        self._indent()
        self._gen_body(node.body)
        self._dedent()
        self._write("}")

    def _for_init(self, node) -> str:
        """Render ForLoop init: VarDecl -> 'int x = 0', else use expr."""
        if isinstance(node, VarDecl):
            c_type = _c_type(node.type_annotation)
            val = f" = {self._gen_expr(node.value)}" if node.value else ""
            return f"{c_type} {node.name}{val}"
        if isinstance(node, Assignment):
            target = self._gen_expr(node.target)
            value  = self._gen_expr(node.value)
            return f"{target} = {value}"
        return self._gen_expr(node)

    def _for_update(self, node) -> str:
        """Render ForLoop update: AugAssignment -> 'x += 1', else use expr."""
        if isinstance(node, AugAssignment):
            target = self._gen_expr(node.target)
            value  = self._gen_expr(node.value)
            return f"{target} {node.op} {value}"
        if isinstance(node, Assignment):
            target = self._gen_expr(node.target)
            value  = self._gen_expr(node.value)
            return f"{target} = {value}"
        return self._gen_expr(node)



    def generate_PrintStmt(self, node: PrintStmt) -> None:
        if not node.args:
            self._write('printf("\\n");')
            return
        if len(node.args) == 1:
            arg = node.args[0]
            if isinstance(arg, Literal):
                if arg.kind == "string":
                    self._write(f'printf("%s\\n", {self._gen_expr(arg)});')
                elif arg.kind == "int":
                    self._write(f'printf("%d\\n", {self._gen_expr(arg)});')
                elif arg.kind == "float":
                    self._write(f'printf("%f\\n", {self._gen_expr(arg)});')
                else:
                    self._write(f'printf("%s\\n", {self._gen_expr(arg)});')
            else:
                self._write(f'printf("%d\\n", {self._gen_expr(arg)});')
        else:
            args_str = ", ".join(self._gen_expr(a) for a in node.args)
            self._write(f'printf("{" ".join(["%s"] * len(node.args))}\\n", {args_str});')

    def generate_Return(self, node: Return) -> None:
        if node.value:
            self._write(f"return {self._gen_expr(node.value)};")
        else:
            self._write("return;")

    def generate_Break(self, node: Break) -> None:
        self._write("break;")

    def generate_Continue(self, node: Continue) -> None:
        self._write("continue;")

    def generate_ExprStmt(self, node: ExprStmt) -> None:
        self._write(f"{self._gen_expr(node.expr)};")

    def generate_AugAssignment(self, node: AugAssignment) -> None:
        target = self._gen_expr(node.target)
        value = self._gen_expr(node.value)
        self._write(f"{target} {node.op} {value};")

    def generate_TryExcept(self, node: TryExcept) -> None:
        # C has no exceptions — emit a comment
        self._write("/* try/except not supported in C */")
        self._gen_body(node.try_body)

    def generate_Raise(self, node: Raise) -> None:
        self._write('fprintf(stderr, "Error raised\\n");')
        self._write("exit(1);")

    def generate_Import(self, node: Import) -> None:
        self._write(f"/* import {node.module} */")

    def generate_Assert(self, node: Assert) -> None:
        cond = self._gen_expr(node.condition)
        self._write(f"assert({cond});")

    # ── Expressions ───────────────────────────────────────────────────────

    def expr_Ternary(self, node: Ternary) -> str:
        cond = self._gen_expr(node.condition)
        tv = self._gen_expr(node.true_value)
        fv = self._gen_expr(node.false_value)
        return f"({cond} ? {tv} : {fv})"

    def expr_ListLiteral(self, node: ListLiteral) -> str:
        elems = ", ".join(self._gen_expr(e) for e in node.elements)
        return "{" + elems + "}"

    def expr_ListComp(self, node: ListComp) -> str:
        return "/* list comprehension not supported in C */"

    def expr_Lambda(self, node: Lambda) -> str:
        return "/* lambda not supported in C */"

    def expr_BinaryOp(self, node: BinaryOp) -> str:
        if node.op == "**":
            left = self._gen_expr(node.left)
            right = self._gen_expr(node.right)
            return f"pow({left}, {right})"
        left = self._gen_expr(node.left)
        right = self._gen_expr(node.right)
        return f"({left} {node.op} {right})"
