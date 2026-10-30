"""Composable building modules and their connection graph."""

from .model import Assembly, ClearanceZone, Connection, ConnectionAnchor, Module
from .operations import connect_modules, disconnect_modules, replace_module, split_assembly
from .adapters import corridor_module, hall_module
from .validation import ValidationIssue, render_assembly, validate_assembly

__all__ = [
    "Assembly",
    "ClearanceZone",
    "Connection",
    "ConnectionAnchor",
    "Module",
    "connect_modules",
    "disconnect_modules",
    "replace_module",
    "split_assembly",
    "ValidationIssue",
    "render_assembly",
    "validate_assembly",
    "corridor_module",
    "hall_module",
]
