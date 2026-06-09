"""
codegen/java_generator.py
=========================
Generates Java source code from Canonical IR.

Key differences from base:
- Strongly typed: all variables, params, and return types must have types
- Classes wrap all code (no top-level functions)
- Semicolons terminate statements
- Uses { } for blocks
- No list comprehensions → converted to for loops by transformer
- print() → System.out.println()
- null instead of None
- && || ! instead of and or not
- === → ==, !== → !=
"""

from __future__ import annotations
from typing import Optional, List
from ir.nodes import *
from codegen.base_generator import BaseGenerator


# Python type → Java type mapping
PYTHON_TO_JAVA_TYPE = {
    "int": "int", "float": "double", "str": "String",
    "bool": "boolean", "None": "void", "list": "List<Object>",
    "dict": "Map<String, Object>", "set": "Set<Object>",
    "tuple": "Object[]", "any": "Object", "Any": "Object",
}


def _java_type(t: Optional[str]) -> str:
    if t is None:
        return "Object"
    return PYTHON_TO_JAVA_TYPE.get(t, t)


class JavaGenerator(BaseGenerator):
    LANGUAGE_NAME = "Java"
    STMT_TERMINATOR = ";"
    BLOCK_OPEN = "{"
    BLOCK_CLOSE = "}"
    NULL_LITERAL = "null"
    TRUE_LITERAL = "true"
    FALSE_LITERAL = "false"
    AND_OP = "&&"
    OR_OP = "||"
    NOT_OP = "!"
    EQ_OP = "=="
    NEQ_OP = "!="

    # ── Module ────────────────────────────────────────────────────────────

    def generate_Module(self, node: Module) -> None:
        # Emit imports from the IR imports list (injected by transform)
        for imp in node.imports:
            if imp.module:
                self._write(f"import {imp.module};")
        self._blank()

        # If transform already wrapped in a ClassDef, just emit it directly
        has_class = any(isinstance(n, ClassDef) for n in node.body)
        if has_class:
            for stmt in node.body:
                self._gen(stmt)
            return

        # Fallback: wrap everything in TranspiledCode class
        self._write("public class TranspiledCode {")
        self._indent()
        for stmt in node.body:
            self._gen(stmt)
            self._blank()
        self._dedent()
        self._write("}")

    # ── Declarations ─────────────────────────────────────────────────────

    def _format_param(self, param: Param) -> str:
        java_type = _java_type(param.type_annotation)
        return f"{java_type} {param.name}"

    def _format_return_type(self, return_type: Optional[str]) -> str:
        return _java_type(return_type) if return_type else "void"

    def _format_function_signature(self, node: FunctionDef,
                                    params_str: str, ret: str) -> str:
        modifier = node.access_modifier or "public"
        # Don't make methods static if they are inside a class (instance methods)
        # Only keep static if explicitly set AND we're not inside a class context
        inside_class = getattr(self, '_current_class', None) is not None
        is_constructor = inside_class and node.name == getattr(self, '_current_class', None)
        if is_constructor:
            # Java constructors have no return type
            return f"{modifier} {node.name}({params_str})"
        static = " static" if (node.is_static and not inside_class) else ""
        return f"{modifier}{static} {ret} {node.name}({params_str})"

    # ── this. for self references (mirrors C++ this-> fix) ────────────────

    def expr_Attribute(self, node) -> str:
        """Convert _this_cpp_ref.x sentinel → this.x in Java."""
        obj = self._gen_expr(node.obj)
        if obj == "_this_cpp_ref":
            return f"this.{node.attr}"
        return f"{obj}.{node.attr}"

    def generate_ClassDef(self, node: ClassDef) -> None:
        # Track current class so we can detect constructors and avoid static
        self._current_class = node.name
        extends = f" extends {node.bases[0]}" if node.bases else ""
        self._write(f"public class {node.name}{extends} {{")
        self._indent()
        self._gen_body(node.body)
        self._dedent()
        self._write("}")
        self._current_class = None

    def generate_VarDecl(self, node: VarDecl) -> None:
        java_type = _java_type(node.type_annotation)
        modifier = "final " if node.is_const else ""
        val = f" = {self._gen_expr(node.value)}" if node.value else ""
        self._write(f"{modifier}{java_type} {node.name}{val};")

    # ── Statements ────────────────────────────────────────────────────────

    def generate_Assignment(self, node: Assignment) -> None:
        target = self._gen_expr(node.target)
        value = self._gen_expr(node.value)
        if node.type_annotation:
            java_type = _java_type(node.type_annotation)
            self._write(f"{java_type} {target} = {value};")
        else:
            self._write(f"{target} = {value};")

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
        ttype = _java_type(node.target_type) if node.target_type else "Object"
        iterable = self._gen_expr(node.iterable)
        self._write(f"for ({ttype} {node.target} : {iterable}) {{")
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
        if len(node.args) == 1:
            arg = self._gen_expr(node.args[0])
            self._write(f'System.out.println({arg});')
        elif len(node.args) > 1:
            # Concatenate with +
            parts = " + \" \" + ".join(self._gen_expr(a) for a in node.args)
            self._write(f'System.out.println({parts});')
        else:
            self._write('System.out.println();')

    def generate_TryExcept(self, node: TryExcept) -> None:
        self._write("try {")
        self._indent()
        self._gen_body(node.try_body)
        self._dedent()
        self._write("}")
        for handler in node.handlers:
            exc = handler.exception_type or "Exception"
            name = handler.name or "e"
            self._write(f"catch ({exc} {name}) {{")
            self._indent()
            self._gen_body(handler.body)
            self._dedent()
            self._write("}")
        if node.finally_body:
            self._write("finally {")
            self._indent()
            self._gen_body(node.finally_body)
            self._dedent()
            self._write("}")

    def generate_Raise(self, node: Raise) -> None:
        exc = self._gen_expr(node.exception) if node.exception else "new RuntimeException()"
        self._write(f"throw {exc};")

    def generate_Import(self, node: Import) -> None:
        if node.module:
            self._write(f"import {node.module};")

    def generate_Return(self, node: Return) -> None:
        if node.value:
            self._write(f"return {self._gen_expr(node.value)};")
        else:
            self._write("return;")

    def generate_Break(self, node: Break) -> None:
        self._write("break;")

    def generate_Continue(self, node: Continue) -> None:
        self._write("continue;")

    def generate_Assert(self, node: Assert) -> None:
        cond = self._gen_expr(node.condition)
        self._write(f"assert {cond};")

    def generate_ExprStmt(self, node: ExprStmt) -> None:
        self._write(f"{self._gen_expr(node.expr)};")

    # ── Expressions ───────────────────────────────────────────────────────

    def expr_Ternary(self, node: Ternary) -> str:
        cond = self._gen_expr(node.condition)
        tv = self._gen_expr(node.true_value)
        fv = self._gen_expr(node.false_value)
        return f"({cond} ? {tv} : {fv})"

    def expr_Lambda(self, node: Lambda) -> str:
        params = ", ".join(p.name for p in node.params)
        body = self._gen_expr(node.body)
        return f"({params}) -> {body}"

    def expr_ListLiteral(self, node: ListLiteral) -> str:
        elems = ", ".join(self._gen_expr(e) for e in node.elements)
        return f"new ArrayList<>(Arrays.asList({elems}))"

    def expr_DictLiteral(self, node: DictLiteral) -> str:
        self._write("new HashMap<>() {{")
        self._indent()
        for k, v in zip(node.keys, node.values):
            self._write(f"put({self._gen_expr(k)}, {self._gen_expr(v)});")
        self._dedent()
        self._write("}}")
        return ""

    def _map_binary_op(self, op: str) -> str:
        if op == "**":
            return "Math.pow"  # handled specially in expr_BinaryOp
        return op

    def expr_BinaryOp(self, node: BinaryOp) -> str:
        if node.op == "**":
            left = self._gen_expr(node.left)
            right = self._gen_expr(node.right)
            return f"Math.pow({left}, {right})"
        left = self._gen_expr(node.left)
        right = self._gen_expr(node.right)
        op = node.op
        return f"({left} {op} {right})"

    def expr_ListComp(self, node: ListComp) -> str:
        # Java doesn't have list comprehensions — this is a fallback
        # The transformer should have converted this to a ForEachLoop
        return f"/* list comprehension — use transformer */"
