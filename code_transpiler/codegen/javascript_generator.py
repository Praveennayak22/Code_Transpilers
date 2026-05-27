"""
codegen/javascript_generator.py
================================
Generates JavaScript source code from Canonical IR.

Key differences from base:
- Uses `let` / `const` for declarations
- No type annotations
- console.log() for print
- `===` and `!==` for equality
- Arrow functions for lambdas
- Array.from() for list comprehensions
"""

from __future__ import annotations
from typing import Optional, List
from ir.nodes import *
from codegen.base_generator import BaseGenerator


class JavaScriptGenerator(BaseGenerator):
    LANGUAGE_NAME = "JavaScript"
    STMT_TERMINATOR = ";"
    BLOCK_OPEN = "{"
    BLOCK_CLOSE = "}"
    NULL_LITERAL = "null"
    TRUE_LITERAL = "true"
    FALSE_LITERAL = "false"
    AND_OP = "&&"
    OR_OP = "||"
    NOT_OP = "!"
    EQ_OP = "==="
    NEQ_OP = "!=="

    def generate_Module(self, node: Module) -> None:
        for stmt in node.body:
            self._gen(stmt)
            self._blank()

    def _format_function_signature(self, node: FunctionDef,
                                    params_str: str, ret: str) -> str:
        async_kw = "async " if node.is_async else ""
        return f"{async_kw}function {node.name}({params_str}) {{"

    def generate_FunctionDef(self, node: FunctionDef) -> None:
        params_str = self._gen_params(node.params)
        async_kw = "async " if node.is_async else ""
        self._write(f"{async_kw}function {node.name}({params_str}) {{")
        self._indent()
        self._gen_body(node.body)
        self._dedent()
        self._write("}")

    def generate_ClassDef(self, node: ClassDef) -> None:
        extends = f" extends {node.bases[0]}" if node.bases else ""
        self._write(f"class {node.name}{extends} {{")
        self._indent()
        self._gen_body(node.body)
        self._dedent()
        self._write("}")

    def generate_Assignment(self, node: Assignment) -> None:
        target = self._gen_expr(node.target)
        value = self._gen_expr(node.value)
        self._write(f"let {target} = {value};")

    def generate_VarDecl(self, node: VarDecl) -> None:
        kw = "const" if node.is_const else "let"
        val = f" = {self._gen_expr(node.value)}" if node.value else ""
        self._write(f"{kw} {node.name}{val};")

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
        iterable = self._gen_expr(node.iterable)
        self._write(f"for (let {node.target} of {iterable}) {{")
        self._indent()
        self._gen_body(node.body)
        self._dedent()
        self._write("}")

    def generate_ForLoop(self, node: ForLoop) -> None:
        init = self._gen_expr(node.init) if node.init else ""
        cond = self._gen_expr(node.condition) if node.condition else ""
        upd = self._gen_expr(node.update) if node.update else ""
        self._write(f"for ({init}; {cond}; {upd}) {{")
        self._indent()
        self._gen_body(node.body)
        self._dedent()
        self._write("}")

    def generate_PrintStmt(self, node: PrintStmt) -> None:
        args = ", ".join(self._gen_expr(a) for a in node.args)
        self._write(f"console.log({args});")

    def generate_TryExcept(self, node: TryExcept) -> None:
        self._write("try {")
        self._indent()
        self._gen_body(node.try_body)
        self._dedent()
        self._write("}")
        if node.handlers:
            name = node.handlers[0].name or "e"
            self._write(f"catch ({name}) {{")
            self._indent()
            self._gen_body(node.handlers[0].body)
            self._dedent()
            self._write("}")
        if node.finally_body:
            self._write("finally {")
            self._indent()
            self._gen_body(node.finally_body)
            self._dedent()
            self._write("}")

    def generate_Raise(self, node: Raise) -> None:
        exc = self._gen_expr(node.exception) if node.exception else "new Error()"
        self._write(f"throw {exc};")

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

    def generate_Import(self, node: Import) -> None:
        if node.names:
            names = ", ".join(node.names)
            self._write(f"import {{ {names} }} from '{node.module}';")
        elif node.module:
            alias = node.alias or node.module.split(".")[-1]
            self._write(f"import {alias} from '{node.module}';")

    def generate_AugAssignment(self, node: AugAssignment) -> None:
        target = self._gen_expr(node.target)
        value = self._gen_expr(node.value)
        self._write(f"{target} {node.op} {value};")

    # ── Expressions ───────────────────────────────────────────────────────

    def expr_Ternary(self, node: Ternary) -> str:
        cond = self._gen_expr(node.condition)
        tv = self._gen_expr(node.true_value)
        fv = self._gen_expr(node.false_value)
        return f"({cond} ? {tv} : {fv})"

    def expr_Lambda(self, node: Lambda) -> str:
        params = ", ".join(p.name for p in node.params)
        body = self._gen_expr(node.body)
        return f"({params}) => {body}"

    def expr_ListComp(self, node: ListComp) -> str:
        iterable = self._gen_expr(node.iterable)
        element = self._gen_expr(node.element)
        if node.condition:
            cond = self._gen_expr(node.condition)
            return (f"{iterable}.filter(({node.target}) => {cond})"
                    f".map(({node.target}) => {element})")
        return f"{iterable}.map(({node.target}) => {element})"

    def expr_TupleLiteral(self, node: TupleLiteral) -> str:
        elems = ", ".join(self._gen_expr(e) for e in node.elements)
        return f"[{elems}]"

    def _map_compare_op(self, op: str) -> str:
        return {"==": "===", "!=": "!=="}.get(op, op)
