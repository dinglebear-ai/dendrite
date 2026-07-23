#!/usr/bin/env python3
"""Offline-first preflight for a current Unraid CA plugin repository."""

from __future__ import annotations

import argparse
import http.client
import ipaddress
import re
import socket
import ssl
import struct
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER = re.compile(
    r"\{\{|\bTODO\b|PLACEHOLDER|YOUR_[A-Z0-9_]+|example\.com",
    re.IGNORECASE,
)
PLUGIN_TAGS = {
    "PluginURL",
    "Name",
    "Category",
    "Icon",
    "Overview",
    "Project",
    "Support",
    "Beta",
    "Deprecated",
    "DonateLink",
    "DonateText",
    "ReadMe",
}
PROFILE_TAGS = {
    "Profile",
    "Forum",
    "WebPage",
    "Icon",
    "Discord",
    "Facebook",
    "Photo",
    "Reddit",
    "Twitter",
    "Video",
    "DonateLink",
    "DonateText",
}
URL_TAGS = {
    "PluginURL",
    "Support",
    "Project",
    "Icon",
    "ReadMe",
    "Forum",
    "WebPage",
    "Discord",
    "Photo",
    "Video",
    "DonateLink",
    "Reddit",
    "Twitter",
    "Facebook",
}
RECOMMENDED_PLUGIN_TAGS = ("Support", "Project", "Overview", "Category")
RECOMMENDED_PROFILE_TAGS = ("Icon", "WebPage")
REQUIRED_PLUGIN_TAGS = {"Name", "PluginURL"}
REQUIRED_PROFILE_TAGS = {"Profile"}
TEXT_SUFFIXES = {".md", ".plg", ".svg", ".txt", ".xml"}
MAX_REDIRECTS = 10
MAX_PLUGIN_MANIFEST_BYTES = 16 * 1024 * 1024
UNICODE_DOT_TRANSLATION = str.maketrans(
    {
        "\N{IDEOGRAPHIC FULL STOP}": ".",
        "\N{FULLWIDTH FULL STOP}": ".",
        "\N{HALFWIDTH IDEOGRAPHIC FULL STOP}": ".",
    }
)


@dataclass(frozen=True)
class ResolvedHTTPSURL:
    url: str
    hostname: str
    port: int
    request_target: str
    addresses: tuple[tuple[int, str], ...]


def node_text(root: ET.Element, tag: str) -> str:
    node = root.find(tag)
    return "" if node is None else "".join(node.itertext()).strip()


def parse_xml(path: Path, errors: list[str]) -> ET.Element | None:
    try:
        return ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        errors.append(f"{path}: invalid XML: {exc}")
        return None


def read_text(path: Path, errors: list[str]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"{path}: cannot read UTF-8 text: {exc}")
        return None


def validate_https_url_syntax(url: str) -> urllib.parse.SplitResult:
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"invalid URL authority: {exc}") from exc
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("embedded URL credentials are not allowed")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    hostname = parsed.hostname
    assert hostname is not None
    security_hostname = hostname.translate(UNICODE_DOT_TRANSLATION).rstrip(".")
    numeric_parts = security_hostname.split(".")
    numeric_host = 1 <= len(numeric_parts) <= 4 and all(
        re.fullmatch(r"(?:0[xX][0-9A-Fa-f]+|\d+)", part) for part in numeric_parts
    )
    canonical_ipv4 = len(numeric_parts) == 4 and all(
        re.fullmatch(r"(?:0|[1-9]\d{0,2})", part) and int(part) <= 255
        for part in numeric_parts
    )
    if numeric_host and not canonical_ipv4:
        raise ValueError(f"noncanonical numeric host {hostname}")
    try:
        literal = ipaddress.ip_address(security_hostname)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise ValueError(f"non-public literal address {literal}")
    return parsed


def validate_child_tags(
    path: Path,
    root: ET.Element,
    allowed: set[str],
    errors: list[str],
) -> None:
    for child in root:
        if child.tag not in allowed:
            errors.append(
                f"{path}: unsupported <{child.tag}>; consult the parser-backed XML field reference"
            )


def direct_nodes(root: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in root if child.tag == tag]


def validate_singleton_tags(
    path: str | Path,
    root: ET.Element,
    supported: set[str],
    required: set[str],
    errors: list[str],
) -> None:
    for tag in sorted(supported):
        count = len(direct_nodes(root, tag))
        if tag in required and count != 1:
            errors.append(f"{path}: expected exactly one direct <{tag}>, found {count}")
        elif tag not in required and count > 1:
            errors.append(f"{path}: expected at most one direct <{tag}>, found {count}")


def collect_urls(
    path: Path, root: ET.Element, errors: list[str]
) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    for tag in URL_TAGS:
        for index, node in enumerate(root.iter(tag), start=1):
            value = "".join(node.itertext()).strip()
            if not value:
                continue
            label = f"{path} <{tag}>" if index == 1 else f"{path} <{tag}> #{index}"
            try:
                validate_https_url_syntax(value)
            except ValueError as exc:
                errors.append(f"{label}: unsafe or invalid HTTPS URL: {value} ({exc})")
                continue
            urls.append((label, value))
    return urls


def resolve_public_https_url(url: str) -> ResolvedHTTPSURL:
    parsed = validate_https_url_syntax(url)
    hostname = parsed.hostname
    assert hostname is not None
    port = parsed.port or 443
    try:
        address_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed: {exc}") from exc
    if not address_info:
        raise ValueError("DNS returned no addresses")
    addresses: list[tuple[int, str]] = []
    for family, _, _, _, socket_address in address_info:
        if family not in {socket.AF_INET, socket.AF_INET6}:
            continue
        ip = ipaddress.ip_address(socket_address[0])
        if not ip.is_global:
            raise ValueError(f"resolves to non-public address {ip}")
        candidate = (family, str(ip))
        if candidate not in addresses:
            addresses.append(candidate)
    if not addresses:
        raise ValueError("DNS returned no usable IPv4 or IPv6 addresses")
    path = parsed.path or "/"
    request_target = path + (f"?{parsed.query}" if parsed.query else "")
    return ResolvedHTTPSURL(
        url=url,
        hostname=hostname,
        port=port,
        request_target=request_target,
        addresses=tuple(addresses),
    )


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to a validated IP while retaining hostname TLS."""

    def __init__(
        self,
        host: str,
        port: int,
        address: tuple[int, str],
        *,
        timeout: float,
        context: ssl.SSLContext | None = None,
    ) -> None:
        super().__init__(host, port, timeout=timeout, context=context)
        self._validated_address = address

    def connect(self) -> None:
        family, ip = self._validated_address
        raw_socket = socket.socket(family, socket.SOCK_STREAM)
        raw_socket.settimeout(self.timeout)
        try:
            if self.source_address:
                raw_socket.bind(self.source_address)
            destination: tuple[object, ...]
            if family == socket.AF_INET6:
                destination = (ip, self.port, 0, 0)
            else:
                destination = (ip, self.port)
            raw_socket.connect(destination)
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except BaseException:
            raw_socket.close()
            raise


def request_pinned_https(
    target: ResolvedHTTPSURL, timeout: float = 15
) -> tuple[int, str | None]:
    failures: list[str] = []
    for address in target.addresses:
        connection = PinnedHTTPSConnection(
            target.hostname,
            target.port,
            address,
            timeout=timeout,
        )
        try:
            connection.request(
                "GET",
                target.request_target,
                headers={
                    "User-Agent": "unraid-ca-preflight/3",
                    "Accept": "*/*",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            status = response.status
            location = response.getheader("Location")
            response.close()
            return status, location
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            failures.append(f"{address[1]}: {exc}")
        finally:
            connection.close()
    raise OSError(
        "; ".join(failures) if failures else "no validated address was attempted"
    )


def request_pinned_https_body(
    target: ResolvedHTTPSURL, timeout: float = 15
) -> tuple[int, str | None, bytes]:
    failures: list[str] = []
    for address in target.addresses:
        connection = PinnedHTTPSConnection(
            target.hostname,
            target.port,
            address,
            timeout=timeout,
        )
        try:
            connection.request(
                "GET",
                target.request_target,
                headers={
                    "User-Agent": "unraid-ca-preflight/4",
                    "Accept": "application/xml,text/xml,*/*",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            status = response.status
            location = response.getheader("Location")
            body = b""
            if 200 <= status < 300:
                content_length = response.getheader("Content-Length")
                if (
                    content_length is not None
                    and content_length.isdecimal()
                    and int(content_length) > MAX_PLUGIN_MANIFEST_BYTES
                ):
                    raise ValueError(
                        "plugin manifest exceeds "
                        f"{MAX_PLUGIN_MANIFEST_BYTES} byte limit"
                    )
                body = response.read(MAX_PLUGIN_MANIFEST_BYTES + 1)
                if len(body) > MAX_PLUGIN_MANIFEST_BYTES:
                    raise ValueError(
                        "plugin manifest exceeds "
                        f"{MAX_PLUGIN_MANIFEST_BYTES} byte limit"
                    )
            response.close()
            return status, location, body
        except (OSError, ValueError, ssl.SSLError, http.client.HTTPException) as exc:
            failures.append(f"{address[1]}: {exc}")
        finally:
            connection.close()
    raise OSError(
        "; ".join(failures) if failures else "no validated address was attempted"
    )


def check_url(
    label: str,
    url: str,
    errors: list[str],
    *,
    resolver: Callable[[str], ResolvedHTTPSURL] = resolve_public_https_url,
    requester: Callable[
        [ResolvedHTTPSURL], tuple[int, str | None]
    ] = request_pinned_https,
) -> bool:
    current = url
    visited: set[str] = set()
    for _ in range(MAX_REDIRECTS + 1):
        if current in visited:
            errors.append(f"{label}: redirect loop: {current}")
            return False
        visited.add(current)
        try:
            target = resolver(current)
            status, location = requester(target)
        except (
            OSError,
            TimeoutError,
            ValueError,
            ssl.SSLError,
            http.client.HTTPException,
        ) as exc:
            errors.append(f"{label}: not anonymously reachable: {current} ({exc})")
            return False
        if 300 <= status < 400:
            if not location:
                errors.append(
                    f"{label}: HTTP {status} redirect has no Location: {current}"
                )
                return False
            current = urllib.parse.urljoin(current, location)
            continue
        if status >= 400:
            errors.append(f"{label}: returned HTTP {status}: {current}")
            return False
        return True
    errors.append(f"{label}: exceeded {MAX_REDIRECTS} redirects: {url}")
    return False


def compare_plugin_manifest_url(
    label: str,
    wrapper_url: str,
    manifest: bytes,
    errors: list[str],
) -> bool:
    try:
        root = ET.fromstring(manifest)
    except ET.ParseError as exc:
        errors.append(f"{label}: fetched .plg is invalid XML: {exc}")
        return False
    if root.tag != "PLUGIN":
        errors.append(f"{label}: fetched .plg root must be <PLUGIN>, got <{root.tag}>")
        return False
    manifest_url = root.attrib.get("pluginURL", "").strip()
    if not manifest_url:
        errors.append(f"{label}: fetched .plg has no non-empty pluginURL attribute")
        return False
    if manifest_url != wrapper_url:
        errors.append(
            f"{label}: wrapper <PluginURL> {wrapper_url} does not exactly match "
            f"the fetched .plg pluginURL {manifest_url}"
        )
        return False
    return True


def fetch_and_compare_plugin_manifest(
    label: str | Path,
    wrapper_url: str,
    errors: list[str],
    *,
    resolver: Callable[[str], ResolvedHTTPSURL] = resolve_public_https_url,
    requester: Callable[
        [ResolvedHTTPSURL], tuple[int, str | None, bytes]
    ] = request_pinned_https_body,
) -> bool:
    current = wrapper_url
    visited: set[str] = set()
    for _ in range(MAX_REDIRECTS + 1):
        if current in visited:
            errors.append(f"{label}: .plg redirect loop: {current}")
            return False
        visited.add(current)
        try:
            target = resolver(current)
            status, location, body = requester(target)
        except (
            OSError,
            TimeoutError,
            ValueError,
            ssl.SSLError,
            http.client.HTTPException,
        ) as exc:
            errors.append(f"{label}: .plg not anonymously fetchable: {current} ({exc})")
            return False
        if 300 <= status < 400:
            if not location:
                errors.append(
                    f"{label}: .plg HTTP {status} redirect has no Location: {current}"
                )
                return False
            current = urllib.parse.urljoin(current, location)
            continue
        if status >= 400:
            errors.append(f"{label}: .plg returned HTTP {status}: {current}")
            return False
        return compare_plugin_manifest_url(str(label), wrapper_url, body, errors)
    errors.append(f"{label}: .plg exceeded {MAX_REDIRECTS} redirects: {wrapper_url}")
    return False


def submission_text_artifacts(repository: Path) -> list[Path]:
    """Return only files that CA consumes, not arbitrary repository content."""
    candidates: set[Path] = set()
    for path in repository.iterdir():
        if not path.is_file():
            continue
        name = path.name.lower()
        if (
            path.name.startswith("LICENSE")
            or name in {"ca_profile.xml", "description.md"}
            or name.startswith("icon.")
            or path.suffix.lower() == ".plg"
        ):
            candidates.add(path)
    plugins_dir = repository / "plugins"
    if plugins_dir.is_dir():
        candidates.update(path for path in plugins_dir.glob("*.xml") if path.is_file())
    return sorted(candidates)


def scan_placeholders(repository: Path, errors: list[str]) -> None:
    for path in submission_text_artifacts(repository):
        if path.suffix.lower() not in TEXT_SUFFIXES and not path.name.startswith(
            "LICENSE"
        ):
            continue
        text = read_text(path, errors)
        if text is not None and PLACEHOLDER.search(text):
            errors.append(
                f"{path.relative_to(repository)} contains a placeholder or TODO"
            )


def png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        data = path.read_bytes()[:24]
    except OSError:
        return None
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repository",
        type=Path,
        help="repository root containing LICENSE and ca_profile.xml",
    )
    parser.add_argument(
        "--check-urls", action="store_true", help="perform anonymous network requests"
    )
    args = parser.parse_args()
    repository = args.repository.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    urls: list[tuple[str, str]] = []
    plugin_manifests: list[tuple[Path, str]] = []

    if not repository.is_dir():
        errors.append(f"repository is not a directory: {repository}")
    else:
        scan_placeholders(repository, errors)

    license_path = repository / "LICENSE"
    license_text = read_text(license_path, errors) if license_path.is_file() else None
    if license_text is None or not license_text.strip():
        errors.append(
            "missing or empty root LICENSE; CA requires an OSI-approved license"
        )
    else:
        warnings.append(
            "confirm the root LICENSE is OSI-approved; local preflight does not classify licenses"
        )

    profile_path = repository / "ca_profile.xml"
    if not profile_path.is_file():
        errors.append("missing root ca_profile.xml")
    else:
        profile = parse_xml(profile_path, errors)
        if profile is not None:
            if profile.tag != "CommunityApplications":
                errors.append(
                    f"ca_profile.xml: expected <CommunityApplications> root, got <{profile.tag}>"
                )
            else:
                validate_child_tags(profile_path, profile, PROFILE_TAGS, errors)
                validate_singleton_tags(
                    "ca_profile.xml",
                    profile,
                    PROFILE_TAGS,
                    REQUIRED_PROFILE_TAGS,
                    errors,
                )
            profile_nodes = direct_nodes(profile, "Profile")
            if len(profile_nodes) == 1 and not node_text(profile, "Profile"):
                errors.append(
                    "ca_profile.xml: <Profile> is required and must be non-empty"
                )
            for tag in RECOMMENDED_PROFILE_TAGS:
                if not node_text(profile, tag):
                    warnings.append(f"ca_profile.xml: recommended <{tag}> is missing")
            urls.extend(collect_urls(profile_path, profile, errors))

    plugins_dir = repository / "plugins"
    plugin_files = sorted(plugins_dir.glob("*.xml")) if plugins_dir.is_dir() else []
    if not plugin_files:
        errors.append("missing plugin wrapper XML under plugins/")

    for path in plugin_files:
        root = parse_xml(path, errors)
        if root is None:
            continue
        relative = path.relative_to(repository)
        if root.tag != "Plugin":
            errors.append(f"{relative}: expected <Plugin> root, got <{root.tag}>")
        else:
            validate_child_tags(relative, root, PLUGIN_TAGS, errors)
            validate_singleton_tags(
                relative,
                root,
                PLUGIN_TAGS,
                REQUIRED_PLUGIN_TAGS,
                errors,
            )
        name_nodes = direct_nodes(root, "Name")
        if len(name_nodes) == 1 and not node_text(root, "Name"):
            errors.append(f"{relative}: <Name> is required and must be non-empty")
        plugin_url_nodes = direct_nodes(root, "PluginURL")
        if len(plugin_url_nodes) == 1:
            plugin_url = "".join(plugin_url_nodes[0].itertext()).strip()
            if not plugin_url:
                errors.append(
                    f"{relative}: <PluginURL> is required and must be non-empty"
                )
            elif not urllib.parse.urlsplit(plugin_url).path.lower().endswith(".plg"):
                errors.append(
                    f"{relative}: <PluginURL> must point to a .plg: {plugin_url}"
                )
            else:
                plugin_manifests.append((relative, plugin_url))
        for tag in RECOMMENDED_PLUGIN_TAGS:
            if not node_text(root, tag):
                warnings.append(f"{relative}: recommended <{tag}> is missing")
        support = node_text(root, "Support")
        if support and "forums.unraid.net" not in support:
            warnings.append(
                f"{relative}: prefer a dedicated forums.unraid.net support thread"
            )
        beta = node_text(root, "Beta")
        if beta and beta.lower() not in {"true", "false"}:
            errors.append(f"{relative}: optional <Beta> must be true or false")
        elif beta.lower() == "false":
            warnings.append(
                f"{relative}: remove <Beta>false</Beta>; only true survives feed projection"
            )
        urls.extend(collect_urls(path, root, errors))

    icon_pngs = [
        path
        for path in submission_text_artifacts(repository)
        if path.suffix.lower() == ".png" and "icon" in path.name.lower()
    ]
    for png in icon_pngs:
        dimensions = png_dimensions(png)
        relative = png.relative_to(repository)
        if dimensions is None:
            errors.append(f"{relative}: not a valid PNG")
        elif dimensions != (256, 256):
            warnings.append(
                f"{relative}: listing icon convention is 256x256; found {dimensions[0]}x{dimensions[1]}"
            )

    reachable_urls = 0
    if args.check_urls:
        for label, url in urls:
            if "<PluginURL>" in label:
                continue
            reachable_urls += int(check_url(label, url, errors))
        for relative, plugin_url in plugin_manifests:
            reachable_urls += int(
                fetch_and_compare_plugin_manifest(relative, plugin_url, errors)
            )

    for item in warnings:
        print(f"WARN: {item}", file=sys.stderr)
    if errors:
        print("Unraid CA preflight failed:", file=sys.stderr)
        for item in errors:
            print(f"- {item}", file=sys.stderr)
        return 1
    if args.check_urls:
        url_summary = f"{reachable_urls} publicly reachable URL(s)"
    else:
        url_summary = f"{len(urls)} HTTPS URL(s), network validation not run"
    print(
        f"Unraid CA preflight passed: {len(plugin_files)} plugin wrapper(s), "
        f"{url_summary}, {len(warnings)} warning(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
