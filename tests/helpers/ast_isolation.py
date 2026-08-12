# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Static AST inspection backing write-isolation gate 3 (T014, FR-001).

This is a TEST-ONLY helper. Production code MUST NOT import it. It parses
a Python source file without executing it and reports what the module
imports and which attribute names it references, so a test can fail when
a polling-lifecycle module reaches for a write-capable symbol.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModuleFacts:
    """Names a module imports and attributes it references.

    Attributes:
        imported_modules: Dotted module paths named by any import.
        imported_names: Bare names bound by any import statement.
        attribute_names: Attribute names referenced anywhere.
        assigned_names: Attribute names that are assignment targets.
    """

    imported_modules: frozenset[str]
    imported_names: frozenset[str]
    attribute_names: frozenset[str]
    assigned_names: frozenset[str]

    def references(self, name: str) -> bool:
        """Return whether the module names ``name`` in any position.

        Args:
            name: Symbol or attribute name to look for.

        Returns:
            True when the name appears as an import, an imported name, or
            a referenced attribute.
        """
        return (
            name in self.imported_names
            or name in self.attribute_names
            or any(module.split(".")[-1] == name for module in self.imported_modules)
        )

    def imports_from(self, package: str) -> bool:
        """Return whether any import names ``package`` or a submodule.

        Args:
            package: Dotted package path.

        Returns:
            True when an import targets that package or below it.
        """
        return any(
            module == package or module.startswith(f"{package}.")
            for module in self.imported_modules
        )


def _collect_imports(
    tree: ast.AST,
) -> tuple[set[str], set[str]]:
    """Collect dotted module paths and bound names from import nodes.

    Args:
        tree: Parsed module tree.

    Returns:
        A pair of module paths and imported names.
    """
    modules: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if base:
                modules.add(base)
            for alias in node.names:
                names.add(alias.asname or alias.name)
                if base:
                    modules.add(f"{base}.{alias.name}")
    return modules, names


def scan_module(path: Path) -> ModuleFacts:
    """Parse one Python file and report its imports and attributes.

    Args:
        path: Source file to parse.

    Returns:
        Facts describing what the module names.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules, names = _collect_imports(tree)
    attributes: set[str] = set()
    assigned: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            attributes.add(node.attr)
            if isinstance(node.ctx, ast.Store):
                assigned.add(node.attr)
    return ModuleFacts(
        frozenset(modules), frozenset(names), frozenset(attributes), frozenset(assigned)
    )


def scan_paths(paths: list[Path]) -> dict[Path, ModuleFacts]:
    """Parse every Python file under the given files or directories.

    Args:
        paths: Files or directories to scan.

    Returns:
        Facts keyed by the source path they came from.
    """
    result: dict[Path, ModuleFacts] = {}
    for path in paths:
        candidates = sorted(path.rglob("*.py")) if path.is_dir() else [path]
        for candidate in candidates:
            result[candidate] = scan_module(candidate)
    return result


def annotated_assignment_types(path: Path, attribute: str) -> set[str]:
    """Return annotation sources for ``self.<attribute>`` assignments.

    Args:
        path: Source file to parse.
        attribute: Attribute name, without the ``self.`` prefix.

    Returns:
        Rendered annotation expressions, one per annotated assignment.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        target = node.target
        if (
            isinstance(target, ast.Attribute)
            and target.attr == attribute
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            found.add(ast.unparse(node.annotation))
    return found


def returned_annotations(path: Path, function_name: str) -> set[str]:
    """Return rendered return annotations for a named function.

    Args:
        path: Source file to parse.
        function_name: Function or method name to look for.

    Returns:
        Rendered return annotations, one per matching definition.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == function_name
            and node.returns is not None
        ):
            found.add(ast.unparse(node.returns))
    return found
