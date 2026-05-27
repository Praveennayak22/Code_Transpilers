"""
codegen/python_generator.py
============================
Generates Python source code from Canonical IR.

Used when the target language is Python (Java→Python, JS→Python).

Key characteristics:
- Indentation-based blocks (no braces)
- No semicolons
- print() for output
- and/or/not for boolean ops
- None/True/False literals
"""

from __future__ import annotations
from typing import Optional, List
from ir.nodes import *
from codegen.base_generator import BaseGenerator


class PythonGenerator(BaseGenerator):
    LANGUAGE_NAME = "Python"
    STMT_TERMINATOR = ""
    BLOCK_OPEN = ":"
    BLOCK_CLOSE = ""
    NULL_LITERAL = "None"
    TRUE_LITERAL = "True"
    FALSE_LITERAL = "False"
    AND_OP = "and"
    OR_OP = "or"
    NOT_OP = "not "
    EQ_OP = "=="
    NEQ_OP = "!="

    def generate_Module(self, node: Module) -> None:
        for imp in node.imports:
            self._gen(imp)
        if node.imports:
            self._blank()
        for stmt in node.body:
            self._gen(stmt)
            self._blank()

    def _format_function_signature(self, node: FunctionDef,
                                    params_str: str, ret: str) -> str:
        ret_ann = f" -> {ret}" if ret and ret != "void" else ""
        async_kw = "async " if node.is_async else ""
        return f"{async_kw}def {node.name}({params_str}){ret_ann}:"

    def generate_FunctionDef(self, node: FunctionDef) -> None:
        params_str = self._gen_params(node.params)
        for dec in node.decorators:
            self._write(f"@{dec}")
        sig = self._format_function_signature(node, params_str, node.return_type or "")
        self._write(sig)
        self._indent()
        if not node.body:
            self._write("pass")
        else:
            self._gen_body(node.body)
        self._dedent()

    def generate_ClassDef(self, node: ClassDef) -> None:
        bases = f"({', '.join(node.bases)})" if node.bases else ""
        for dec in node.decorators:
            self._write(f"@{dec}")
        self._write(f"class {node.name}{bases}:")
        self._indent()
        if not node.body:
            self._write("pass")
        else:
            self._gen_body(node.body)
        self._dedent()

    def generate_Assignment(self, node: Assignment) -> None:
        target = self._gen_expr(node.target)
        value = self._gen_expr(node.value)
        if node.type_annotation:
            self._write(f"{target}: {node.type_annotation} = {value}")
        else:
            self._write(f"{target} = {value}")

    def generate_VarDecl(self, node: VarDecl) -> None:
        val = f" = {self._gen_expr(node.value)}" if node.value else " = None"
        if node.type_annotation:
            self._write(f"{node.name}: {node.type_annotation}{val}")
        else:
            self._write(f"{node.name}{val}")

    def generate_IfStmt(self, node: IfStmt) -> None:
        self._write(f"if {self._gen_expr(node.condition)}:")
        self._indent()
        if not node.then_body:
            self._write("pass")
        else:
            self._gen_body(node.then_body)
        self._dedent()
        for elif_clause in node.elif_clauses:
            self._write(f"elif {self._gen_expr(elif_clause.condition)}:")
            self._indent()
            self._gen_body(elif_clause.body) if elif_clause.body else self._write("pass")
            self._dedent()
        if node.else_body:
            self._write("else:")
            self._indent()
            self._gen_body(node.else_body)
            self._dedent()

    def generate_WhileLoop(self, node: WhileLoop) -> None:
        self._write(f"while {self._gen_expr(node.condition)}:")
        self._indent()
        self._gen_body(node.body) if node.body else self._write("pass")
        self._dedent()

    def generate_ForEachLoop(self, node: ForEachLoop) -> None:
        iterable = self._gen_expr(node.iterable)
        self._write(f"for {node.target} in {iterable}:")
        self._indent()
        self._gen_body(node.body) if node.body else self._write("pass")
        self._dedent()

    def generate_ForLoop(self, node: ForLoop) -> None:
        # C-style for → convert to while loop in Python
        if node.init:
            self._gen(node.init)
        cond = self._gen_expr(node.condition) if node.condition else "True"
        self._write(f"while {cond}:")
        self._indent()
        self._gen_body(node.body)
        if node.update:
            self._gen(node.update)
        self._dedent()

    def generate_PrintStmt(self, node: PrintStmt) -> None:
        args = ", ".join(self._gen_expr(a) for a in node.args)
        self._write(f"print({args})")

    def generate_TryExcept(self, node: TryExcept) -> None:
        self._write("try:")
        self._indent()
        self._gen_body(node.try_body) if node.try_body else self._write("pass")
        self._dedent()
        for handler in node.handlers:
            if handler.exception_type and handler.name:
                self._write(f"except {handler.exception_type} as {handler.name}:")
            elif handler.exception_type:
                self._write(f"except {handler.exception_type}:")
            else:
                self._write("except Exception:")
            self._indent()
            self._gen_body(handler.body) if handler.body else self._write("pass")
            self._dedent()
        if node.finally_body:
            self._write("finally:")
            self._indent()
            self._gen_body(node.finally_body)
            self._dedent()

    def generate_Raise(self, node: Raise) -> None:
        if node.exception:
            self._write(f"raise {self._gen_expr(node.exception)}")
        else:
            self._write("raise")

    def generate_Return(self, node: Return) -> None:
        if node.value:
            self._write(f"return {self._gen_expr(node.value)}")
        else:
            self._write("return")

    def generate_Break(self, node: Break) -> None:
        self._write("break")

    def generate_Continue(self, node: Continue) -> None:
        self._write("continue")

    def generate_ExprStmt(self, node: ExprStmt) -> None:
        self._write(self._gen_expr(node.expr))

    def generate_AugAssignment(self, node: AugAssignment) -> None:
        target = self._gen_expr(node.target)
        value = self._gen_expr(node.value)
        self._write(f"{target} {node.op} {value}")

    # Python keywords that are invalid as identifiers/params
    _PY_KEYWORDS = frozenset({
        "False", "None", "True", "and", "as", "assert", "async", "await",
        "break", "class", "continue", "def", "del", "elif", "else",
        "except", "finally", "for", "from", "global", "if", "import",
        "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise",
        "return", "try", "while", "with", "yield",
    })

    def generate_Import(self, node: Import) -> None:
        module = node.module or ""
        # Expanded Java package prefixes (including androidx, lombok, etc.)
        JAVA_PREFIXES = (
            "java.", "javax.", "org.", "com.", "android.", "androidx.",
            "sun.", "kotlin.", "scala.", "groovy.", "lombok.", "io.",
            "net.", "edu.", "gov.", "mil.",
        )
        JS_PLACEHOLDERS = ("import_statement", "export_statement")
        is_java       = any(module.startswith(p) for p in JAVA_PREFIXES)
        # JS imports often embed the whole 'import X from "y"' as module name
        is_js_inline  = (' ' in module or '"' in module or "'" in module)
        is_placeholder = module in JS_PLACEHOLDERS
        # Java wildcard: import lombok.* or similar
        is_wildcard   = module.endswith('.*') or module.endswith('*')
        if is_java or is_js_inline or is_placeholder or is_wildcard:
            # Strip leading "import " from raw JS statement text to avoid
            # generating "# import import React from 'react'"
            display = module
            if display.startswith("import "):
                display = display[len("import "):]
            elif display.startswith("export "):
                display = display[len("export "):]
            self._write(f"# import {display}")
            return
        if node.names:
            names = ", ".join(node.names)
            self._write(f"from {module} import {names}")
        elif node.alias:
            self._write(f"import {module} as {node.alias}")
        else:
            self._write(f"import {module}")


    def generate_Delete(self, node: Delete) -> None:
        self._write(f"del {self._gen_expr(node.target)}")

    def generate_Assert(self, node: Assert) -> None:
        cond = self._gen_expr(node.condition)
        if node.message:
            msg = self._gen_expr(node.message)
            self._write(f"assert {cond}, {msg}")
        else:
            self._write(f"assert {cond}")

    # ── Expressions ───────────────────────────────────────────────────────

    # Placeholder node type names produced when JS/Java lifter can't parse
    # a node (JSX, decorators, template literals, etc.). Emitting them as
    # Python identifiers produces unrunnable code.
    _PLACEHOLDER_NAMES = frozenset({
        "jsx_element", "jsx_fragment", "jsx_expression", "jsx_attribute",
        "import_statement", "export_statement", "export_default",
        "property_identifier", "type_identifier", "template_string",
        "identifier",  # bare 'identifier' is a tree-sitter placeholder
    })

    def expr_Name(self, node: Name) -> str:
        # Replace JSX/tree-sitter placeholder node-type names with None
        if node.id in self._PLACEHOLDER_NAMES or node.id.endswith("_identifier"):
            return "None"   # safe in all expression contexts
        # Rename Python keywords used as identifiers (e.g. Java param named 'global')
        if node.id in self._PY_KEYWORDS:
            return f"{node.id}_"
        return node.id

    def _format_param(self, param: Param) -> str:
        """Rename params that clash with Python keywords (e.g. 'global' → 'global_')."""
        name = param.name
        if name in self._PY_KEYWORDS:
            name = f"{name}_"
        if param.type_annotation:
            return f"{name}: {param.type_annotation}"
        return name

    def generate_ExprStmt(self, node: ExprStmt) -> None:
        expr_str = self._gen_expr(node.expr)
        # Skip C-style comment placeholders entirely (they're invalid Python)
        if expr_str.startswith("/*") and expr_str.endswith("*/"):
            self._write(f"# {expr_str[2:-2].strip()}")
        else:
            self._write(expr_str)

    def expr_Assignment(self, node: Assignment) -> str:
        """Handle assignment-as-expression using walrus operator (Python 3.8+)."""
        target = self._gen_expr(node.target)
        value  = self._gen_expr(node.value)
        return f"({target} := {value})"

    def expr_Attribute(self, node: Attribute) -> str:
        """Override to handle Java .class access (e.g. Foo.class → type(Foo))."""
        obj = self._gen_expr(node.obj)
        if node.attr == "class":
            return f"type({obj})"
        return f"{obj}.{node.attr}"

    def expr_Ternary(self, node: Ternary) -> str:
        cond = self._gen_expr(node.condition)
        tv = self._gen_expr(node.true_value)
        fv = self._gen_expr(node.false_value)
        return f"({tv} if {cond} else {fv})"

    def expr_Lambda(self, node: Lambda) -> str:
        params = ", ".join(p.name for p in node.params)
        body = self._gen_expr(node.body)
        return f"lambda {params}: {body}"

    def expr_ListComp(self, node: ListComp) -> str:
        elem = self._gen_expr(node.element)
        iterable = self._gen_expr(node.iterable)
        if node.condition:
            cond = self._gen_expr(node.condition)
            return f"[{elem} for {node.target} in {iterable} if {cond}]"
        return f"[{elem} for {node.target} in {iterable}]"

    def expr_UnaryOp(self, node: UnaryOp) -> str:
        operand = self._gen_expr(node.operand)
        if node.op == "not":
            return f"not {operand}"
        return f"{node.op}{operand}"


    def expr_BoolOp(self, node: BoolOp) -> str:
        op = "and" if node.op == "and" else "or"
        parts = [self._gen_expr(v) for v in node.values]
        return f"({f' {op} '.join(parts)})"

    def expr_SetLiteral(self, node: SetLiteral) -> str:
        elems = ", ".join(self._gen_expr(e) for e in node.elements)
        return "{" + elems + "}"

    def expr_TupleLiteral(self, node: TupleLiteral) -> str:
        elems = ", ".join(self._gen_expr(e) for e in node.elements)
        if len(node.elements) == 1:
            return f"({elems},)"
        return f"({elems})"
