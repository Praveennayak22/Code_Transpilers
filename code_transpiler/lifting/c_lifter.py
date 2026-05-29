"""
lifting/c_lifter.py
====================
Lifts a C tree-sitter CST into the Canonical IR.

Handles the most common C constructs:
- Function definitions and declarations
- Variable declarations (with type)
- Control flow (if/else, for, while, do-while)
- Expressions (arithmetic, comparison, calls, pointer ops)
- Struct definitions
- #include / #define directives
- printf → PrintStmt mapping
- scanf → input() mapping
"""

from __future__ import annotations
from typing import Optional, List

from ir.nodes import (
    Module, FunctionDef, ClassDef, Param, VarDecl,
    Assignment, Return, IfStmt, WhileLoop, ForLoop,
    Break, Continue, ExprStmt, Import, PrintStmt,
    Name, Literal, BinaryOp, UnaryOp, Call, Attribute,
    Index, AugAssignment, CanonicalNode,
)


class CLifter:
    """Converts C tree-sitter CST → Canonical IR."""

    def lift(self, tree, source_code: str = "") -> Module:
        """Entry point: lift a full C parse tree."""
        self._source_bytes = source_code.encode("utf-8") if source_code else b""
        root = tree.root_node
        body = []
        imports = []
        for child in root.children:
            result = self._lift_node(child)
            if result is None:
                continue
            if isinstance(result, Import):
                imports.append(result)
            elif isinstance(result, list):
                body.extend(result)
            else:
                body.append(result)
        return Module(body=body, imports=imports)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _text(self, node) -> str:
        if self._source_bytes:
            return self._source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        return node.type

    def _lift_node(self, node) -> Optional[CanonicalNode]:
        method = f"_lift_{node.type}"
        handler = getattr(self, method, self._lift_generic)
        return handler(node)

    def _lift_generic(self, node) -> None:
        return None

    def _lift_expr(self, node) -> Optional[CanonicalNode]:
        if node is None:
            return None
        method = f"_expr_{node.type}"
        handler = getattr(self, method, self._expr_generic)
        return handler(node)

    def _lift_block(self, node) -> list:
        result = []
        for child in node.children:
            if child.type in ("{", "}"):
                continue
            r = self._lift_node(child)
            if r:
                result.append(r)
        return result

    # ── Top-level declarations ────────────────────────────────────────────────

    def _lift_preproc_include(self, node) -> Import:
        text = self._text(node).strip()
        # #include <stdio.h>  or  #include "myfile.h"
        module = text.replace("#include", "").strip().strip("<>\"")
        return Import(module=module, source_line=node.start_point[0])

    def _lift_preproc_def(self, node) -> None:
        # #define MAX 100 — skip for now (could map to constant VarDecl)
        return None

    def _lift_comment(self, node) -> None:
        return None

    def _lift_function_definition(self, node) -> FunctionDef:
        name = ""
        params = []
        body = []
        return_type = None
        for child in node.children:
            if child.type == "function_declarator":
                for c in child.children:
                    if c.type == "identifier":
                        name = self._text(c)
                    elif c.type == "parameter_list":
                        params = self._lift_parameter_list(c)
            elif child.type in ("primitive_type", "type_identifier",
                                "pointer_declarator"):
                return_type = self._text(child).replace("*", "").strip()
            elif child.type == "compound_statement":
                body = self._lift_block(child)
        return FunctionDef(
            name=name, params=params, body=body,
            return_type=return_type,
            source_line=node.start_point[0],
        )

    def _lift_parameter_list(self, node) -> List[Param]:
        params = []
        for child in node.children:
            if child.type == "parameter_declaration":
                p = self._lift_parameter_declaration(child)
                if p:
                    params.append(p)
        return params

    def _lift_parameter_declaration(self, node) -> Optional[Param]:
        type_ann = None
        name = ""
        for child in node.children:
            if child.type in ("primitive_type", "type_identifier"):
                type_ann = self._text(child)
            elif child.type == "identifier":
                name = self._text(child)
            elif child.type == "pointer_declarator":
                # int *ptr
                for c in child.children:
                    if c.type == "identifier":
                        name = self._text(c)
                if type_ann:
                    type_ann = type_ann + "*"
        return Param(name=name, type_annotation=type_ann) if name else None

    def _lift_declaration(self, node) -> Optional[CanonicalNode]:
        """int x = 5; or int x;"""
        type_ann = None
        name = ""
        value = None
        for child in node.children:
            if child.type in ("primitive_type", "type_identifier"):
                type_ann = self._text(child)
            elif child.type == "init_declarator":
                for c in child.children:
                    if c.type == "identifier":
                        name = self._text(c)
                    elif c.type not in ("=",):
                        value = self._lift_expr(c)
            elif child.type == "identifier":
                name = self._text(child)
        if name:
            return VarDecl(name=name, type_annotation=type_ann, value=value,
                           source_line=node.start_point[0])
        return None

    # ── Statements ────────────────────────────────────────────────────────────

    def _lift_expression_statement(self, node) -> Optional[CanonicalNode]:
        for child in node.children:
            if child.type == ";":
                continue
            expr = self._lift_expr(child)
            if expr:
                # Map printf to PrintStmt
                if isinstance(expr, Call):
                    func = expr.func
                    if isinstance(func, Name) and func.id in ("printf", "puts"):
                        args = expr.args[1:] if len(expr.args) > 1 else expr.args
                        return PrintStmt(args=args, source_line=node.start_point[0])
                return ExprStmt(expr=expr, source_line=node.start_point[0])
        return None

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

    def _lift_if_statement(self, node) -> IfStmt:
        condition = None
        then_body = []
        else_body = []
        
        # Track which part we're parsing (0=cond, 1=then, 2=else)
        section = 0
        for child in node.children:
            if child.type in ("if", "(", ")", "else"):
                if child.type == "else":
                    section = 2
                continue
            
            if child.type in ("parenthesized_expression", "condition_clause"):
                for c in child.children:
                    if c.type not in ("(", ")"):
                        condition = self._lift_expr(c)
                section = 1
            elif section == 1:
                # Then body
                if child.type == "compound_statement":
                    then_body = self._lift_block(child)
                else:
                    r = self._lift_node(child)
                    if r: then_body.append(r)
            elif section == 2:
                # Else body
                if child.type == "else_clause":
                    # For some reason tree-sitter might wrap it in an else_clause
                    for c in child.children:
                        if c.type not in ("else",):
                            if c.type == "compound_statement":
                                else_body = self._lift_block(c)
                            else:
                                r = self._lift_node(c)
                                if r: else_body.append(r)
                elif child.type == "compound_statement":
                    else_body = self._lift_block(child)
                else:
                    r = self._lift_node(child)
                    if r: else_body.append(r)
                    
        return IfStmt(condition=condition, then_body=then_body,
                      else_body=else_body, source_line=node.start_point[0])

    def _lift_while_statement(self, node) -> WhileLoop:
        condition = None
        body = []
        section = 0 # 0=cond, 1=body
        for child in node.children:
            if child.type in ("while", "(", ")"):
                continue
            if child.type in ("parenthesized_expression", "condition_clause"):
                for c in child.children:
                    if c.type not in ("(", ")"):
                        condition = self._lift_expr(c)
                section = 1
            elif section == 1:
                if child.type == "compound_statement":
                    body = self._lift_block(child)
                else:
                    r = self._lift_node(child)
                    if r: body.append(r)
        return WhileLoop(condition=condition, body=body,
                         source_line=node.start_point[0])

    def _lift_for_statement(self, node) -> ForLoop:
        init = None
        condition = None
        update = None
        body = []
        children = list(node.children)
        # for ( init ; condition ; update ) body
        section = 0  # 0=pre, 1=init, 2=cond, 3=update
        for child in children:
            if child.type == "(":
                section = 1
            elif child.type == ";" and section == 1:
                section = 2
            elif child.type == ";" and section == 2:
                section = 3
            elif child.type == ")":
                section = 4
            elif child.type == "compound_statement":
                body = self._lift_block(child)
            elif section == 1 and child.type not in (";",):
                init = self._lift_node(child) or self._lift_expr(child)
            elif section == 2 and child.type not in (";",):
                condition = self._lift_expr(child)
            elif section == 3 and child.type not in (";",):
                update = self._lift_expr(child)
        return ForLoop(init=init, condition=condition, update=update,
                       body=body, source_line=node.start_point[0])

    def _lift_compound_statement(self, node) -> list:
        return self._lift_block(node)

    def _lift_struct_specifier(self, node) -> Optional[ClassDef]:
        name = ""
        body = []
        for child in node.children:
            if child.type == "type_identifier":
                name = self._text(child)
            elif child.type == "field_declaration_list":
                for c in child.children:
                    r = self._lift_node(c)
                    if r:
                        body.append(r)
        if name:
            return ClassDef(name=name, bases=[], body=body,
                            source_line=node.start_point[0])
        return None

    def _lift_field_declaration(self, node) -> Optional[VarDecl]:
        type_ann = None
        name = ""
        for child in node.children:
            if child.type in ("primitive_type", "type_identifier"):
                type_ann = self._text(child)
            elif child.type == "field_identifier":
                name = self._text(child)
        if name:
            return VarDecl(name=name, type_annotation=type_ann,
                           source_line=node.start_point[0])
        return None

    # ── Expressions ───────────────────────────────────────────────────────────

    def _expr_generic(self, node) -> Optional[CanonicalNode]:
        text = self._text(node).strip()
        if not text:
            return None
        try:
            return Literal(value=int(text, 0), kind="int")
        except (ValueError, TypeError):
            pass
        try:
            return Literal(value=float(text), kind="float")
        except (ValueError, TypeError):
            pass
        if text in ("NULL", "nullptr"):
            return Literal(value=None, kind="null")
        if text in ("true", "false"):
            return Literal(value=(text == "true"), kind="bool")
        return Name(id=text)

    def _expr_identifier(self, node) -> Name:
        return Name(id=self._text(node))

    def _expr_number_literal(self, node) -> Literal:
        text = self._text(node).rstrip("uUlLfF")
        try:
            return Literal(value=int(text, 0), kind="int")
        except (ValueError, TypeError):
            pass
        try:
            return Literal(value=float(text), kind="float")
        except (ValueError, TypeError):
            return Literal(value=text, kind="string")

    def _expr_string_literal(self, node) -> Literal:
        text = self._text(node)
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return Literal(value=text, kind="string")

    def _expr_char_literal(self, node) -> Literal:
        text = self._text(node).strip("'")
        return Literal(value=text, kind="string")

    def _expr_true(self, node) -> Literal:
        return Literal(value=True, kind="bool")

    def _expr_false(self, node) -> Literal:
        return Literal(value=False, kind="bool")

    def _expr_null(self, node) -> Literal:
        return Literal(value=None, kind="null")

    def _expr_parenthesized_expression(self, node) -> Optional[CanonicalNode]:
        for child in node.children:
            if child.type not in ("(", ")"):
                return self._lift_expr(child)
        return None

    def _expr_binary_expression(self, node) -> BinaryOp:
        op = ""
        left = None
        right = None
        for child in node.children:
            if child.type in ("+", "-", "*", "/", "%", "==", "!=",
                               "<", ">", "<=", ">=", "&&", "||",
                               "&", "|", "^", "<<", ">>"):
                op = child.type
            elif left is None:
                left = self._lift_expr(child)
            else:
                right = self._lift_expr(child)
        op_map = {"&&": "and", "||": "or"}
        return BinaryOp(left=left, op=op_map.get(op, op), right=right)

    def _expr_unary_expression(self, node) -> UnaryOp:
        op = ""
        operand = None
        for child in node.children:
            if child.type in ("-", "+", "!", "~", "*", "&"):
                op = child.type
            else:
                operand = self._lift_expr(child)
        op_map = {"!": "not", "*": "deref", "&": "addr"}
        return UnaryOp(op=op_map.get(op, op), operand=operand)

    def _expr_assignment_expression(self, node) -> Assignment:
        target = None
        value = None
        for child in node.children:
            if child.type == "=":
                continue
            elif child.type in ("+=", "-=", "*=", "/=", "%="):
                op = child.type[0]
                # turn into AugAssignment below
                continue
            elif target is None:
                target = self._lift_expr(child)
            else:
                value = self._lift_expr(child)
        return Assignment(target=target, value=value,
                          source_line=node.start_point[0])

    def _expr_update_expression(self, node) -> AugAssignment:
        """i++ or ++i → i += 1"""
        operand = None
        for child in node.children:
            if child.type not in ("++", "--"):
                operand = self._lift_expr(child)
        op = "+=" if "++" in self._text(node) else "-="
        return AugAssignment(target=operand, op=op,
                             value=Literal(value=1, kind="int"),
                             source_line=node.start_point[0])

    def _expr_call_expression(self, node) -> Call:
        func = None
        args = []
        for child in node.children:
            if child.type == "argument_list":
                for c in child.children:
                    if c.type not in ("(", ")", ","):
                        a = self._lift_expr(c)
                        if a:
                            args.append(a)
            elif func is None:
                func = self._lift_expr(child)
        return Call(func=func, args=args, source_line=node.start_point[0])

    def _expr_field_expression(self, node) -> Attribute:
        """struct.member or ptr->member"""
        obj = None
        attr = ""
        for child in node.children:
            if child.type in (".", "->"):
                continue
            elif obj is None:
                obj = self._lift_expr(child)
            else:
                attr = self._text(child)
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

    def _expr_cast_expression(self, node) -> Optional[CanonicalNode]:
        """(int)x → just lift the inner expression, drop the cast"""
        for child in node.children:
            if child.type not in ("(", ")", "type_descriptor"):
                return self._lift_expr(child)
        return None

    def _expr_pointer_expression(self, node) -> Optional[CanonicalNode]:
        """*ptr or &var — just lift the inner value"""
        for child in node.children:
            if child.type not in ("*", "&"):
                return self._lift_expr(child)
        return None

    def _expr_conditional_expression(self, node) -> Optional[CanonicalNode]:
        """a ? b : c"""
        from ir.nodes import Ternary
        parts = [self._lift_expr(c) for c in node.children
                 if c.type not in ("?", ":") and c.is_named]
        cond      = parts[0] if len(parts) > 0 else None
        true_val  = parts[1] if len(parts) > 1 else None
        false_val = parts[2] if len(parts) > 2 else None
        return Ternary(condition=cond, true_value=true_val, false_value=false_val)
