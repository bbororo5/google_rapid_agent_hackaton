from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "launchpilot"
LEGACY_NAMESPACES = {
    "launchpilot.agent",
    "launchpilot.api",
    "launchpilot.application",
    "launchpilot.domain",
    "launchpilot.infrastructure",
}
CORE_FILENAMES = {
    "evidence.py",
    "models.py",
    "ports.py",
    "retrieval.py",
    "service.py",
    "use_case.py",
}
FRAMEWORK_PACKAGES = {"fastapi", "elasticsearch", "opentelemetry", "psycopg"}
FEATURE_MODULES = {
    "analysis",
    "campaigns",
    "evaluation",
    "identity",
    "knowledge",
    "performance",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_legacy_layer_namespaces_are_not_reintroduced() -> None:
    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        for imported in _imports(path):
            if any(
                imported == namespace or imported.startswith(f"{namespace}.")
                for namespace in LEGACY_NAMESPACES
            ):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)} -> {imported}")

    assert not violations, "Legacy layer imports found:\n" + "\n".join(violations)


def test_feature_core_does_not_depend_on_delivery_or_storage_frameworks() -> None:
    excluded_modules = {"bootstrap", "devtools", "observability", "persistence"}
    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(PACKAGE_ROOT)
        if relative.parts[0] in excluded_modules or path.name not in CORE_FILENAMES:
            continue
        for imported in _imports(path):
            root_package = imported.split(".", maxsplit=1)[0]
            if root_package in FRAMEWORK_PACKAGES:
                violations.append(f"{relative} -> {imported}")

    assert not violations, "Framework imports found in feature core:\n" + "\n".join(
        violations
    )


def test_http_adapters_do_not_import_concrete_data_stores() -> None:
    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        if not (path.name == "api.py" or path.name.endswith("_api.py")):
            continue
        for imported in _imports(path):
            if imported.endswith((".postgres", ".elasticsearch")):
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT)} -> {imported}"
                )

    assert not violations, "Concrete stores imported by HTTP adapters:\n" + "\n".join(
        violations
    )


def test_feature_modules_collaborate_only_through_public_interfaces() -> None:
    violations: list[str] = []
    for source_module in FEATURE_MODULES:
        public_api = PACKAGE_ROOT / source_module / "public.py"
        assert public_api.exists(), f"{source_module} must define public.py"

        for path in (PACKAGE_ROOT / source_module).rglob("*.py"):
            for imported in _imports(path):
                parts = imported.split(".")
                if len(parts) < 2 or parts[0] != "launchpilot":
                    continue
                target_module = parts[1]
                if target_module not in FEATURE_MODULES or target_module == source_module:
                    continue
                if len(parts) < 3 or parts[2] != "public":
                    violations.append(
                        f"{path.relative_to(PACKAGE_ROOT)} -> {imported}"
                    )

    assert not violations, "Feature boundary bypasses found:\n" + "\n".join(
        violations
    )
