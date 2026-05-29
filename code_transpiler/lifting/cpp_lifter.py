"""
lifting/cpp_lifter.py
======================
Lifts a C++ tree-sitter CST into the Canonical IR.

Inherits everything from CLifter and adds C++-specific handling:
- Namespaces (using namespace std)
- Classes (class/struct with access specifiers)
- Templates (basic handling)
- std::cout → PrintStmt
- new/delete expressions
- References (&), override, virtual, etc.
"""

from __future__ import annotations
from typing import Optional

from ir.nodes import (
    Module, FunctionDef, ClassDef, Param, VarDecl,
    Assignment, Return, ExprStmt, Import, PrintStmt,
    Name, Literal, BinaryOp, Call, Attribute,
    CanonicalNode,
)
from lifting.c_lifter import CLifter


class CppLifter(CLifter):
    """
    Converts C++ tree-sitter CST → Canonical IR.
    Inherits all C handling and extends it for C++ constructs.
    """

    def lift(self, tree, source_code: str = "") -> Module:
        """Entry point: lift a full C++ parse tree."""
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

    # ── C++ specific statements ───────────────────────────────────────────────

    def _lift_namespace_definition(self, node) -> Optional[list]:
        """namespace foo { ... } — lift contents, discard namespace wrapper"""
        body = []
        for child in node.children:
            if child.type == "declaration_list":
                for c in child.children:
                    r = self._lift_node(c)
                    if r:
                        body.append(r)
        return body if body else None

    def _lift_using_declaration(self, node) -> None:
        """using namespace std; — skip"""
        return None

    def _lift_class_specifier(self, node) -> ClassDef:
        """class Foo : public Bar { ... }"""
        name = ""
        bases = []
        body = []
        for child in node.children:
            if child.type == "type_identifier":
                if not name:
                    name = self._text(child)
                else:
                    bases.append(self._text(child))
            elif child.type == "base_class_clause":
                for c in child.children:
                    if c.type == "type_identifier":
                        bases.append(self._text(c))
            elif child.type == "field_declaration_list":
                body = self._lift_class_body(child)
        return ClassDef(name=name, bases=bases, body=body,
                        source_line=node.start_point[0])

    def _lift_class_body(self, node) -> list:
        result = []
        for child in node.children:
            if child.type in ("{", "}", "access_specifier"):
                continue
            r = self._lift_node(child)
            if r:
                result.append(r)
        return result

    def _lift_template_declaration(self, node) -> Optional[CanonicalNode]:
        """template<typename T> — lift the inner declaration, ignore template"""
        for child in node.children:
            if child.type in ("function_definition", "class_specifier",
                               "struct_specifier"):
                return self._lift_node(child)
        return None

    def _lift_function_definition(self, node) -> FunctionDef:
        """Same as C, but also handles constructor_or_destructor."""
        return super()._lift_function_definition(node)

    # ── C++ expression overrides ──────────────────────────────────────────────

    def _lift_expression_statement(self, node) -> Optional[CanonicalNode]:
        for child in node.children:
            if child.type == ";":
                continue
            expr = self._lift_expr(child)
            if expr:
                # Map std::cout << x → PrintStmt
                if isinstance(expr, BinaryOp) and expr.op == "<<":
                    # Traverse to leftmost leaf
                    leftmost = expr
                    while isinstance(leftmost, BinaryOp) and leftmost.op == "<<":
                        leftmost = leftmost.left
                        
                    if isinstance(leftmost, Attribute) and leftmost.attr == "cout":
                        args = self._flatten_cout(expr)
                        return PrintStmt(args=args,
                                         source_line=node.start_point[0])
                    if isinstance(leftmost, Name) and leftmost.id in ("cout", "wcout"):
                        args = self._flatten_cout(expr)
                        return PrintStmt(args=args,
                                         source_line=node.start_point[0])
                # Map printf too (inherited logic)
                if isinstance(expr, Call):
                    func = expr.func
                    if isinstance(func, Name) and func.id in ("printf", "puts"):
                        args = expr.args[1:] if len(expr.args) > 1 else expr.args
                        return PrintStmt(args=args,
                                         source_line=node.start_point[0])
                return ExprStmt(expr=expr, source_line=node.start_point[0])
        return None

    def _flatten_cout(self, expr) -> list:
        """
        Flatten chained cout << a << b << c into [a, b, c].
        Drops endl / '\\n' literals.
        """
        args = []
        node = expr
        while isinstance(node, BinaryOp) and node.op == "<<":
            right = node.right
            if not self._is_endl(right):
                args.insert(0, right)
            node = node.left
        # node is now the cout Name/Attribute — skip it
        return args

    def _is_endl(self, node) -> bool:
        if isinstance(node, Name) and node.id in ("endl", "ends", "flush"):
            return True
        if isinstance(node, Literal) and isinstance(node.value, str):
            return node.value.strip() in ("\\n", "\\r\\n", "")
        return False

    def _expr_new_expression(self, node) -> Call:
        """new Foo(args) → Call(Name('Foo'), args)"""
        class_name = ""
        args = []
        for child in node.children:
            if child.type == "type_identifier":
                class_name = self._text(child)
            elif child.type == "argument_list":
                for c in child.children:
                    if c.type not in ("(", ")", ","):
                        a = self._lift_expr(c)
                        if a:
                            args.append(a)
        return Call(func=Name(id=class_name), args=args)

    def _expr_delete_expression(self, node) -> None:
        """delete ptr — skip (Python GC handles this)"""
        return None

    def _expr_reference_declarator(self, node) -> Optional[CanonicalNode]:
        """&x — just return x"""
        for child in node.children:
            if child.type not in ("&",):
                return self._lift_expr(child)
        return None

    def _expr_scoped_identifier(self, node) -> Attribute:
        """std::cout → Attribute(Name('std'), 'cout')"""
        parts = []
        for child in node.children:
            if child.type not in ("::",):
                parts.append(self._text(child))
        if len(parts) >= 2:
            obj = Name(id=parts[0])
            return Attribute(obj=obj, attr="::".join(parts[1:]))
        return Name(id=parts[0] if parts else "")

    def _expr_scoped_namespace_identifier(self, node) -> Attribute:
        return self._expr_scoped_identifier(node)

    def _expr_this(self, node) -> Name:
        return Name(id="self")

    def _expr_nullptr(self, node) -> Literal:
        return Literal(value=None, kind="null")
