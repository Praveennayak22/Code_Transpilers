"""
lifting/javascript_lifter.py
=============================
Lifts a JavaScript tree-sitter CST into the Canonical IR.

Handles common JavaScript constructs:
- Function declarations and arrow functions
- Class declarations
- Variable declarations (let, const, var)
- Control flow
- console.log → PrintStmt
"""

from __future__ import annotations
from typing import Optional, List

from ir.nodes import (
    Module, FunctionDef, ClassDef, Param, VarDecl,
    Assignment, Return, IfStmt, ElifClause,
    WhileLoop, ForLoop, ForEachLoop, Break, Continue,
    ExprStmt, TryExcept, ExceptHandler, Raise, Import, PrintStmt,
    Name, Literal, BinaryOp, UnaryOp, CompareOp, BoolOp,
    Call, Attribute, Index, Ternary, Lambda, ListLiteral,
    CanonicalNode, AugAssignment,
)


class JavaScriptLifter:
    """Converts JavaScript tree-sitter CST → Canonical IR."""

    def lift(self, tree, source_code: str = "") -> Module:
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
        if self._source_bytes:
            return self._source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        return node.type

    def _lift_node(self, node) -> Optional[CanonicalNode]:
        method = f"_lift_{node.type}"
        handler = getattr(self, method, self._lift_generic)
        return handler(node)

    def _lift_generic(self, node) -> Optional[CanonicalNode]:
        return None

    def _lift_block(self, node) -> list:
        result = []
        for child in node.children:
            if child.type in ("{", "}"):
                continue
            r = self._lift_node(child)
            if r:
                result.append(r)
        return result

    def _lift_statement_block(self, node) -> list:
        return self._lift_block(node)

    def _lift_program(self, node):
        results = []
        for child in node.children:
            r = self._lift_node(child)
            if r:
                results.append(r)
        return results

    def _lift_import_statement(self, node) -> Import:
        text = self._text(node)
        return Import(module=text, source_line=node.start_point[0])

    def _lift_function_declaration(self, node) -> FunctionDef:
        name = ""
        params = []
        body = []
        is_async = False
        for child in node.children:
            if child.type == "async":
                is_async = True
            elif child.type == "identifier":
                name = self._text(child)
            elif child.type == "formal_parameters":
                params = self._lift_formal_params(child)
            elif child.type == "statement_block":
                body = self._lift_block(child)
        return FunctionDef(name=name, params=params, body=body,
                            is_async=is_async, source_line=node.start_point[0])

    def _lift_formal_params(self, node) -> List[Param]:
        params = []
        for child in node.children:
            if child.type == "identifier":
                params.append(Param(name=self._text(child)))
            elif child.type == "assignment_pattern":
                # Default parameter: x = 5
                pname = ""
                pdefault = None
                for c in child.children:
                    if c.type == "identifier" and not pname:
                        pname = self._text(c)
                    elif c.type != "=":
                        pdefault = self._lift_expr(c)
                params.append(Param(name=pname, default_value=pdefault))
        return params

    def _lift_class_declaration(self, node) -> ClassDef:
        name = ""
        bases = []
        body = []
        for child in node.children:
            if child.type == "identifier":
                name = self._text(child)
            elif child.type == "class_heritage":
                for c in child.children:
                    if c.type == "identifier":
                        bases.append(self._text(c))
            elif child.type == "class_body":
                body = self._lift_class_body(child)
        return ClassDef(name=name, bases=bases, body=body,
                        source_line=node.start_point[0])

    def _lift_class_body(self, node) -> list:
        result = []
        for child in node.children:
            if child.type in ("{", "}"):
                continue
            r = self._lift_node(child)
            if r:
                result.append(r)
        return result

    def _lift_method_definition(self, node) -> FunctionDef:
        name = ""
        params = []
        body = []
        is_static = False
        is_async = False
        for child in node.children:
            if child.type == "static":
                is_static = True
            elif child.type == "async":
                is_async = True
            elif child.type == "property_identifier":
                name = self._text(child)
            elif child.type == "formal_parameters":
                params = self._lift_formal_params(child)
            elif child.type == "statement_block":
                body = self._lift_block(child)
        return FunctionDef(name=name, params=params, body=body,
                            is_static=is_static, is_async=is_async,
                            source_line=node.start_point[0])

    def _lift_variable_declaration(self, node) -> Optional[CanonicalNode]:
        is_const = False
        for child in node.children:
            if child.type == "const":
                is_const = True
            elif child.type == "variable_declarator":
                name = ""
                value = None
                for c in child.children:
                    if c.type == "identifier":
                        name = self._text(c)
                    elif c.type != "=":
                        value = self._lift_expr(c)
                return VarDecl(name=name, value=value, is_const=is_const,
                                source_line=node.start_point[0])
        return None

    def _lift_lexical_declaration(self, node) -> Optional[CanonicalNode]:
        return self._lift_variable_declaration(node)

    def _lift_expression_statement(self, node) -> Optional[CanonicalNode]:
        for child in node.children:
            if child.type == ";":
                continue
            expr = self._lift_expr(child)
            if expr:
                # Detect console.log
                if isinstance(expr, Call):
                    if isinstance(expr.func, Attribute) and expr.func.attr == "log":
                        if isinstance(expr.func.obj, Attribute) and expr.func.obj.attr == "console":
                            return PrintStmt(args=expr.args, source_line=node.start_point[0])
                        elif isinstance(expr.func.obj, Name) and expr.func.obj.id == "console":
                            return PrintStmt(args=expr.args, source_line=node.start_point[0])
                return ExprStmt(expr=expr, source_line=node.start_point[0])
        return None

    def _lift_if_statement(self, node) -> IfStmt:
        condition = None
        then_body = []
        else_body = []
        elif_clauses = []
        for child in node.children:
            if child.type == "parenthesized_expression":
                for c in child.children:
                    if c.type not in ("(", ")"):
                        condition = self._lift_expr(c)
            elif child.type == "statement_block" and not then_body:
                then_body = self._lift_block(child)
            elif child.type == "else_clause":
                for c in child.children:
                    if c.type == "statement_block":
                        else_body = self._lift_block(c)
                    elif c.type == "if_statement":
                        else_body = [self._lift_node(c)]
        return IfStmt(condition=condition, then_body=then_body,
                      elif_clauses=elif_clauses, else_body=else_body,
                      source_line=node.start_point[0])

    def _lift_while_statement(self, node) -> WhileLoop:
        condition = None
        body = []
        for child in node.children:
            if child.type == "parenthesized_expression":
                for c in child.children:
                    if c.type not in ("(", ")"):
                        condition = self._lift_expr(c)
            elif child.type == "statement_block":
                body = self._lift_block(child)
        return WhileLoop(condition=condition, body=body, source_line=node.start_point[0])

    def _lift_for_in_statement(self, node) -> ForEachLoop:
        target = ""
        iterable = None
        body = []
        past_in = False
        for child in node.children:
            if child.type in ("for", "(", ")"):
                continue
            elif child.type in ("of", "in"):
                past_in = True
            elif not past_in and child.type == "identifier":
                target = self._text(child)
            elif past_in and iterable is None:
                iterable = self._lift_expr(child)
            elif child.type == "statement_block":
                body = self._lift_block(child)
        return ForEachLoop(target=target, iterable=iterable, body=body,
                           source_line=node.start_point[0])

    def _lift_for_statement(self, node) -> ForLoop:
        body = []
        for child in node.children:
            if child.type == "statement_block":
                body = self._lift_block(child)
        return ForLoop(body=body, source_line=node.start_point[0])

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
            if child.type == "statement_block" and not try_body:
                try_body = self._lift_block(child)
            elif child.type == "catch_clause":
                param = ""
                body = []
                for c in child.children:
                    if c.type == "identifier":
                        param = self._text(c)
                    elif c.type == "statement_block":
                        body = self._lift_block(c)
                handlers.append(ExceptHandler(name=param, body=body))
            elif child.type == "finally_clause":
                for c in child.children:
                    if c.type == "statement_block":
                        finally_body = self._lift_block(c)
        return TryExcept(try_body=try_body, handlers=handlers, finally_body=finally_body,
                          source_line=node.start_point[0])

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

    def _expr_generic(self, node) -> Optional[CanonicalNode]:
        text = self._text(node).strip()
        if not text or text in (";", ",", "{", "}"):
            return None
        # Complex multi-line or block expressions can't be a Name
        # (would produce raw JS syntax → Python syntax error)
        if "{" in text or "\n" in text or text.startswith("function"):
            return Literal(value=None, kind="null")
        try:
            return Literal(value=int(text, 0), kind="int")
        except ValueError:
            pass
        try:
            return Literal(value=float(text), kind="float")
        except ValueError:
            pass
        return Name(id=text)

    def _expr_identifier(self, node) -> Name:
        return Name(id=self._text(node))

    def _expr_number(self, node) -> Literal:
        text = self._text(node).strip()
        # Try int with base detection (handles 0x, 0o, 0b, decimal)
        try:
            return Literal(value=int(text, 0), kind="int")
        except ValueError:
            try:
                return Literal(value=float(text), kind="float")
            except ValueError:
                # Fallback for unparseable numbers
                return Literal(value=None, kind="null")

    def _expr_string(self, node) -> Literal:
        text = self._text(node)
        if (text.startswith('"') and text.endswith('"')) or \
           (text.startswith("'") and text.endswith("'")):
            text = text[1:-1]
        return Literal(value=text, kind="string")

    def _expr_true(self, node) -> Literal:
        return Literal(value=True, kind="bool")

    def _expr_false(self, node) -> Literal:
        return Literal(value=False, kind="bool")

    def _expr_null(self, node) -> Literal:
        return Literal(value=None, kind="null")

    def _expr_binary_expression(self, node) -> CanonicalNode:
        op = ""
        left = None
        right = None
        for child in node.children:
            if child.type in ("+", "-", "*", "/", "%", "===", "!==", "==", "!=",
                               "<", ">", "<=", ">=", "&&", "||", "&", "|", "^"):
                op = child.type
            elif left is None:
                left = self._lift_expr(child)
            else:
                right = self._lift_expr(child)
        op_map = {"===": "==", "!==": "!=", "&&": "and", "||": "or"}
        op = op_map.get(op, op)
        return BinaryOp(left=left, op=op, right=right)

    def _expr_call_expression(self, node) -> Call:
        func = None
        args = []
        for child in node.children:
            if child.type == "arguments":
                for c in child.children:
                    if c.type not in ("(", ")", ","):
                        arg = self._lift_expr(c)
                        if arg:
                            args.append(arg)
            elif func is None:
                func = self._lift_expr(child)
        return Call(func=func, args=args)

    def _expr_member_expression(self, node) -> Attribute:
        obj = None
        attr = ""
        for child in node.children:
            if child.type == ".":
                continue
            elif child.type == "property_identifier":
                attr = self._text(child)
            elif obj is None:
                obj = self._lift_expr(child)
        return Attribute(obj=obj, attr=attr)

    def _expr_subscript_expression(self, node) -> Index:
        obj = None
        index = None
        for child in node.children:
            if child.type in ("[", "]"):
                continue
            elif obj is None:
                obj = self._lift_expr(child)
            else:
                index = self._lift_expr(child)
        return Index(obj=obj, index=index)

    def _expr_unary_expression(self, node) -> UnaryOp:
        op = ""
        operand = None
        for child in node.children:
            if child.type in ("-", "+", "!", "~", "typeof", "void"):
                op = child.type
            else:
                operand = self._lift_expr(child)
        op_map = {"!": "not"}
        op = op_map.get(op, op)
        return UnaryOp(op=op, operand=operand)

    def _expr_ternary_expression(self, node) -> Ternary:
        parts = [self._lift_expr(c) for c in node.children
                 if c.type not in ("?", ":")]
        parts = [p for p in parts if p is not None]
        condition = parts[0] if len(parts) > 0 else None
        true_val  = parts[1] if len(parts) > 1 else None
        false_val = parts[2] if len(parts) > 2 else None
        return Ternary(condition=condition, true_value=true_val, false_value=false_val)

    def _expr_arrow_function(self, node) -> Lambda:
        params = []
        body_expr = None
        body_block = []
        for child in node.children:
            if child.type == "identifier":
                params.append(Param(name=self._text(child)))
            elif child.type == "formal_parameters":
                params = self._lift_formal_params(child)
            elif child.type == "statement_block":
                body_block = self._lift_block(child)
            elif child.type not in ("=>",):
                body_expr = self._lift_expr(child)
        # If block body has one return → simplify to lambda expression
        if body_block:
            returns = [s for s in body_block if isinstance(s, Return) and s.value]
            if len(returns) == 1 and len(body_block) == 1:
                body_expr = returns[0].value
            else:
                # Multi-statement block: wrap as FunctionDef stored as Lambda placeholder
                body_expr = Literal(value=None, kind="null")
        return Lambda(params=params, body=body_expr)

    def _expr_function_expression(self, node) -> CanonicalNode:
        """Handle anonymous function expressions used as callbacks.
        function(err, data) { ... } -> Lambda or None placeholder
        """
        params = []
        body_block = []
        for child in node.children:
            if child.type == "formal_parameters":
                params = self._lift_formal_params(child)
            elif child.type == "statement_block":
                body_block = self._lift_block(child)
        # Simple case: single return -> lambda
        if len(body_block) == 1 and isinstance(body_block[0], Return):
            body_expr = body_block[0].value or Literal(value=None, kind="null")
            return Lambda(params=params, body=body_expr)
        # Complex body: can't represent cleanly in Python, use None placeholder
        return Literal(value=None, kind="null")

    def _expr_template_string(self, node) -> Literal:
        """Handle JS template literals: `Hello ${name}` -> 'Hello {name}'.format()"""
        text = self._text(node)
        # Strip backticks
        if text.startswith("`") and text.endswith("`"):
            text = text[1:-1]
        # Replace ${expr} with {expr} (Python f-string style)
        import re
        text = re.sub(r'\$\{([^}]+)\}', r'{\1}', text)
        return Literal(value=text, kind="string")

    def _expr_array(self, node) -> ListLiteral:
        elements = []
        for child in node.children:
            if child.type not in ("[", "]", ","):
                elem = self._lift_expr(child)
                if elem:
                    elements.append(elem)
        return ListLiteral(elements=elements)

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

    def _expr_parenthesized_expression(self, node) -> Optional[CanonicalNode]:
        for child in node.children:
            if child.type not in ("(", ")"):
                return self._lift_expr(child)
        return None

    def _expr_new_expression(self, node) -> Call:
        class_name = ""
        args = []
        for child in node.children:
            if child.type == "identifier":
                class_name = self._text(child)
            elif child.type == "arguments":
                for c in child.children:
                    if c.type not in ("(", ")", ","):
                        arg = self._lift_expr(c)
                        if arg:
                            args.append(arg)
        return Call(func=Name(id=class_name), args=args)
