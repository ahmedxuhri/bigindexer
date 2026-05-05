"""
Gate 1 — MappingRule engine (language-agnostic).
Rules are applied per-node during AST traversal.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from tree_sitter import Node

from bgi.core.cov import COV


@dataclass
class MappingRule:
    tier: int
    token: COV
    confidence: float
    matcher: Callable[[Node], bool]
    description: str = ""


def dedupe_ordered(tokens: list[COV]) -> list[COV]:
    """Remove duplicate tokens while preserving first-occurrence order."""
    seen: set[COV] = set()
    result: list[COV] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def node_text(node: Node) -> str:
    return node.text.decode("utf-8") if node.text else ""


def call_attribute_name(call_node: Node) -> str | None:
    """
    For a call node like `obj.save(...)`, return the method name ('save').
    For a plain call like `print(...)`, return the function name ('print').
    """
    func = call_node.child_by_field_name("function")
    if func is None:
        return None
    if func.type == "attribute":
        attr = func.child_by_field_name("attribute")
        return node_text(attr) if attr else None
    if func.type == "identifier":
        return node_text(func)
    return None


def call_object_name(call_node: Node) -> str | None:
    """
    For `logging.info(...)`, return the object name ('logging').
    For `logger.error(...)`, return 'logger'.
    """
    func = call_node.child_by_field_name("function")
    if func is None:
        return None
    if func.type == "attribute":
        obj = func.child_by_field_name("object")
        return node_text(obj) if obj else None
    return None


def decorator_name(decorator_node: Node) -> str:
    """Return the full text of a decorator node (without the @)."""
    text = node_text(decorator_node)
    return text.lstrip("@").strip()
