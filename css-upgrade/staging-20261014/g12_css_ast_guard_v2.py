"""Staging-only G12 AST writer guard V2: binds write receiver exactly once.

Synthetic regression tool. Do not import or execute the private CSS module.
This prototype does not prove exhaustive sink interception or Sheets/SQLite CAS.
"""
from __future__ import annotations
import ast
import copy
import hashlib

EXPECTED_SHA = "a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
PROTECTED_TABS = frozenset(("CSS Project Dashboard", "CSS Contract-SIF Tracker",
                            "CSS Contract-SIF Skipped", "CSS Manual Exclusions"))
PROTECTED_IDS = frozenset((948865119, 1618938211, 692581491, 1445506838))
SHEET_METHODS = frozenset(("clear","batch_clear","resize","sort","update",
                           "batch_update","update_cells","append_rows",
                           "delete_rows","insert_rows","format","batch_format"))
FUNCTION_WRITERS = frozenset(("set_with_dataframe","overwrite_dataframe",
                              "write_dataframe_to_sheet","sync_dataframe_to_sheet"))
SHEET_HINTS = ("ws","worksheet","sheet","spread")

def __g12_guard_sheet_writer__(worksheet, operation):
    try:
        title=getattr(worksheet,"title",None)
        sheet_id=getattr(worksheet,"id",None)
    except Exception as exc:
        raise RuntimeError("G12_GUARD_SHEET_IDENTITY_UNAVAILABLE") from exc
    if title in PROTECTED_TABS or sheet_id in PROTECTED_IDS:
        raise RuntimeError("G12_GUARD_PROTECTED_TAB_WRITE_DENIED")
    if not isinstance(title,str) or type(sheet_id) is not int:
        raise RuntimeError("G12_GUARD_UNKNOWN_WORKSHEET")
    return None

def _name(expr):
    if isinstance(expr,ast.Name):
        return expr.id
    if isinstance(expr,ast.Attribute):
        left=_name(expr.value)
        return left+"."+expr.attr if left else expr.attr
    return ""

class GuardTransformer(ast.NodeTransformer):
    def __init__(self, reserved_names):
        self.instrumented=[]
        self.unknown_calls=[]
        self.reserved=set(reserved_names)
        self.count=0
    def unique_target(self):
        while True:
            self.count+=1
            name="__g12_scoped_target_%d" % self.count
            if name not in self.reserved:
                self.reserved.add(name)
                return name
    def visit_Call(self, node):
        node=self.generic_visit(node)
        target=None
        method=_name(node.func).rsplit(".",1)[-1]
        if isinstance(node.func,ast.Name) and method in FUNCTION_WRITERS:
            if node.args:
                target=copy.deepcopy(node.args[0])
            else:
                self.unknown_calls.append({"line":node.lineno,"method":method,"receiver_shape":"MissingArgument"})
        elif isinstance(node.func,ast.Attribute) and method in SHEET_METHODS:
            owner=_name(node.func.value).lower()
            if any(h in owner for h in SHEET_HINTS):
                target=copy.deepcopy(node.func.value)
            else:
                self.unknown_calls.append({"line":node.lineno,"method":method,"receiver_shape":type(node.func.value).__name__})
        if target is None:
            return node
        # Bind the potentially effectful receiver ONCE before guard + write.
        name=self.unique_target()
        receiver=ast.Name(id=name,ctx=ast.Load())
        if isinstance(node.func,ast.Attribute):
            node.func.value=receiver
        else:
            node.args[0]=receiver
        guard=ast.Call(func=ast.Name(id="__g12_guard_sheet_writer__",ctx=ast.Load()),
                       args=[ast.Name(id=name,ctx=ast.Load()),ast.Constant(method)],
                       keywords=[])
        body=ast.Subscript(
            value=ast.Tuple(elts=[guard,node],ctx=ast.Load()),
            slice=ast.Constant(1),ctx=ast.Load())
        params=ast.arguments(posonlyargs=[],args=[ast.arg(arg=name)],vararg=None,
                             kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])
        wrapped=ast.Call(func=ast.Lambda(args=params,body=body),args=[target],keywords=[])
        ast.copy_location(wrapped,node)
        self.instrumented.append({"line":node.lineno,"method":method})
        return wrapped

def guard_ast(source:bytes,*,exact_sha:str|None=None,reject_unclassified:bool=False):
    digest=hashlib.sha256(source).hexdigest()
    if exact_sha is not None and digest!=exact_sha:
        raise ValueError("G12_SOURCE_FINGERPRINT_MISMATCH")
    tree=ast.parse(source)
    reserved={n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}
    reserved.update(n.arg for n in ast.walk(tree) if isinstance(n,ast.arg))
    transformer=GuardTransformer(reserved)
    staged=transformer.visit(tree)
    if reject_unclassified and transformer.unknown_calls:
        raise RuntimeError("G12_UNCLASSIFIED_WRITER_CANDIDATES")
    ast.fix_missing_locations(staged)
    compiled=compile(staged,"<staging-g12-v2>", "exec")
    by_method={}
    for item in transformer.instrumented:
        by_method[item["method"]]=by_method.get(item["method"],0)+1
    unknown_by_method={}
    for item in transformer.unknown_calls:
        method=item["method"]
        unknown_by_method[method]=unknown_by_method.get(method,0)+1
    unknown_shapes={}
    for item in transformer.unknown_calls:
        shape=item["receiver_shape"]
        unknown_shapes[shape]=unknown_shapes.get(shape,0)+1
    return compiled,{
        "source_sha256":digest,
        "known_writer_calls_instrumented":len(transformer.instrumented),
        "method_counts":dict(sorted(by_method.items())),
        "unknown_writer_candidates":len(transformer.unknown_calls),
        "unknown_method_counts":dict(sorted(unknown_by_method.items())),
        "unknown_receiver_shapes":dict(sorted(unknown_shapes.items())),
        "runtime_guard_executed_on_real_css":False,
        "unknown_sites_require_review":bool(transformer.unknown_calls),
        "expression_receiver_evaluated_once_in_wrapped_sites":True,
        "all_sink_coverage_proven":False,
        "operational_source_or_db_modified":False,
    }
