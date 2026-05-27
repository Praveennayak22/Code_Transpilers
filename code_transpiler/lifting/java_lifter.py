"""
lifting/java_lifter.py
=======================
Lifts a Java tree-sitter CST into the Canonical IR.

Handles the most common Java constructs:
- Class and method definitions
- Variable declarations
- Control flow (if/else, for, while, try/catch)
- Expressions (arithmetic, comparison, calls)
"""

from __future__ import annotations
from typing import Optional, List

from ir.nodes import (
    Module, FunctionDef, ClassDef, Param, VarDecl,
    Assignment, Return, IfStmt, ElifClause,
    WhileLoop, ForLoop, ForEachLoop, Break, Continue,
    ExprStmt, TryExcept, ExceptHandler, Raise, Import, PrintStmt,
    Name, Literal, BinaryOp, UnaryOp, CompareOp, BoolOp,
    Call, Attribute, Index, Ternary, ListLiteral,
    CanonicalNode, AugAssignment,
)


class JavaLifter:
    """Converts Java tree-sitter CST → Canonical IR."""

    def lift(self, tree, source_code: str = "") -> Module:
        """Entry point: lift a full Java tree-sitter parse tree."""
        self._source_bytes = source_code.encode("utf-8") if source_code else b""
        root = tree.root_node

        body = []
        imports = []
        for child in root.children:
            result = self._lift_node(child)
            if result is not None:
                if isinstance(result, Import):
                    imports.append(result)
                elif isinstance(result, list):
                    body.extend(result)
                else:
                    body.append(result)
        return Module(body=body, imports=imports)

    def _text(self, node) -> str:
        """Get the source text for a node."""
        if self._source_bytes:
            return self._source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        return node.type

    def _lift_node(self, node) -> Optional[CanonicalNode]:
        """Dispatch to the appropriate lift method."""
        method = f"_lift_{node.type}"
        handler = getattr(self, method, self._lift_generic)
        return handler(node)

    def _lift_generic(self, node) -> Optional[CanonicalNode]:
        """Fallback for unsupported node types."""
        return None

    def _children_named(self, node):
        """Get only named children (skip punctuation tokens)."""
        return [c for c in node.children if c.is_named]

    def _lift_program(self, node):
        results = []
        for child in node.children:
            r = self._lift_node(child)
            if r:
                results.append(r)
        return results

    def _lift_import_declaration(self, node) -> Import:
        text = self._text(node)
        # "import java.util.List;"
        module = text.replace("import", "").replace(";", "").strip()
        return Import(module=module, source_line=node.start_point[0])

    def _lift_class_declaration(self, node) -> ClassDef:
        name = ""
        bases = []
        body = []
        for child in node.children:
            if child.type == "identifier":
                name = self._text(child)
            elif child.type == "superclass":
                for c in child.children:
                    if c.type == "type_identifier":
                        bases.append(self._text(c))
            elif child.type == "class_body":
                body = self._lift_class_body(child)
        return ClassDef(name=name, bases=bases, body=body,
                        source_line=node.start_point[0])

    def _lift_class_body(self, node) -> list:
        result = []
        for child in node.children:
            r = self._lift_node(child)
            if r:
                result.append(r)
        return result

    def _lift_method_declaration(self, node) -> FunctionDef:
        name = ""
        params = []
        body = []
        return_type = None
        modifiers = []
        for child in node.children:
            if child.type == "modifiers":
                modifiers = [self._text(c) for c in child.children if c.is_named]
            elif child.type in ("type_identifier", "integral_type", "floating_point_type",
                                 "boolean_type", "void_type", "generic_type"):
                return_type = self._text(child)
            elif child.type == "identifier":
                name = self._text(child)
            elif child.type == "formal_parameters":
                params = self._lift_formal_params(child)
            elif child.type == "block":
                body = self._lift_block(child)
        return FunctionDef(
            name=name, params=params, body=body,
            return_type=return_type,
            is_static="static" in modifiers,
            access_modifier="public" if "public" in modifiers else "private",
            source_line=node.start_point[0],
        )

    def _lift_formal_params(self, node) -> List[Param]:
        params = []
        for child in node.children:
            if child.type == "formal_parameter":
                p = self._lift_formal_parameter(child)
                if p:
                    params.append(p)
        return params

    def _lift_formal_parameter(self, node) -> Optional[Param]:
        type_ann = None
        name = ""
        for child in node.children:
            if child.type in ("type_identifier", "integral_type", "floating_point_type",
                               "boolean_type", "generic_type", "array_type"):
                type_ann = self._text(child)
            elif child.type == "identifier":
                name = self._text(child)
        return Param(name=name, type_annotation=type_ann) if name else None

    def _lift_block(self, node) -> list:
        result = []
        for child in node.children:
            if child.type in ("{", "}"):
                continue
            r = self._lift_node(child)
            if r:
                result.append(r)
        return result

    def _lift_local_variable_declaration(self, node) -> Optional[CanonicalNode]:
        type_ann = None
        name = ""
        value = None
        for child in node.children:
            if child.type in ("type_identifier", "integral_type", "floating_point_type",
                               "boolean_type", "generic_type", "array_type"):
                type_ann = self._text(child)
            elif child.type == "variable_declarator":
                for c in child.children:
                    if c.type == "identifier":
                        name = self._text(c)
                    elif c.type not in ("=",):
                        value = self._lift_expr(c)
        if name:
            return VarDecl(name=name, type_annotation=type_ann, value=value,
                           source_line=node.start_point[0])
        return None

    def _lift_expression_statement(self, node) -> Optional[CanonicalNode]:
        for child in node.children:
            if child.type != ";":
                expr = self._lift_expr(child)
                if expr:
                    # Detect System.out.println
                    if isinstance(expr, Call):
                        func = expr.func
                        if isinstance(func, Attribute) and func.attr in ("println", "print"):
                            if isinstance(func.obj, Attribute) and func.obj.attr == "out":
                                return PrintStmt(args=expr.args,
                                                  source_line=node.start_point[0])
                    return ExprStmt(expr=expr, source_line=node.start_point[0])
        return None

    def _lift_if_statement(self, node) -> Optional[IfStmt]:
        condition = None
        then_body = []
        else_body = []
        for child in node.children:
            if child.type == "parenthesized_expression":
                for c in child.children:
                    if c.type not in ("(", ")"):
                        condition = self._lift_expr(c)
            elif child.type == "block" and condition is not None and not then_body:
                then_body = self._lift_block(child)
            elif child.type in ("block", "if_statement") and then_body:
                if child.type == "block":
                    else_body = self._lift_block(child)
                else:
                    else_body = [self._lift_node(child)]
        return IfStmt(condition=condition, then_body=then_body,
                      else_body=else_body, source_line=node.start_point[0])

    def _lift_while_statement(self, node) -> Optional[WhileLoop]:
        condition = None
        body = []
        for child in node.children:
            if child.type == "parenthesized_expression":
                for c in child.children:
                    if c.type not in ("(", ")"):
                        condition = self._lift_expr(c)
            elif child.type == "block":
                body = self._lift_block(child)
        return WhileLoop(condition=condition, body=body,
                          source_line=node.start_point[0])

    def _lift_for_statement(self, node) -> Optional[CanonicalNode]:
        # Enhanced for: for (Type x : iterable)
        children = list(node.children)
        text = self._text(node)
        if ":" in text:
            # Enhanced for loop
            target = ""
            iterable = None
            body = []
            target_type = None
            for child in children:
                if child.type == "enhanced_for_statement":
                    return self._lift_node(child)
            # Parse manually
            in_parens = False
            for child in children:
                if child.type == "block":
                    body = self._lift_block(child)
            return ForEachLoop(target=target, iterable=iterable, body=body,
                               source_line=node.start_point[0])
        # Standard for loop
        init = None
        cond = None
        upd = None
        body = []
        for child in children:
            if child.type == "block":
                body = self._lift_block(child)
        return ForLoop(init=init, condition=cond, update=upd, body=body,
                       source_line=node.start_point[0])

    def _lift_enhanced_for_statement(self, node) -> ForEachLoop:
        target_type = None
        target = ""
        iterable = None
        body = []
        for child in node.children:
            if child.type in ("type_identifier", "integral_type", "generic_type"):
                target_type = self._text(child)
            elif child.type == "identifier" and not target:
                target = self._text(child)
            elif child.type not in ("for", "(", ":", ")", ";") and child.is_named:
                if target and iterable is None:
                    iterable = self._lift_expr(child)
            elif child.type == "block":
                body = self._lift_block(child)
        return ForEachLoop(target=target, target_type=target_type,
                           iterable=iterable, body=body,
                           source_line=node.start_point[0])

    def _lift_return_statement(self, node) -> Return:
        value = None
        for child in node.children:
            if child.type not in ("return", ";"):
                value = self._lift_expr(child)
        return Return(value=value, source_line=node.start_point[0])

    def _lift_break_statement(self, node) -> Break:
        return Break(source_line=node.start_point[0])

    def _lift_continue_statement(self, node) -> Continue:
        return Continue(source_line=node.start_point[0])

    def _lift_try_statement(self, node) -> TryExcept:
        try_body = []
        handlers = []
        finally_body = []
        for child in node.children:
            if child.type == "block" and not try_body:
                try_body = self._lift_block(child)
            elif child.type == "catch_clause":
                handlers.append(self._lift_catch_clause(child))
            elif child.type == "finally_clause":
                for c in child.children:
                    if c.type == "block":
                        finally_body = self._lift_block(c)
        return TryExcept(try_body=try_body, handlers=handlers,
                          finally_body=finally_body, source_line=node.start_point[0])

    def _lift_catch_clause(self, node) -> ExceptHandler:
        exc_type = None
        name = None
        body = []
        for child in node.children:
            if child.type == "catch_formal_parameter":
                for c in child.children:
                    if c.type == "catch_type":
                        exc_type = self._text(c).strip()
                    elif c.type == "identifier":
                        name = self._text(c)
            elif child.type == "block":
                body = self._lift_block(child)
        return ExceptHandler(exception_type=exc_type, name=name, body=body)

    def _lift_throw_statement(self, node) -> Raise:
        exc = None
        for child in node.children:
            if child.type not in ("throw", ";"):
                exc = self._lift_expr(child)
        return Raise(exception=exc, source_line=node.start_point[0])

    # ── Expressions ───────────────────────────────────────────────────────

    def _lift_expr(self, node) -> Optional[CanonicalNode]:
        if node is None:
            return None
        method = f"_expr_{node.type}"
        handler = getattr(self, method, self._expr_generic)
        return handler(node)

    def _parse_number(self, text: str):
        """Parse numeric literals, handling Java suffixes (L, F, D) and hex/octal."""
        text = text.strip()
        # Remove Java numeric suffixes
        if text and text[-1] in 'LlFfDd':
            text = text[:-1]
        # Try int with base detection (handles 0x, 0o, 0b)
        try:
            return int(text, 0)
        except ValueError:
            pass
        # Fall back to float
        try:
            return float(text)
        except ValueError:
            return None

    def _expr_generic(self, node) -> Optional[CanonicalNode]:
        text = self._text(node).strip()
        if not text:
            return None
        # Try to parse as number
        num_val = self._parse_number(text)
        if num_val is not None:
            kind = "float" if isinstance(num_val, float) else "int"
            return Literal(value=num_val, kind=kind)
        if text in ("null", "NULL"):
            return Literal(value=None, kind="null")
        if text in ("true", "True"):
            return Literal(value=True, kind="bool")
        if text in ("false", "False"):
            return Literal(value=False, kind="bool")
        return Name(id=text)

    def _expr_identifier(self, node) -> Name:
        return Name(id=self._text(node))

    def _expr_decimal_integer_literal(self, node) -> Literal:
        return Literal(value=int(self._text(node)), kind="int")

    def _expr_decimal_floating_point_literal(self, node) -> Literal:
        return Literal(value=float(self._text(node).rstrip("fFdD")), kind="float")

    def _expr_string_literal(self, node) -> Literal:
        text = self._text(node)
        # Remove surrounding quotes
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return Literal(value=text, kind="string")

    def _expr_true(self, node) -> Literal:
        return Literal(value=True, kind="bool")

    def _expr_false(self, node) -> Literal:
        return Literal(value=False, kind="bool")

    def _expr_null_literal(self, node) -> Literal:
        return Literal(value=None, kind="null")

    def _expr_binary_expression(self, node) -> BinaryOp:
        children = [c for c in node.children if c.is_named or c.type not in ("(", ")")]
        op = ""
        left = None
        right = None
        for child in node.children:
            if child.type in ("+", "-", "*", "/", "%", "==", "!=", "<", ">", "<=", ">=",
                               "&&", "||", "&", "|", "^", "<<", ">>"):
                op = child.type
            elif left is None:
                left = self._lift_expr(child)
            else:
                right = self._lift_expr(child)
        # Map Java ops to canonical ops
        op_map = {"&&": "and", "||": "or"}
        op = op_map.get(op, op)
        return BinaryOp(left=left, op=op, right=right)

    def _expr_method_invocation(self, node) -> Call:
        func = None
        args = []
        for child in node.children:
            if child.type == "argument_list":
                for c in child.children:
                    if c.type not in ("(", ")", ","):
                        arg = self._lift_expr(c)
                        if arg:
                            args.append(arg)
            elif child.type == "identifier" and func is None:
                func = Name(id=self._text(child))
            elif child.type == "field_access":
                func = self._expr_field_access(child)
        return Call(func=func, args=args)

    def _expr_field_access(self, node) -> Attribute:
        obj = None
        attr = ""
        for child in node.children:
            if child.type == "identifier" and not attr:
                if obj is None:
                    obj = Name(id=self._text(child))
                else:
                    attr = self._text(child)
            elif child.type == "." :
                pass
            elif child.type == "this":
                obj = Name(id="this")
            elif obj is None:
                obj = self._lift_expr(child)
            else:
                attr = self._text(child)
        return Attribute(obj=obj, attr=attr)

    def _expr_parenthesized_expression(self, node) -> Optional[CanonicalNode]:
        for child in node.children:
            if child.type not in ("(", ")"):
                return self._lift_expr(child)
        return None

    def _expr_unary_expression(self, node) -> UnaryOp:
        op = ""
        operand = None
        for child in node.children:
            if child.type in ("-", "+", "!", "~"):
                op = child.type
            else:
                operand = self._lift_expr(child)
        op_map = {"!": "not"}
        op = op_map.get(op, op)
        return UnaryOp(op=op, operand=operand)

    def _expr_object_creation_expression(self, node) -> Call:
        # new ClassName(args)
        class_name = ""
        args = []
        for child in node.children:
            if child.type == "type_identifier":
                class_name = self._text(child)
            elif child.type == "argument_list":
                for c in child.children:
                    if c.type not in ("(", ")", ","):
                        arg = self._lift_expr(c)
                        if arg:
                            args.append(arg)
        return Call(func=Name(id=class_name), args=args)

    def _expr_array_access(self, node) -> Index:
        obj = None
        index = None
        for child in node.children:
            if child.type == "[":
                continue
            elif child.type == "]":
                continue
            elif obj is None:
                obj = self._lift_expr(child)
            else:
                index = self._lift_expr(child)
        return Index(obj=obj, index=index)

    def _expr_ternary_expression(self, node) -> Ternary:
        parts = [self._lift_expr(c) for c in node.children
                 if c.type not in ("?", ":") and c.is_named]
        condition = parts[0] if len(parts) > 0 else None
        true_val  = parts[1] if len(parts) > 1 else None
        false_val = parts[2] if len(parts) > 2 else None
        return Ternary(condition=condition, true_value=true_val, false_value=false_val)

    def _expr_assignment_expression(self, node) -> Assignment:
        target = None
        value = None
        for child in node.children:
            if child.type == "=":
                continue
            elif target is None:
                target = self._lift_expr(child)
            else:
                value = self._lift_expr(child)
        return Assignment(target=target, value=value)
