#!/usr/bin/env python3
"""Validate the structure of an Unraid OS plugin or Unraid API plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

PLACEHOLDER = re.compile(
    r"PLUGIN_ID|PLUGIN_TITLE|PLUGIN_PASCAL|PLUGIN_NAMESPACE|AUTHOR_NAME|OWNER/PLUGIN_ID|MENU_LABEL|ICON_NAME|"
    r"PLUGIN_PAGE_TAG|MIN_UNRAID_VERSION|COPYRIGHT_HOLDER|\bYEAR\b|PagePrefix|"
    r"YOUR_[A-Z0-9_]+|"
    r"\b[A-Z][A-Z0-9_]*_PLACEHOLDER\b"
)
SAFE_ID = re.compile(r"^[a-z][a-z0-9-]*$")
OS_SAFE_ID = re.compile(r"^[a-z][a-z0-9.-]*$")
PLG_ENTITY = re.compile(
    r'^\s*<!ENTITY\s+([A-Za-z_][A-Za-z0-9_.-]*)\s+"([^"]*)">\s*$', re.MULTILINE
)
TEXT_SUFFIXES = {
    ".json",
    ".md",
    ".page",
    ".php",
    ".plg",
    ".sh",
    ".svg",
    ".ts",
    ".xml",
    ".yaml",
    ".yml",
}
OS_TEXT_SUFFIXES = TEXT_SUFFIXES | {".css", ".html", ".js", ".tsx"}
DECORATOR_GROUP = (
    r"(?:\s*@[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?"
    r"(?:\s*\((?:[^()]|\([^()]*\))*\))?\s*)+"
)


class Result:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def read_text(path: Path, result: Result) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        result.error(f"{path}: cannot read UTF-8 text: {exc}")
        return None


def check_placeholders(root: Path, result: Result, plugin_type: str) -> None:
    if plugin_type == "hybrid":
        check_placeholders(root, result, "os")
        for api_root in api_plugin_dirs(root):
            check_placeholders(api_root, result, "api")
        return
    if plugin_type == "os":
        relevant_dirs = plugin_payload_dirs(root)
        relevant_files = {
            root / "build-plg.sh",
            root / "scripts/build-txz.sh",
            root / "scripts/build-classic-package.sh",
            root / "unraid-plugin/scripts/build-txz.sh",
            *root.glob("*.plg"),
            *root.glob("LICENSE*"),
            *root.glob("unraid-plugin/*.plg"),
            *root.glob("unraid-plugin/LICENSE*"),
        }
    else:
        relevant_dirs = [root / "src", root / "test"]
        relevant_files = {
            root / "package.json",
            root / "tsconfig.json",
            root / "index.ts",
            *root.glob("LICENSE*"),
        }
    text_suffixes = OS_TEXT_SUFFIXES if plugin_type == "os" else TEXT_SUFFIXES
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {"node_modules", "dist", ".git"} for part in path.parts):
            continue
        if path.suffix.lower() not in text_suffixes and not path.name.startswith(
            "LICENSE"
        ):
            continue
        if path not in relevant_files and not any(
            path.is_relative_to(base) for base in relevant_dirs
        ):
            continue
        content = read_text(path, result)
        if content is not None and PLACEHOLDER.search(content):
            result.error(f"{path.relative_to(root)}: unresolved scaffold placeholder")


def package_is_api_plugin(path: Path) -> bool:
    try:
        package = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(package, dict) and str(package.get("name", "")).startswith(
        "unraid-api-plugin-"
    )


def api_plugin_dirs(root: Path) -> list[Path]:
    found: set[Path] = set()
    for package in root.glob("*/package.json"):
        if package_is_api_plugin(package):
            found.add(package.parent)
    return sorted(found)


def detect_type(root: Path) -> str | None:
    package = root / "package.json"
    if package.is_file() and package_is_api_plugin(package):
        return "api"
    has_os = (
        list(root.glob("*.plg"))
        or list(root.glob("unraid-plugin/*.plg"))
        or (root / "src/usr/local/emhttp/plugins").is_dir()
        or (root / "source").is_dir()
        or (root / "unraid-plugin/source").is_dir()
    )
    if has_os and api_plugin_dirs(root):
        return "hybrid"
    if has_os:
        return "os"
    return None


def plugin_payload_dirs(root: Path) -> list[Path]:
    bases = [
        root / "src/usr/local/emhttp/plugins",
        root / "source/usr/local/emhttp/plugins",
        root / "unraid-plugin/source/usr/local/emhttp/plugins",
    ]
    found: set[Path] = set()
    for base in bases:
        if base.is_dir():
            found.update(path for path in base.iterdir() if path.is_dir())
    source = root / "source"
    if source.is_dir():
        found.update(
            path
            for path in source.glob("*/usr/local/emhttp/plugins/*")
            if path.is_dir()
        )
    return sorted(found)


def php_web_endpoints(payload: Path) -> list[Path]:
    include = payload / "include"
    if not include.is_dir():
        return []
    endpoints: list[Path] = []
    for path in include.glob("*.php"):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            endpoints.append(path)
            continue
        if "$_REQUEST" in content or "php://input" in content or "$_POST" in content:
            endpoints.append(path)
    return sorted(endpoints)


def validate_private_runtime_modes(root: Path, result: Result) -> None:
    """Fail when staged private runtime executables have already lost +x."""
    local_roots = [
        root / "src/usr/local",
        root / "source/usr/local",
        root / "unraid-plugin/source/usr/local",
    ]
    source = root / "source"
    if source.is_dir():
        local_roots.extend(path for path in source.glob("*/usr/local") if path.is_dir())
    for local_root in local_roots:
        if not local_root.is_dir():
            continue
        for prefix in local_root.iterdir():
            if not prefix.is_dir() or prefix.name == "emhttp":
                continue
            for directory_name in ("bin", "sbin", "libexec"):
                directory = prefix / directory_name
                if not directory.is_dir():
                    continue
                for path in directory.rglob("*"):
                    if not path.is_file() or path.is_symlink():
                        continue
                    try:
                        mode = path.stat().st_mode
                        with path.open("rb") as handle:
                            header = handle.read(4)
                    except OSError as exc:
                        result.error(
                            f"{path.relative_to(root)}: cannot inspect executable mode: {exc}"
                        )
                        continue
                    executable_location = directory_name in {"bin", "sbin"}
                    executable_content = header.startswith((b"#!", b"\x7fELF"))
                    if (
                        executable_location or executable_content
                    ) and not mode & stat.S_IXUSR:
                        result.error(
                            f"{path.relative_to(root)}: staged private runtime helper is not executable; "
                            "assert archive mode and a clean-extraction smoke invocation"
                        )


def resolve_entities(value: str, entities: dict[str, str]) -> str:
    """Resolve simple internal entity references used by common .plg manifests."""
    resolved = value
    for _ in range(16):
        expanded = re.sub(
            r"&([A-Za-z_][A-Za-z0-9_.-]*);",
            lambda match: entities.get(match.group(1), match.group(0)),
            resolved,
        )
        if expanded == resolved:
            break
        resolved = expanded
    return resolved


def validate_archive_executable_modes(
    artifact: Path, root: Path, result: Result
) -> None:
    """Inspect private runtime modes in the release archive without extracting it."""
    try:
        with tarfile.open(artifact, mode="r:*") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                name = member.name.removeprefix("./")
                match = re.search(
                    r"(?:^|/)usr/local/[^/]+/(bin|sbin|libexec)/(.*)$", name
                )
                if not match:
                    continue
                directory_name = match.group(1)
                executable_content = False
                if directory_name == "libexec":
                    extracted = archive.extractfile(member)
                    header = extracted.read(4) if extracted is not None else b""
                    executable_content = header.startswith((b"#!", b"\x7fELF"))
                if (
                    directory_name in {"bin", "sbin"} or executable_content
                ) and not member.mode & stat.S_IXUSR:
                    result.error(
                        f"{artifact.relative_to(root)}: private runtime helper is not executable in archive: "
                        f"{name} (mode {member.mode:04o})"
                    )
    except (OSError, tarfile.TarError) as exc:
        result.error(
            f"{artifact.relative_to(root)}: cannot inspect package archive: {exc}"
        )


def has_installable_package_file(root: ET.Element) -> bool:
    """Return whether a manifest contains an actual downloadable package file."""
    for node in root.iter("FILE"):
        name = node.attrib.get("Name", "").strip().lower()
        url = node_text_value(node.find("URL")).lower()
        if name.endswith((".tgz", ".txz")) or url.endswith((".tgz", ".txz")):
            return True
    return False


def node_text_value(node: ET.Element | None) -> str:
    return "" if node is None else "".join(node.itertext()).strip()


def validate_manifest_contract(
    manifest: Path,
    root: Path,
    parsed: ET.Element,
    entities: dict[str, str],
    require_package: bool,
    result: Result,
) -> None:
    relative = manifest.relative_to(root)
    attributes = {
        key: resolve_entities(value, entities).strip()
        for key, value in parsed.attrib.items()
    }
    for attribute in ("name", "author", "version", "pluginURL"):
        if not attributes.get(attribute):
            result.error(
                f"{relative}: missing required attribute {attribute} on <PLUGIN>"
            )
    plugin_url = attributes.get("pluginURL")
    if plugin_url:
        parsed_url = urlparse(plugin_url)
        if parsed_url.scheme != "https" or not parsed_url.hostname:
            result.error(f"{relative}: pluginURL must be an absolute HTTPS URL")
    for attribute, purpose in (
        ("min", "minimum Unraid compatibility"),
        ("support", "public support destination"),
        ("icon", "plugin-manager icon"),
    ):
        if not attributes.get(attribute):
            result.warn(
                f"{relative}: no {attribute} attribute ({purpose}); confirm this omission is intentional"
            )
    if require_package and not has_installable_package_file(parsed):
        result.error(
            f"{relative}: no installable package <FILE> with a .tgz/.txz Name or URL"
        )


def strip_typescript_comments_and_strings(content: str) -> str:
    """Remove comments and literal contents while preserving line structure."""
    token = re.compile(
        r"//[^\n]*|/\*.*?\*/|"
        r'"(?:\\.|[^"\\])*"|'
        r"'(?:\\.|[^'\\])*'|"
        r"`(?:\\.|[^`\\])*`",
        re.DOTALL,
    )

    def blank(match: re.Match[str]) -> str:
        value = match.group(0)
        return (
            "\n" * value.count("\n")
            if value.startswith(("//", "/*"))
            else '""' + "\n" * value.count("\n")
        )

    return token.sub(blank, content)


def strip_typescript_comments(content: str) -> str:
    """Remove comments while preserving string literals used by import/export."""
    token = re.compile(
        r"//[^\n]*|/\*.*?\*/|"
        r'"(?:\\.|[^"\\])*"|'
        r"'(?:\\.|[^'\\])*'|"
        r"`(?:\\.|[^`\\])*`",
        re.DOTALL,
    )

    def blank_comments(match: re.Match[str]) -> str:
        value = match.group(0)
        if value.startswith(("//", "/*")):
            return "\n" * value.count("\n")
        return value

    return token.sub(blank_comments, content)


def class_validator_decorators(content: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(
        r'import\s*\{(?P<names>[^}]*)\}\s*from\s*["\']class-validator["\']',
        content,
        re.DOTALL,
    ):
        for item in match.group("names").split(","):
            item = item.strip()
            if not item:
                continue
            parts = re.split(r"\s+as\s+", item)
            names.add(parts[-1].strip())
    for match in re.finditer(
        r'import\s+\*\s+as\s+([A-Za-z_$][\w$]*)\s+from\s*["\']class-validator["\']',
        content,
    ):
        names.add(f"{match.group(1)}.*")
    return names


def named_import_aliases(content: str, module_pattern: str) -> dict[str, str]:
    """Map local named-import bindings to their exported names."""
    aliases: dict[str, str] = {}
    pattern = re.compile(
        rf'import\s*\{{(?P<names>[^}}]*)\}}\s*from\s*["\'](?:{module_pattern})["\']',
        re.DOTALL,
    )
    for match in pattern.finditer(content):
        for item in match.group("names").split(","):
            item = item.strip()
            if not item or item.startswith("type "):
                continue
            parts = re.split(r"\s+as\s+", item.removeprefix("type ").strip())
            exported = parts[0].strip()
            local = parts[-1].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", exported) and re.fullmatch(
                r"[A-Za-z_$][\w$]*", local
            ):
                aliases[local] = exported
    return aliases


def namespace_imports(content: str, module_pattern: str) -> set[str]:
    """Return namespace bindings imported from the selected module."""
    return set(
        re.findall(
            rf"import\s+\*\s+as\s+([A-Za-z_$][\w$]*)\s+from\s*"
            rf'["\'](?:{module_pattern})["\']',
            content,
        )
    )


def decorator_aliases(
    content: str, module_pattern: str, exported_names: set[str]
) -> dict[str, str]:
    aliases = named_import_aliases(content, module_pattern)
    for namespace in namespace_imports(content, module_pattern):
        aliases.update(
            {f"{namespace}.{exported}": exported for exported in exported_names}
        )
    return aliases


def decorator_names(decorators: str, aliases: dict[str, str]) -> set[str]:
    return {
        aliases.get(name, name)
        for name in re.findall(
            r"@([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)", decorators
        )
    }


def raw_decorator_names(decorators: str) -> set[str]:
    return {
        name
        for name in re.findall(
            r"@([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)", decorators
        )
    }


def graphql_operations_without_permissions(content: str) -> list[str]:
    graphql_aliases = decorator_aliases(
        content,
        r"@nestjs/graphql",
        {"Resolver", "Query", "Mutation", "Subscription", "ResolveField"},
    )
    permission_aliases = decorator_aliases(
        content,
        r"@unraid/shared(?:/[^\"']*)?",
        {"UsePermissions"},
    )
    permission_bindings = {
        local
        for local, exported in permission_aliases.items()
        if exported == "UsePermissions"
    }
    sanitized = strip_typescript_comments_and_strings(content)
    member = re.compile(
        rf"(?P<decorators>{DECORATOR_GROUP})"
        r"(?:(?:public|private|protected|static|async|readonly|abstract)\s+)*"
        r"(?P<name>[A-Za-z_$][\w$]*)\s*\(",
        re.DOTALL,
    )
    resolver_class = re.compile(
        rf"(?P<decorators>{DECORATOR_GROUP})"
        r"(?:export\s+)?(?:abstract\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)[^{]*\{",
        re.DOTALL,
    )
    missing: list[str] = []
    resolver_ranges: list[tuple[int, int]] = []
    for class_match in resolver_class.finditer(sanitized):
        class_decorators = decorator_names(
            class_match.group("decorators"), graphql_aliases
        )
        if "Resolver" not in class_decorators:
            continue
        opening = sanitized.find("{", class_match.start())
        closing = matching_brace(sanitized, opening)
        if closing is None:
            continue
        resolver_ranges.append((class_match.start(), closing + 1))
        body = sanitized[opening + 1 : closing]
        for match in member.finditer(body):
            decorator_source = match.group("decorators")
            decorators = decorator_names(decorator_source, graphql_aliases)
            if not decorators.intersection(
                {"Query", "Mutation", "Subscription", "ResolveField"}
            ):
                continue
            if not raw_decorator_names(decorator_source).intersection(
                permission_bindings
            ):
                missing.append(match.group("name"))

    # Keep a conservative fallback for unusual resolver declarations the class
    # scanner cannot recognize. Operations inside recognized classes were
    # already evaluated above.
    for match in member.finditer(sanitized):
        if any(start <= match.start() < end for start, end in resolver_ranges):
            continue
        decorator_source = match.group("decorators")
        decorators = decorator_names(decorator_source, graphql_aliases)
        if decorators.intersection(
            {"Query", "Mutation", "Subscription", "ResolveField"}
        ) and not raw_decorator_names(decorator_source).intersection(
            permission_bindings
        ):
            missing.append(match.group("name"))
    return missing


def matching_brace(content: str, opening: int) -> int | None:
    depth = 0
    for index in range(opening, len(content)):
        if content[index] == "{":
            depth += 1
        elif content[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def graphql_input_fields_without_validation(content: str) -> list[str]:
    validator_names = class_validator_decorators(content)
    graphql_aliases = decorator_aliases(
        content,
        r"@nestjs/graphql",
        {"InputType", "Field"},
    )
    sanitized = strip_typescript_comments_and_strings(content)
    class_pattern = re.compile(
        rf"(?P<decorators>{DECORATOR_GROUP})"
        r"(?:export\s+)?class\s+"
        r"(?P<name>[A-Za-z_$][\w$]*)[^{]*\{",
        re.DOTALL,
    )
    field_pattern = re.compile(
        rf"(?P<decorators>{DECORATOR_GROUP})"
        r"(?:(?:public|private|protected|static|readonly|declare)\s+)*"
        r"(?:(?:get|set)\s+)?"
        r"(?P<name>[A-Za-z_$][\w$]*)[?!]?\s*(?::|=|\()",
        re.DOTALL,
    )
    missing: list[str] = []
    for class_match in class_pattern.finditer(sanitized):
        if "InputType" not in decorator_names(
            class_match.group("decorators"), graphql_aliases
        ):
            continue
        opening = sanitized.find("{", class_match.start())
        closing = matching_brace(sanitized, opening)
        if closing is None:
            continue
        body = sanitized[opening + 1 : closing]
        for field_match in field_pattern.finditer(body):
            decorators = decorator_names(
                field_match.group("decorators"), graphql_aliases
            )
            if "Field" not in decorators:
                continue
            validated = any(name in validator_names for name in decorators)
            if not validated:
                validated = any(
                    "." in name and f"{name.split('.', 1)[0]}.*" in validator_names
                    for name in decorators
                )
            if not validated:
                missing.append(
                    f"{class_match.group('name')}.{field_match.group('name')}"
                )
    return missing


def resolve_typescript_import(source: Path, specifier: str) -> Path | None:
    if not specifier.startswith("."):
        return None
    imported = (source.parent / specifier).resolve()
    candidates = [imported]
    if imported.suffix in {".js", ".mjs", ".cjs"}:
        candidates = [
            imported.with_suffix(".ts"),
            imported.with_suffix(".mts"),
            imported.with_suffix(".cts"),
        ]
    candidates.append(imported / "index.ts")
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def source_declares_class_binding(name: str, content: str) -> bool:
    sanitized = strip_typescript_comments_and_strings(content)
    return bool(
        re.search(rf"\bclass\s+{re.escape(name)}\b", sanitized)
        or re.search(
            rf"\b(?:const|let|var)\s+{re.escape(name)}\s*=\s*class\b",
            sanitized,
        )
    )


def source_exports_class_binding(name: str, content: str) -> bool:
    sanitized = strip_typescript_comments_and_strings(content)
    if name == "default":
        return bool(re.search(r"\bexport\s+default\s+class(?:\s|\{)", sanitized))
    if re.search(
        rf"\bexport\s+(?:default\s+)?class\s+{re.escape(name)}\b", sanitized
    ) or re.search(
        rf"\bexport\s+(?:const|let|var)\s+{re.escape(name)}\s*=\s*class\b",
        sanitized,
    ):
        return True
    if not source_declares_class_binding(name, content):
        return False
    export_lists = strip_typescript_comments(content)
    return any(
        any(
            (
                (parts := re.split(r"\s+as\s+", item.strip()))[-1].strip() == name
                and parts[0].strip() == name
            )
            for item in match.group("names").split(",")
            if item.strip()
        )
        for match in re.finditer(
            r"\bexport\s*\{(?P<names>[^}]*)\}(?!\s*from\b)",
            export_lists,
            re.DOTALL,
        )
    )


def is_class_constructor_binding(
    name: str,
    entry: Path,
    entry_content: str,
    source_documents: dict[Path, str],
) -> bool:
    if source_declares_class_binding(name, entry_content):
        return True

    named_import = re.compile(
        r"import\s*\{(?P<names>[^}]*)\}\s*from\s*"
        r'["\'](?P<specifier>\.[^"\']*)["\']',
        re.DOTALL,
    )
    for match in named_import.finditer(entry_content):
        imported_name: str | None = None
        for item in match.group("names").split(","):
            parts = re.split(r"\s+as\s+", item.strip())
            if not parts or len(parts) > 2:
                continue
            exported = parts[0].removeprefix("type ").strip()
            local = parts[-1].strip()
            if local == name:
                imported_name = exported
                break
        if imported_name is None:
            continue
        imported_path = resolve_typescript_import(entry, match.group("specifier"))
        if imported_path is None:
            continue
        imported_content = source_documents.get(imported_path.resolve())
        if imported_content is None:
            continue
        if source_exports_class_binding(imported_name, imported_content):
            return True
    return False


def validate_api_module_exports(
    entry: Path,
    content: str,
    source_documents: dict[Path, str],
    result: Result,
) -> None:
    sanitized = strip_typescript_comments_and_strings(content)
    constructor_exports: set[str] = set()
    assignment_exports = list(
        re.finditer(
            r"\bexport\s+const\s+(ApiModule|CliModule)\s*=\s*",
            sanitized,
        )
    )
    for match in assignment_exports:
        export_name = match.group(1)
        constructor_exports.add(export_name)
        initializer = sanitized[match.end() :].lstrip()
        if re.match(r"class(?:\s+[A-Za-z_$][\w$]*)?\s*\{", initializer):
            continue
        identifier = re.match(r"([A-Za-z_$][\w$]*)\b", initializer)
        if identifier is not None:
            remainder = initializer[identifier.end() :].lstrip()
            if (
                not remainder or remainder.startswith(";")
            ) and is_class_constructor_binding(
                identifier.group(1), entry, content, source_documents
            ):
                continue
        result.error(
            f"{entry.name}: {export_name} must be initialized with a class constructor"
        )

    constructor_exports.update(
        re.findall(
            r"\bexport\s+class\s+(ApiModule|CliModule)\b",
            sanitized,
        )
    )

    exports_with_strings = strip_typescript_comments(content)
    export_list = re.compile(
        r"\bexport\s*\{(?P<names>[^}]*)\}"
        r"(?:\s*from\s*[\"'](?P<specifier>[^\"']+)[\"'])?",
        re.DOTALL,
    )
    for match in export_list.finditer(exports_with_strings):
        specifier = match.group("specifier")
        for item in match.group("names").split(","):
            item = item.strip().removeprefix("type ").strip()
            if not item:
                continue
            parts = re.split(r"\s+as\s+", item)
            if len(parts) > 2:
                continue
            local_name = parts[0].strip()
            export_name = parts[-1].strip()
            if export_name not in {"ApiModule", "CliModule"}:
                continue
            constructor_exports.add(export_name)
            is_constructor = False
            if specifier:
                imported_path = resolve_typescript_import(entry, specifier)
                if imported_path is not None:
                    imported_content = source_documents.get(imported_path.resolve())
                    if imported_content is not None:
                        is_constructor = source_exports_class_binding(
                            local_name, imported_content
                        )
            else:
                is_constructor = is_class_constructor_binding(
                    local_name, entry, content, source_documents
                )
            if not is_constructor:
                result.error(
                    f"{entry.name}: {export_name} must be initialized with a class constructor"
                )

    if not constructor_exports:
        result.error(f"{entry.name}: must export ApiModule or CliModule")


def validate_os(root: Path, result: Result) -> None:
    payloads = plugin_payload_dirs(root)
    if not payloads:
        result.error(
            "missing plugin payload under src/usr/local/emhttp/plugins/<id>/ or source/<package>/usr/local/emhttp/plugins/<id>/"
        )
        return
    if len(payloads) > 1:
        result.warn(
            f"multiple OS plugin payloads found ({len(payloads)}); validate lifecycle boundaries independently"
        )

    for payload in payloads:
        plugin_id = payload.name
        if not OS_SAFE_ID.fullmatch(plugin_id):
            result.error(f"unsafe plugin id: {plugin_id}")
        if not any(path.is_file() for path in payload.rglob("*")):
            result.error(
                f"{payload.relative_to(root)}: plugin payload directory is empty"
            )
            continue
        pages = list(payload.glob("*.page"))
        if not pages:
            result.warn(
                f"{plugin_id}: no webGUI .page file (valid only for headless plugins)"
            )
        for page in pages:
            content = read_text(page, result)
            if content is not None and "---" not in content:
                result.error(
                    f"{page.relative_to(root)}: missing .page front-matter delimiter"
                )

        for endpoint in php_web_endpoints(payload):
            content = read_text(endpoint, result) or ""
            relative = endpoint.relative_to(root)
            if "json_encode" not in content:
                result.error(f"{relative}: web-callable PHP endpoint must emit JSON")
            local_csrf = "csrf_token" in content and "hash_equals" in content
            platform_csrf = "auto_prepend" in content or "local_prepend.php" in content
            if not local_csrf and not platform_csrf:
                result.error(
                    f"{relative}: no recognizable local or webGUI platform CSRF gate"
                )
            if (
                "exec(" in content or "shell_exec(" in content
            ) and "escapeshellarg" not in content:
                result.warn(
                    f"{relative}: shells out without a recognizable escapeshellarg boundary; audit that every command is static"
                )

        for shell in payload.rglob("*.sh"):
            mode = shell.stat().st_mode
            if not mode & stat.S_IXUSR:
                result.warn(
                    f"{shell.relative_to(root)}: source file is not executable; prove the build/install step normalizes mode 0755"
                )
            content = read_text(shell, result) or ""
            if re.search(
                r"(^|[;\s])(source|\.)\s+[^\n]*(\.cfg|\$CFG)", content, re.MULTILINE
            ):
                result.warn(
                    f"{shell.relative_to(root)}: sources plugin config; audit ownership, writer allowlists, quoting, validation, and permissions"
                )

    validate_private_runtime_modes(root, result)
    if not any(
        (root / name).is_file() for name in ("LICENSE", "LICENSE.md", "LICENSE.txt")
    ):
        result.warn("no root license file found")

    build_scripts = [
        root / "build-plg.sh",
        root / "builder/build-plugin.ts",
        root / "scripts/build-txz.sh",
        root / "scripts/build-classic-package.sh",
        root / "unraid-plugin/scripts/build-txz.sh",
    ]
    if not any(path.is_file() for path in build_scripts):
        result.warn("no recognized .plg build entry point")
    if (root / "build-plg.sh").is_file() and not (
        root / "build-plg.sh"
    ).stat().st_mode & stat.S_IXUSR:
        result.error("build-plg.sh is not executable")

    manifests = sorted(root.glob("*.plg"))
    if (root / "plugins").is_dir():
        manifests.extend(sorted((root / "plugins").glob("*.plg")))
    manifests.extend(sorted(root.glob("unraid-plugin/*.plg")))
    if not manifests:
        result.warn("no generated .plg manifest found; build before release validation")
    for manifest in manifests:
        manifest_content = read_text(manifest, result) or ""
        if "<MD5>" in manifest_content and "sha256" not in manifest_content.lower():
            result.warn(
                f"{manifest.relative_to(root)}: package uses loader MD5 without a recognizable SHA-256 verification step"
            )
        try:
            parsed = ET.parse(manifest).getroot()
        except (OSError, ET.ParseError) as exc:
            result.error(f"{manifest.relative_to(root)}: invalid .plg XML: {exc}")
            continue
        if parsed.tag != "PLUGIN":
            result.error(f"{manifest.relative_to(root)}: root must be <PLUGIN>")
        entities = dict(PLG_ENTITY.findall(manifest_content))
        validate_manifest_contract(
            manifest,
            root,
            parsed,
            entities,
            require_package=any(payload.glob("*.page") for payload in payloads),
            result=result,
        )
        package_name_raw = entities.get("packageName") or entities.get("txz")
        package_url_raw = entities.get("packageURL") or entities.get("txzURL")
        package_name = (
            resolve_entities(package_name_raw, entities) if package_name_raw else None
        )
        package_url = (
            resolve_entities(package_url_raw, entities) if package_url_raw else None
        )
        if package_name:
            if "&" in package_name:
                result.error(
                    f"{manifest.relative_to(root)}: package filename contains unresolved entities: {package_name}"
                )
                continue
            if Path(package_name).name != package_name or not package_name.endswith(
                (".tgz", ".txz")
            ):
                result.error(
                    f"{manifest.relative_to(root)}: unsafe or unsupported packageName entity: {package_name}"
                )
                continue
            if (
                package_url
                and "&" not in package_url
                and Path(urlparse(package_url).path).name != package_name
            ):
                result.error(
                    f"{manifest.relative_to(root)}: packageURL basename does not match packageName ({package_name})"
                )
            exact_artifacts = [
                candidate
                for candidate in (
                    root / package_name,
                    root / "deploy" / package_name,
                    root / "deploy/plugins/local" / package_name,
                    root / "packages" / package_name,
                )
                if candidate.is_file()
            ]
            if not exact_artifacts:
                stable_name = entities.get("name", manifest.stem)
                stable = root / f"{stable_name}.tgz"
                detail = (
                    f"; stable archive exists at {stable.name}"
                    if stable.is_file()
                    else ""
                )
                result.warn(
                    f"{manifest.relative_to(root)}: exact packageName artifact is not present locally: {package_name}{detail}; "
                    "prove the release job emits this exact filename"
                )
            else:
                artifact = exact_artifacts[0]
                package_md5 = entities.get("packageMD5") or entities.get("md5")
                package_sha256 = entities.get("packageSHA256") or entities.get("sha256")
                try:
                    artifact_bytes = artifact.read_bytes()
                except OSError as exc:
                    result.error(
                        f"{artifact.relative_to(root)}: cannot read package artifact: {exc}"
                    )
                    continue
                if (
                    package_md5
                    and hashlib.md5(artifact_bytes).hexdigest().lower()
                    != package_md5.lower()
                ):
                    result.error(
                        f"{manifest.relative_to(root)}: packageMD5 does not match {artifact.relative_to(root)}"
                    )
                if (
                    package_sha256
                    and hashlib.sha256(artifact_bytes).hexdigest().lower()
                    != package_sha256.lower()
                ):
                    result.error(
                        f"{manifest.relative_to(root)}: packageSHA256 does not match {artifact.relative_to(root)}"
                    )
                if not package_sha256:
                    result.warn(
                        f"{manifest.relative_to(root)}: no package SHA-256 entity found for "
                        f"{artifact.relative_to(root)}; MD5 is only an Unraid loader compatibility field"
                    )
                validate_archive_executable_modes(artifact, root, result)


def load_json(path: Path, result: Result) -> dict[str, object] | None:
    text = read_text(path, result)
    if text is None:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        result.error(f"{path}: invalid JSON: {exc}")
        return None
    if not isinstance(value, dict):
        result.error(f"{path}: expected JSON object")
        return None
    return value


def validate_api(root: Path, result: Result) -> None:
    package_path = root / "package.json"
    if not package_path.is_file():
        result.error("missing package.json")
        return
    package = load_json(package_path, result)
    if package is None:
        return
    name = package.get("name")
    if not isinstance(name, str) or not name.startswith("unraid-api-plugin-"):
        result.error("package name must start with unraid-api-plugin-")
    elif not SAFE_ID.fullmatch(name.removeprefix("unraid-api-plugin-")):
        result.error(f"unsafe API plugin id in package name: {name}")
    if package.get("type") != "module":
        result.error('package.json must set "type": "module"')
    exports = package.get("exports")
    export_root = exports.get(".") if isinstance(exports, dict) else None
    export_import = export_root.get("import") if isinstance(export_root, dict) else None
    export_types = export_root.get("types") if isinstance(export_root, dict) else None
    if package.get("main") != "dist/index.js" and export_import != "./dist/index.js":
        result.warn(
            'package.json should expose "./dist/index.js" through main or exports'
        )
    if not package.get("types") and not export_types:
        result.warn(
            "package.json should publish TypeScript declarations through types or exports"
        )
    if not exports:
        result.warn("package.json should define exports")
    scripts = package.get("scripts")
    if not isinstance(scripts, dict) or not scripts.get("build"):
        result.error("package.json requires a build script")
    if not isinstance(scripts, dict) or not scripts.get("test"):
        result.warn("package.json has no test script")
    peers = package.get("peerDependencies")
    if not isinstance(peers, dict) or "@nestjs/common" not in peers:
        result.error("peerDependencies must include compatible @nestjs/common")

    entry = root / "src/index.ts"
    if not entry.is_file():
        entry = root / "index.ts"
    if not entry.is_file():
        result.error("missing src/index.ts or index.ts entry point")
        return
    content = read_text(entry, result) or ""
    if not re.search(r"export\s+const\s+adapter\s*=\s*['\"]nestjs['\"]", content):
        result.error(f"{entry.relative_to(root)}: must export adapter = 'nestjs'")
    source_documents = {entry.resolve(): content}
    for source in root.glob("src/**/*.ts"):
        if source == entry or source.name.endswith((".test.ts", ".spec.ts")):
            continue
        source_documents[source.resolve()] = read_text(source, result) or ""
    validate_api_module_exports(entry, content, source_documents, result)
    for match in re.finditer(r"from\s+['\"](\.[^'\"]+)['\"]", content):
        specifier = match.group(1)
        if not specifier.endswith(".js"):
            result.warn(
                f"{entry.relative_to(root)}: relative ESM import should end in .js: {specifier}"
            )

    tests = (
        list(root.glob("test/**/*.ts"))
        + list(root.glob("src/**/*.spec.ts"))
        + list(root.glob("src/**/*.test.ts"))
        + list(root.glob("src/**/__test__/*.ts"))
    )
    source_text = "\n".join(source_documents.values())
    host_imports = {
        "@nestjs/core": "@nestjs/core",
        "@nestjs/config": "@nestjs/config",
        "@nestjs/graphql": "@nestjs/graphql",
        "@unraid/shared": "@unraid/shared",
        "class-transformer": "class-transformer",
        "class-validator": "class-validator",
    }
    peers_dict = peers if isinstance(peers, dict) else {}
    for marker, dependency in host_imports.items():
        if marker in source_text and dependency not in peers_dict:
            result.error(
                f"peerDependencies must include imported host package {dependency}"
            )

    for source, source_content in source_documents.items():
        for operation in graphql_operations_without_permissions(source_content):
            result.error(
                f"{source.relative_to(root)}: resolver operation {operation} has no explicit "
                "per-operation @UsePermissions decorator"
            )
        for field in graphql_input_fields_without_validation(source_content):
            result.error(
                f"{source.relative_to(root)}: GraphQL input field {field} has no class-validator decorator"
            )
    if "graphqlSchemaExtension" in source_text:
        contract_tests = list(root.glob("**/*schema*contract*.test.ts")) + list(
            root.glob("**/*schema*contract*.spec.ts")
        )
        if not contract_tests:
            result.warn(
                "graphqlSchemaExtension is present without a recognizable resolver/SDL contract test"
            )

    if not tests:
        result.warn("no API plugin tests found")
    if not any(
        (root / name).is_file() for name in ("LICENSE", "LICENSE.md", "LICENSE.txt")
    ):
        result.warn("no root license file found")


def validate_hybrid(root: Path, result: Result) -> None:
    validate_os(root, result)
    api_roots = api_plugin_dirs(root)
    if not api_roots:
        result.error(
            "hybrid plugin has no immediate child package named unraid-api-plugin-*"
        )
        return
    if len(api_roots) > 1:
        result.warn(
            f"multiple API plugin packages found ({len(api_roots)}); validate coordinated ownership independently"
        )
    for api_root in api_roots:
        validate_api(api_root, result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--type", choices=("os", "api", "hybrid"), dest="plugin_type")
    args = parser.parse_args()
    root = args.path.resolve()
    result = Result()
    if not root.is_dir():
        result.error(f"not a directory: {root}")
        plugin_type = args.plugin_type or "unknown"
    else:
        plugin_type = args.plugin_type or detect_type(root)
        if plugin_type is None:
            result.error("cannot detect plugin type; pass --type os or --type api")
            plugin_type = "unknown"
        elif plugin_type == "os":
            validate_os(root, result)
        elif plugin_type == "api":
            validate_api(root, result)
        else:
            validate_hybrid(root, result)
        check_placeholders(root, result, plugin_type)

    for warning in result.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    if result.errors:
        print(f"Unraid {plugin_type} plugin validation failed:", file=sys.stderr)
        for error in result.errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        f"Unraid {plugin_type} plugin validation passed with {len(result.warnings)} warning(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
