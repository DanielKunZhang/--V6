#!/usr/bin/env python3
"""Lightweight regression checks for ic_monitor.py."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MONITOR_PATH = ROOT / "ic_monitor.py"


def _target_names(target):
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for item in target.elts:
            yield from _target_names(item)


def _assigned_names(node):
    for child in ast.walk(node):
        if isinstance(child, ast.Assign):
            for target in child.targets:
                yield from _target_names(target)
        elif isinstance(child, ast.AnnAssign):
            yield from _target_names(child.target)
        elif isinstance(child, ast.AugAssign):
            yield from _target_names(child.target)
        elif isinstance(child, ast.For):
            yield from _target_names(child.target)
        elif isinstance(child, ast.NamedExpr):
            yield from _target_names(child.target)
        elif isinstance(child, (ast.With, ast.AsyncWith)):
            for item in child.items:
                if item.optional_vars:
                    yield from _target_names(item.optional_vars)


def _find_method(tree, class_name, method_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    raise AssertionError(f"{class_name}.{method_name} not found")


def test_send_daily_report_does_not_shadow_helpers():
    tree = ast.parse(MONITOR_PATH.read_text(encoding="utf-8"))
    method = _find_method(tree, "MonitorReporter", "send_daily_report")
    helper_names = {
        item.name
        for item in method.body
        if isinstance(item, ast.FunctionDef)
    }
    shadowed = sorted(helper_names.intersection(_assigned_names(method)))
    assert not shadowed, f"helper function names shadowed by local assignments: {shadowed}"


if __name__ == "__main__":
    test_send_daily_report_does_not_shadow_helpers()
    print("✅ ic_monitor static regression checks passed")
