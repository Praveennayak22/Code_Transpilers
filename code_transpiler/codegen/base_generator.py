"""
codegen/base_generator.py
=========================
BaseGenerator — the abstract base class for all target language generators.

Every target language (Java, JavaScript, Python, C, C++) inherits from this
class and overrides only what is semantically different.

Design inspired by Cito's GenBase class which supports 11 targets.

The generator walks the Canonical IR tree and produces a target language
source code string by appending to an internal buffer.
"""

from __future__ import annotations
from typing import List, Optional, Any
from ir.nodes import *


class BaseGenerator:
    """
    Abstract base code generator.

    Subclasses override specific generate_* methods to handle
    language-specific syntax differences.
    """

    # ── Language metadata (override in subclasses) ────────────────────────
    LANGUAGE_NAME: str = "base"
    INDENT_CHAR: str = "    "       # 4 spaces
    STMT_TERMINATOR: str = ""       # ";" for C-like, "" for Python
    BLOCK_OPEN: str = ""            # "{" for C-like, "" for Python
    BLOCK_CLOSE: str = ""           # "}" for C-like, "" for Python
    NULL_LITERAL: str = "null"      # "None" | "null" | "NULL"
    TRUE_LITERAL: str = "true"      # "True" | "true"
    FALSE_LITERAL: str = "false"    # "False" | "false"
    AND_OP: str = "&&"              # "and" | "&&"
    OR_OP: str = "||"              # "or" | "||"
    NOT_OP: str = "!"               # "not " | "!"
    EQ_OP: str = "=="               # "==" | "==="
    NEQ_OP: str = "!="              # "!=" | "!=="

    def __init__(self):
        self._lines: List[str] = []
        self._indent_level: int = 0

    # ── Public entry point ────────────────────────────────────────────────

    def generate(self, node: CanonicalNode) -> str:
        """Generate target language source code from a CanonicalNode tree."""
        self._lines = []
        self._indent_level = 0
        self._gen(node)
        return "\n".join(self._lines)

    # ── Internal dispatch ─────────────────────────────────────────────────

    def _gen(self, node: CanonicalNode) -> None:
        """Dispatch to the appropriate generate_* method."""
        if node is None:
            return
        method_name = f"generate_{type(node).__name__}"
        method = getattr(self, method_name, self._generate_unknown)
        method(node)

    def _gen_expr(self, node: CanonicalNode) -> str:
        """Generate an expression and return it as a string."""
        if node is None:
            return self.NULL_LITERAL
        method_name = f"expr_{type(node).__name__}"
        method = getattr(self, method_name, self._expr_unknown)
        return method(node)

    def _generate_unknown(self, node: CanonicalNode) -> None:
        self._write(f"/* unsupported: {type(node).__name__} */")

    def _expr_unknown(self, node: CanonicalNode) -> str:
        return f"/* expr:{type(node).__name__} */"

    # ── Buffer helpers ────────────────────────────────────────────────────

    def _write(self, text: str) -> None:
        """Write a line at the current indentation level."""
        indent = self.INDENT_CHAR * self._indent_level
        self._lines.append(f"{indent}{text}")

    def _write_raw(self, text: str) -> None:
        """Write a line without any indentation."""
        self._lines.append(text)

    def _indent(self) -> None:
        self._indent_level += 1

    def _dedent(self) -> None:
        self._indent_level = max(0, self._indent_level - 1)

    def _blank(self) -> None:
        self._lines.append("")

    # ── Body helpers ──────────────────────────────────────────────────────

    def _gen_body(self, body: List[CanonicalNode]) -> None:
        """Generate all statements in a body list."""
        for stmt in body:
            self._gen(stmt)

    def _gen_block(self, body: List[CanonicalNode]) -> None:
        """Generate a block with optional braces (overridden per language)."""
        if self.BLOCK_OPEN:
            self._write(self.BLOCK_OPEN)
        self._indent()
        self._gen_body(body)
        self._dedent()
        if self.BLOCK_CLOSE:
            self._write(self.BLOCK_CLOSE)

    # ── Module ────────────────────────────────────────────────────────────

    def generate_Module(self, node: Module) -> None:
        for imp in node.imports:
            self._gen(imp)
        if node.imports:
            self._blank()
        for stmt in node.body:
            self._gen(stmt)
            self._blank()

    # ── Declarations ─────────────────────────────────────────────────────

    def generate_FunctionDef(self, node: FunctionDef) -> None:
        params_str = self._gen_params(node.params)
        ret = self._format_return_type(node.return_type)
        signature = self._format_function_signature(node, params_str, ret)
        self._write(signature)
        self._gen_block(node.body)

    def _gen_params(self, params: List[Param]) -> str:
        return ", ".join(self._format_param(p) for p in params)

    def _format_param(self, param: Param) -> str:
        """Format a single parameter (override for typed languages)."""
        return param.name

    def _format_return_type(self, return_type: Optional[str]) -> str:
        return return_type or ""

    def _format_function_signature(self, node: FunctionDef,
                                    params_str: str, ret: str) -> str:
        return f"function {node.name}({params_str})"

    def generate_ClassDef(self, node: ClassDef) -> None:
        bases = f"({', '.join(node.bases)})" if node.bases else ""
        self._write(f"class {node.name}{bases}")
        self._gen_block(node.body)

    def generate_VarDecl(self, node: VarDecl) -> None:
        val = f" = {self._gen_expr(node.value)}" if node.value else ""
        self._write(f"{node.name}{val}{self.STMT_TERMINATOR}")

    # ── Statements ────────────────────────────────────────────────────────

    def generate_Assignment(self, node: Assignment) -> None:
        target = self._gen_expr(node.target)
        value = self._gen_expr(node.value)
        self._write(f"{target} = {value}{self.STMT_TERMINATOR}")

    def generate_AugAssignment(self, node: AugAssignment) -> None:
        target = self._gen_expr(node.target)
        value = self._gen_expr(node.value)
        self._write(f"{target} {node.op} {value}{self.STMT_TERMINATOR}")

    def generate_Return(self, node: Return) -> None:
        if node.value:
            self._write(f"return {self._gen_expr(node.value)}{self.STMT_TERMINATOR}")
        else:
            self._write(f"return{self.STMT_TERMINATOR}")

    def generate_IfStmt(self, node: IfStmt) -> None:
        self._write(f"if ({self._gen_expr(node.condition)})")
        self._gen_block(node.then_body)
        for elif_clause in node.elif_clauses:
            self._write(f"else if ({self._gen_expr(elif_clause.condition)})")
            self._gen_block(elif_clause.body)
        if node.else_body:
            self._write("else")
            self._gen_block(node.else_body)

    def generate_WhileLoop(self, node: WhileLoop) -> None:
        self._write(f"while ({self._gen_expr(node.condition)})")
        self._gen_block(node.body)

    def generate_ForLoop(self, node: ForLoop) -> None:
        init = self._gen_expr(node.init) if node.init else ""
        cond = self._gen_expr(node.condition) if node.condition else ""
        upd = self._gen_expr(node.update) if node.update else ""
        self._write(f"for ({init}; {cond}; {upd})")
        self._gen_block(node.body)

    def generate_ForEachLoop(self, node: ForEachLoop) -> None:
        iterable = self._gen_expr(node.iterable)
        self._write(f"for (var {node.target} of {iterable})")
        self._gen_block(node.body)

    def generate_Break(self, node: Break) -> None:
        self._write(f"break{self.STMT_TERMINATOR}")

    def generate_Continue(self, node: Continue) -> None:
        self._write(f"continue{self.STMT_TERMINATOR}")

    def generate_ExprStmt(self, node: ExprStmt) -> None:
        self._write(f"{self._gen_expr(node.expr)}{self.STMT_TERMINATOR}")

    def generate_PrintStmt(self, node: PrintStmt) -> None:
        args = ", ".join(self._gen_expr(a) for a in node.args)
        self._write(f"print({args}){self.STMT_TERMINATOR}")

    def generate_TryExcept(self, node: TryExcept) -> None:
        self._write("try")
        self._gen_block(node.try_body)
        for handler in node.handlers:
            exc = handler.exception_type or "Exception"
            name = f" {handler.name}" if handler.name else ""
            self._write(f"catch ({exc}{name})")
            self._gen_block(handler.body)
        if node.finally_body:
            self._write("finally")
            self._gen_block(node.finally_body)

    def generate_Raise(self, node: Raise) -> None:
        exc = self._gen_expr(node.exception) if node.exception else ""
        self._write(f"throw {exc}{self.STMT_TERMINATOR}")

    def generate_Assert(self, node: Assert) -> None:
        cond = self._gen_expr(node.condition)
        self._write(f"assert({cond}){self.STMT_TERMINATOR}")

    def generate_Comment(self, node: Comment) -> None:
        self._write(f"// {node.text}")

    def generate_Import(self, node: Import) -> None:
        pass  # Override in each language

    def generate_Delete(self, node: Delete) -> None:
        pass  # Language-specific

    # ── Expressions ───────────────────────────────────────────────────────

    def expr_Name(self, node: Name) -> str:
        return node.id

    def expr_Literal(self, node: Literal) -> str:
        if node.kind == "null":
            return self.NULL_LITERAL
        elif node.kind == "bool":
            return self.TRUE_LITERAL if node.value else self.FALSE_LITERAL
        elif node.kind == "string":
            # Escape all special chars — critical for multiline strings
            # Python triple-quoted strings contain real \n which break C/Java
            escaped = (str(node.value)
                       .replace("\\", "\\\\")
                       .replace('"',  '\\"')
                       .replace("\n", "\\n")
                       .replace("\r", "\\r")
                       .replace("\t", "\\t")
                       .replace("\0", "\\0"))
            return f'"{escaped}"'
        else:
            return str(node.value)

    def expr_BinaryOp(self, node: BinaryOp) -> str:
        left = self._gen_expr(node.left)
        right = self._gen_expr(node.right)
        op = self._map_binary_op(node.op)
        return f"({left} {op} {right})"

    def _map_binary_op(self, op: str) -> str:
        return op  # Override for language-specific operators

    def expr_UnaryOp(self, node: UnaryOp) -> str:
        operand = self._gen_expr(node.operand)
        if node.op == "not":
            return f"{self.NOT_OP}{operand}"
        return f"{node.op}{operand}"

    def expr_CompareOp(self, node: CompareOp) -> str:
        left = self._gen_expr(node.left)
        right = self._gen_expr(node.right)
        op = self._map_compare_op(node.op)
        return f"({left} {op} {right})"

    def _map_compare_op(self, op: str) -> str:
        mapping = {"==": self.EQ_OP, "!=": self.NEQ_OP}
        return mapping.get(op, op)

    def expr_BoolOp(self, node: BoolOp) -> str:
        op = self.AND_OP if node.op == "and" else self.OR_OP
        parts = [self._gen_expr(v) for v in node.values]
        return f"({f' {op} '.join(parts)})"

    def expr_Call(self, node: Call) -> str:
        func = self._gen_expr(node.func)
        args = [self._gen_expr(a) for a in node.args]
        kwargs = [f"{kw.key}={self._gen_expr(kw.value)}" for kw in node.kwargs]
        all_args = ", ".join(args + kwargs)
        return f"{func}({all_args})"

    def expr_Attribute(self, node: Attribute) -> str:
        return f"{self._gen_expr(node.obj)}.{node.attr}"

    def expr_Index(self, node: Index) -> str:
        return f"{self._gen_expr(node.obj)}[{self._gen_expr(node.index)}]"

    def expr_Slice(self, node: Slice) -> str:
        start = self._gen_expr(node.start) if node.start else ""
        stop = self._gen_expr(node.stop) if node.stop else ""
        return f"{self._gen_expr(node.obj)}[{start}:{stop}]"

    def expr_Ternary(self, node: Ternary) -> str:
        cond = self._gen_expr(node.condition)
        tv = self._gen_expr(node.true_value)
        fv = self._gen_expr(node.false_value)
        return f"({tv} if {cond} else {fv})"

    def expr_Lambda(self, node: Lambda) -> str:
        params = ", ".join(p.name for p in node.params)
        body = self._gen_expr(node.body)
        return f"({params}) => {body}"

    def expr_ListLiteral(self, node: ListLiteral) -> str:
        elems = ", ".join(self._gen_expr(e) for e in node.elements)
        return f"[{elems}]"

    def expr_DictLiteral(self, node: DictLiteral) -> str:
        pairs = ", ".join(
            f"{self._gen_expr(k)}: {self._gen_expr(v)}"
            for k, v in zip(node.keys, node.values)
        )
        return "{" + pairs + "}"

    def expr_TupleLiteral(self, node: TupleLiteral) -> str:
        elems = ", ".join(self._gen_expr(e) for e in node.elements)
        return f"[{elems}]"  # Default: treat as array

    def expr_SetLiteral(self, node: SetLiteral) -> str:
        elems = ", ".join(self._gen_expr(e) for e in node.elements)
        return "{" + elems + "}"

    def expr_ListComp(self, node: ListComp) -> str:
        # Default: generate as comment placeholder (overridden in generators)
        elem = self._gen_expr(node.element)
        iterable = self._gen_expr(node.iterable)
        return f"/* listcomp: {elem} for {node.target} in {iterable} */"
