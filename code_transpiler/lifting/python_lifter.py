"""
lifting/python_lifter.py
========================
Lifts a CPython AST (from ast.parse) into the Canonical IR.

This is the most important lifter as Python is the primary source language
(Python → Java, JavaScript, C, C++).

We walk every node of the CPython AST and convert it to the
corresponding CanonicalNode.
"""

from __future__ import annotations
import ast
from typing import Any, List, Optional

from ir.nodes import (
    Module, FunctionDef, ClassDef, Param, VarDecl,
    Assignment, AugAssignment, Return, IfStmt, ElifClause,
    WhileLoop, ForLoop, ForEachLoop, Break, Continue,
    ExprStmt, TryExcept, ExceptHandler, Raise, Delete, Assert,
    Comment, Import, PrintStmt,
    Name, Literal, BinaryOp, UnaryOp, CompareOp, BoolOp,
    Call, Keyword, Attribute, Index, Slice, Ternary, Lambda,
    ListLiteral, DictLiteral, SetLiteral, TupleLiteral, ListComp,
    CanonicalNode,
)


# Map Python AST operator classes to canonical op strings
_BIN_OP_MAP = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
    ast.Mod: "%", ast.Pow: "**", ast.FloorDiv: "//",
    ast.BitAnd: "&", ast.BitOr: "|", ast.BitXor: "^",
    ast.LShift: "<<", ast.RShift: ">>",
}

_UNARY_OP_MAP = {
    ast.USub: "-", ast.UAdd: "+", ast.Not: "not", ast.Invert: "~",
}

_CMP_OP_MAP = {
    ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.Gt: ">",
    ast.LtE: "<=", ast.GtE: ">=",
    ast.In: "in", ast.NotIn: "not in",
    ast.Is: "is", ast.IsNot: "is not",
}

_AUG_OP_MAP = {
    ast.Add: "+=", ast.Sub: "-=", ast.Mult: "*=", ast.Div: "/=",
    ast.Mod: "%=", ast.Pow: "**=", ast.FloorDiv: "//=",
}


class PythonLifter:
    """Converts CPython AST → Canonical IR."""

    def lift(self, tree: ast.Module, source_code: str = "") -> Module:
        """Entry point: lift a full module."""
        imports = []
        body = []
        for node in tree.body:
            result = self._lift_stmt(node)
            if isinstance(result, Import):
                imports.append(result)
            elif result is not None:
                body.append(result)
        return Module(body=body, imports=imports)

    # ── Statements ────────────────────────────────────────────────────────

    def _lift_stmt(self, node: ast.AST) -> Optional[CanonicalNode]:
        method = f"_lift_{type(node).__name__}"
        handler = getattr(self, method, self._lift_unknown_stmt)
        return handler(node)

    def _lift_unknown_stmt(self, node: ast.AST) -> Optional[CanonicalNode]:
        return None  # Skip unsupported nodes gracefully

    def _lift_body(self, stmts: list) -> List[CanonicalNode]:
        result = []
        for stmt in stmts:
            node = self._lift_stmt(stmt)
            if node is not None:
                result.append(node)
        return result

    def _lift_FunctionDef(self, node: ast.FunctionDef) -> FunctionDef:
        params = self._lift_args(node.args)
        return_type = None
        if node.returns:
            return_type = self._annotation_to_str(node.returns)
        decorators = [ast.unparse(d) for d in node.decorator_list]
        body = self._lift_body(node.body)
        return FunctionDef(
            name=node.name,
            params=params,
            body=body,
            return_type=return_type,
            is_async=False,
            decorators=decorators,
            source_line=node.lineno,
        )

    def _lift_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> FunctionDef:
        result = self._lift_FunctionDef(node)
        result.is_async = True
        return result

    def _lift_ClassDef(self, node: ast.ClassDef) -> ClassDef:
        bases = [ast.unparse(b) for b in node.bases]
        decorators = [ast.unparse(d) for d in node.decorator_list]
        body = self._lift_body(node.body)
        return ClassDef(
            name=node.name,
            bases=bases,
            body=body,
            decorators=decorators,
            source_line=node.lineno,
        )

    def _lift_Return(self, node: ast.Return) -> Return:
        value = self._lift_expr(node.value) if node.value else None
        return Return(value=value, source_line=node.lineno)

    def _lift_Assign(self, node: ast.Assign) -> Assignment:
        target = self._lift_expr(node.targets[0]) if node.targets else None
        value = self._lift_expr(node.value)
        return Assignment(target=target, value=value, source_line=node.lineno)

    def _lift_AnnAssign(self, node: ast.AnnAssign) -> Assignment:
        target = self._lift_expr(node.target)
        value = self._lift_expr(node.value) if node.value else None
        type_ann = self._annotation_to_str(node.annotation)
        return Assignment(
            target=target, value=value,
            type_annotation=type_ann,
            source_line=node.lineno,
        )

    def _lift_AugAssign(self, node: ast.AugAssign) -> AugAssignment:
        target = self._lift_expr(node.target)
        value = self._lift_expr(node.value)
        op = _AUG_OP_MAP.get(type(node.op), "+=")
        return AugAssignment(target=target, op=op, value=value,
                             source_line=node.lineno)

    def _lift_If(self, node: ast.If) -> IfStmt:
        condition = self._lift_expr(node.test)
        then_body = self._lift_body(node.body)
        elif_clauses = []
        else_body = []

        orelse = node.orelse
        while len(orelse) == 1 and isinstance(orelse[0], ast.If):
            elif_node = orelse[0]
            elif_clauses.append(ElifClause(
                condition=self._lift_expr(elif_node.test),
                body=self._lift_body(elif_node.body),
            ))
            orelse = elif_node.orelse

        if orelse:
            else_body = self._lift_body(orelse)

        return IfStmt(
            condition=condition,
            then_body=then_body,
            elif_clauses=elif_clauses,
            else_body=else_body,
            source_line=node.lineno,
        )

    def _lift_While(self, node: ast.While) -> WhileLoop:
        return WhileLoop(
            condition=self._lift_expr(node.test),
            body=self._lift_body(node.body),
            source_line=node.lineno,
        )

    def _lift_For(self, node: ast.For) -> ForEachLoop:
        target = ast.unparse(node.target)
        iterable = self._lift_expr(node.iter)
        body = self._lift_body(node.body)
        return ForEachLoop(
            target=target,
            iterable=iterable,
            body=body,
            source_line=node.lineno,
        )

    def _lift_Break(self, node: ast.Break) -> Break:
        return Break(source_line=node.lineno)

    def _lift_Continue(self, node: ast.Continue) -> Continue:
        return Continue(source_line=node.lineno)

    def _lift_Expr(self, node: ast.Expr) -> Optional[CanonicalNode]:
        # Intercept print() calls specially
        if isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id == "print":
                args = [self._lift_expr(a) for a in call.args]
                return PrintStmt(args=args, source_line=node.lineno)
        expr = self._lift_expr(node.value)
        if expr is None:
            return None
        return ExprStmt(expr=expr, source_line=node.lineno)

    def _lift_Try(self, node: ast.Try) -> TryExcept:
        try_body = self._lift_body(node.body)
        handlers = []
        for h in node.handlers:
            exc_type = ast.unparse(h.type) if h.type else None
            exc_name = h.name
            h_body = self._lift_body(h.body)
            handlers.append(ExceptHandler(
                exception_type=exc_type,
                name=exc_name,
                body=h_body,
            ))
        finally_body = self._lift_body(node.finalbody) if node.finalbody else []
        return TryExcept(
            try_body=try_body,
            handlers=handlers,
            finally_body=finally_body,
            source_line=node.lineno,
        )

    def _lift_Raise(self, node: ast.Raise) -> Raise:
        exc = self._lift_expr(node.exc) if node.exc else None
        return Raise(exception=exc, source_line=node.lineno)

    def _lift_Delete(self, node: ast.Delete) -> Delete:
        target = self._lift_expr(node.targets[0]) if node.targets else None
        return Delete(target=target, source_line=node.lineno)

    def _lift_Assert(self, node: ast.Assert) -> Assert:
        cond = self._lift_expr(node.test)
        msg = self._lift_expr(node.msg) if node.msg else None
        return Assert(condition=cond, message=msg, source_line=node.lineno)

    def _lift_Import(self, node: ast.Import) -> Import:
        alias = node.names[0]
        return Import(
            module=alias.name,
            alias=alias.asname,
            source_line=node.lineno,
        )

    def _lift_ImportFrom(self, node: ast.ImportFrom) -> Import:
        names = [a.name for a in node.names]
        return Import(
            module=node.module or "",
            names=names,
            source_line=node.lineno,
        )

    def _lift_Global(self, node: ast.Global) -> None:
        return None  # Skip — global declarations are Python-specific

    def _lift_Nonlocal(self, node: ast.Nonlocal) -> None:
        return None

    def _lift_Pass(self, node: ast.Pass) -> None:
        return None

    # ── Expressions ───────────────────────────────────────────────────────

    def _lift_expr(self, node: ast.AST) -> Optional[CanonicalNode]:
        if node is None:
            return None
        method = f"_lift_expr_{type(node).__name__}"
        handler = getattr(self, method, self._lift_expr_unknown)
        return handler(node)

    def _lift_expr_unknown(self, node: ast.AST) -> Optional[CanonicalNode]:
        # Fallback: unparse to string literal
        try:
            return Literal(value=ast.unparse(node), kind="string")
        except Exception:
            return None

    def _lift_expr_Constant(self, node: ast.Constant) -> Literal:
        if node.value is None:
            return Literal(value=None, kind="null")
        elif isinstance(node.value, bool):
            return Literal(value=node.value, kind="bool")
        elif isinstance(node.value, int):
            return Literal(value=node.value, kind="int")
        elif isinstance(node.value, float):
            return Literal(value=node.value, kind="float")
        elif isinstance(node.value, str):
            return Literal(value=node.value, kind="string")
        else:
            return Literal(value=str(node.value), kind="string")

    def _lift_expr_Name(self, node: ast.Name) -> Name:
        return Name(id=node.id)

    def _lift_expr_BinOp(self, node: ast.BinOp) -> BinaryOp:
        op = _BIN_OP_MAP.get(type(node.op), "+")
        return BinaryOp(
            left=self._lift_expr(node.left),
            op=op,
            right=self._lift_expr(node.right),
        )

    def _lift_expr_UnaryOp(self, node: ast.UnaryOp) -> UnaryOp:
        op = _UNARY_OP_MAP.get(type(node.op), "-")
        return UnaryOp(op=op, operand=self._lift_expr(node.operand))

    def _lift_expr_Compare(self, node: ast.Compare) -> CanonicalNode:
        left = self._lift_expr(node.left)
        if len(node.ops) == 1:
            op = _CMP_OP_MAP.get(type(node.ops[0]), "==")
            right = self._lift_expr(node.comparators[0])
            return CompareOp(left=left, op=op, right=right)
        # Multiple comparators: a < b < c → (a < b) and (b < c)
        parts = []
        for i, (op_node, comp) in enumerate(zip(node.ops, node.comparators)):
            op = _CMP_OP_MAP.get(type(op_node), "==")
            lhs = left if i == 0 else self._lift_expr(node.comparators[i - 1])
            parts.append(CompareOp(left=lhs, op=op, right=self._lift_expr(comp)))
        return BoolOp(op="and", values=parts)

    def _lift_expr_BoolOp(self, node: ast.BoolOp) -> BoolOp:
        op = "and" if isinstance(node.op, ast.And) else "or"
        values = [self._lift_expr(v) for v in node.values]
        return BoolOp(op=op, values=values)

    def _lift_expr_Call(self, node: ast.Call) -> Call:
        func = self._lift_expr(node.func)
        args = [self._lift_expr(a) for a in node.args]
        kwargs = [
            Keyword(key=kw.arg or "**", value=self._lift_expr(kw.value))
            for kw in node.keywords
        ]
        return Call(func=func, args=args, kwargs=kwargs)

    def _lift_expr_Attribute(self, node: ast.Attribute) -> Attribute:
        return Attribute(obj=self._lift_expr(node.value), attr=node.attr)

    def _lift_expr_Subscript(self, node: ast.Subscript) -> CanonicalNode:
        obj = self._lift_expr(node.value)
        sl = node.slice
        if isinstance(sl, ast.Slice):
            return Slice(
                obj=obj,
                start=self._lift_expr(sl.lower) if sl.lower else None,
                stop=self._lift_expr(sl.upper) if sl.upper else None,
                step=self._lift_expr(sl.step) if sl.step else None,
            )
        return Index(obj=obj, index=self._lift_expr(sl))

    def _lift_expr_IfExp(self, node: ast.IfExp) -> Ternary:
        return Ternary(
            condition=self._lift_expr(node.test),
            true_value=self._lift_expr(node.body),
            false_value=self._lift_expr(node.orelse),
        )

    def _lift_expr_Lambda(self, node: ast.Lambda) -> Lambda:
        params = self._lift_args(node.args)
        body = self._lift_expr(node.body)
        return Lambda(params=params, body=body)

    def _lift_expr_List(self, node: ast.List) -> ListLiteral:
        return ListLiteral(elements=[self._lift_expr(e) for e in node.elts])

    def _lift_expr_Tuple(self, node: ast.Tuple) -> TupleLiteral:
        return TupleLiteral(elements=[self._lift_expr(e) for e in node.elts])

    def _lift_expr_Set(self, node: ast.Set) -> SetLiteral:
        return SetLiteral(elements=[self._lift_expr(e) for e in node.elts])

    def _lift_expr_Dict(self, node: ast.Dict) -> DictLiteral:
        keys = [self._lift_expr(k) for k in node.keys if k is not None]
        values = [self._lift_expr(v) for v in node.values]
        return DictLiteral(keys=keys, values=values)

    def _lift_expr_ListComp(self, node: ast.ListComp) -> ListComp:
        gen = node.generators[0]
        target = ast.unparse(gen.target)
        iterable = self._lift_expr(gen.iter)
        condition = self._lift_expr(gen.ifs[0]) if gen.ifs else None
        element = self._lift_expr(node.elt)
        return ListComp(
            element=element,
            target=target,
            iterable=iterable,
            condition=condition,
        )

    def _lift_expr_JoinedStr(self, node: ast.JoinedStr) -> Literal:
        # f-strings: unparse to string for now
        try:
            return Literal(value=ast.unparse(node), kind="string")
        except Exception:
            return Literal(value="<fstring>", kind="string")

    # ── Helpers ───────────────────────────────────────────────────────────

    def _lift_args(self, args: ast.arguments) -> List[Param]:
        params = []
        # Compute defaults alignment
        n_args = len(args.args)
        n_defaults = len(args.defaults)
        defaults = [None] * (n_args - n_defaults) + list(args.defaults)

        for arg, default in zip(args.args, defaults):
            type_ann = self._annotation_to_str(arg.annotation) if arg.annotation else None
            default_val = self._lift_expr(default) if default else None
            params.append(Param(
                name=arg.arg,
                type_annotation=type_ann,
                default_value=default_val,
            ))

        # *args
        if args.vararg:
            params.append(Param(name=f"*{args.vararg.arg}"))
        # **kwargs
        if args.kwarg:
            params.append(Param(name=f"**{args.kwarg.arg}"))

        return params

    def _annotation_to_str(self, node: ast.AST) -> Optional[str]:
        if node is None:
            return None
        try:
            return ast.unparse(node)
        except Exception:
            return None
