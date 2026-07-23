#!/usr/bin/env python3
"""Regression tests for the Unraid Community Applications preflight validator."""

from __future__ import annotations

import importlib.util
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_DIR = Path(__file__).resolve().parent.parent
VALIDATOR = SKILL_DIR / "scripts/validate_submission.py"


def load_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_submission_under_test", VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = load_validator()


def run_validator(repository: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (sys.executable, str(VALIDATOR), str(repository), *extra),
        cwd=repository,
        check=False,
        text=True,
        capture_output=True,
    )


def materialize_repository(root: Path) -> Path:
    repository = root / "ca-repository"
    plugins = repository / "plugins"
    plugins.mkdir(parents=True)
    (repository / "LICENSE").write_text(
        "MIT License\n\nCopyright 2026 Review QA\n", encoding="utf-8"
    )
    (repository / "ca_profile.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<CommunityApplications>
  <Profile>Review QA applications</Profile>
  <Icon>https://assets.invalid/icon.svg</Icon>
  <WebPage>https://project.invalid/</WebPage>
</CommunityApplications>
""",
        encoding="utf-8",
    )
    (plugins / "fan-watch.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<Plugin>
  <Name>Fan Watch</Name>
  <PluginURL>https://downloads.invalid/fan-watch.plg</PluginURL>
  <Support>https://project.invalid/issues</Support>
  <Project>https://project.invalid/</Project>
  <Overview>Monitors fan health.</Overview>
  <Category>Tools:System</Category>
</Plugin>
""",
        encoding="utf-8",
    )
    return repository


class SubmissionValidatorTests(unittest.TestCase):
    def test_valid_offline_repository_reports_https_urls_without_public_claim(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            result = run_validator(repository)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("HTTPS URL(s)", result.stdout)
            self.assertIn("network validation not run", result.stdout)
            self.assertNotIn("public URL(s)", result.stdout)

    def test_offline_validation_rejects_embedded_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            wrapper = repository / "plugins/fan-watch.xml"
            wrapper.write_text(
                wrapper.read_text(encoding="utf-8").replace(
                    "https://downloads.invalid/fan-watch.plg",
                    "https://user:password@downloads.invalid/fan-watch.plg",
                ),
                encoding="utf-8",
            )
            result = run_validator(repository)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("embedded URL credentials are not allowed", result.stderr)

    def test_offline_validation_rejects_private_literal_and_repeated_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            wrapper = repository / "plugins/fan-watch.xml"
            wrapper.write_text(
                wrapper.read_text(encoding="utf-8").replace(
                    "</Plugin>",
                    "  <ReadMe>https://assets.invalid/readme.md</ReadMe>\n"
                    "  <ReadMe>https://127.0.0.1/private.md</ReadMe>\n"
                    "</Plugin>",
                ),
                encoding="utf-8",
            )
            result = run_validator(repository)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("<ReadMe> #2", result.stderr)
            self.assertIn("non-public literal address 127.0.0.1", result.stderr)

    def test_offline_validation_rejects_noncanonical_numeric_loopback_hosts(
        self,
    ) -> None:
        for host in ("2130706433", "0x7f000001", "0177.0.0.1", "127.1"):
            with self.subTest(host=host):
                with self.assertRaisesRegex(ValueError, "noncanonical numeric host"):
                    validator.validate_https_url_syntax(f"https://{host}/fan-watch.plg")

    def test_offline_validation_rejects_unicode_dot_loopback_hosts(self) -> None:
        for separator in (
            "\N{IDEOGRAPHIC FULL STOP}",
            "\N{FULLWIDTH FULL STOP}",
            "\N{HALFWIDTH IDEOGRAPHIC FULL STOP}",
        ):
            with self.subTest(separator=separator):
                host = separator.join(("127", "0", "0", "1"))
                with self.assertRaisesRegex(
                    ValueError, "non-public literal address 127.0.0.1"
                ):
                    validator.validate_https_url_syntax(f"https://{host}/fan-watch.plg")

    def test_offline_validation_rejects_root_dotted_loopback_hosts(self) -> None:
        for host in (
            "127.0.0.1.",
            "127.0.0.1\N{IDEOGRAPHIC FULL STOP}",
            "127\N{IDEOGRAPHIC FULL STOP}0\N{IDEOGRAPHIC FULL STOP}0"
            "\N{IDEOGRAPHIC FULL STOP}1.",
            "127\N{FULLWIDTH FULL STOP}0\N{FULLWIDTH FULL STOP}0"
            "\N{FULLWIDTH FULL STOP}1\N{FULLWIDTH FULL STOP}",
            "127\N{HALFWIDTH IDEOGRAPHIC FULL STOP}0"
            "\N{HALFWIDTH IDEOGRAPHIC FULL STOP}0"
            "\N{HALFWIDTH IDEOGRAPHIC FULL STOP}1"
            "\N{HALFWIDTH IDEOGRAPHIC FULL STOP}",
        ):
            with self.subTest(host=host):
                with self.assertRaisesRegex(
                    ValueError, "non-public literal address 127.0.0.1"
                ):
                    validator.validate_https_url_syntax(f"https://{host}/fan-watch.plg")

    def test_offline_validation_allows_trailing_root_dot_on_dns_name(self) -> None:
        parsed = validator.validate_https_url_syntax(
            "https://downloads.invalid./fan-watch.plg"
        )
        self.assertEqual(parsed.hostname, "downloads.invalid.")

    def test_unsupported_profile_and_plugin_tags_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            profile = repository / "ca_profile.xml"
            profile.write_text(
                profile.read_text(encoding="utf-8").replace(
                    "</CommunityApplications>",
                    "  <Name>legacy author field</Name>\n</CommunityApplications>",
                ),
                encoding="utf-8",
            )
            wrapper = repository / "plugins/fan-watch.xml"
            wrapper.write_text(
                wrapper.read_text(encoding="utf-8").replace(
                    "</Plugin>",
                    "  <Requires>privileged host access</Requires>\n"
                    "  <Description>legacy description</Description>\n"
                    "  <Screenshot>https://assets.invalid/screen.png</Screenshot>\n"
                    "</Plugin>",
                ),
                encoding="utf-8",
            )
            result = run_validator(repository)
            self.assertNotEqual(result.returncode, 0)
            for tag in ("Name", "Requires", "Description", "Screenshot"):
                self.assertIn(f"unsupported <{tag}>", result.stderr)

    def test_required_plugin_fields_must_be_exactly_one_direct_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            wrapper = repository / "plugins/fan-watch.xml"
            wrapper.write_text(
                wrapper.read_text(encoding="utf-8").replace(
                    "</Plugin>",
                    "  <Name>Duplicate Fan Watch</Name>\n"
                    "  <PluginURL>https://downloads.invalid/duplicate.plg</PluginURL>\n"
                    "</Plugin>",
                ),
                encoding="utf-8",
            )
            result = run_validator(repository)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "expected exactly one direct <Name>, found 2",
            result.stderr,
        )
        self.assertIn(
            "expected exactly one direct <PluginURL>, found 2",
            result.stderr,
        )

    def test_supported_optional_fields_are_direct_singletons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            profile = repository / "ca_profile.xml"
            profile.write_text(
                profile.read_text(encoding="utf-8").replace(
                    "</CommunityApplications>",
                    "  <Icon>https://assets.invalid/duplicate.svg</Icon>\n"
                    "</CommunityApplications>",
                ),
                encoding="utf-8",
            )
            wrapper = repository / "plugins/fan-watch.xml"
            wrapper.write_text(
                wrapper.read_text(encoding="utf-8").replace(
                    "</Plugin>",
                    "  <Support>https://project.invalid/discussions</Support>\n"
                    "</Plugin>",
                ),
                encoding="utf-8",
            )
            result = run_validator(repository)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "ca_profile.xml: expected at most one direct <Icon>, found 2",
            result.stderr,
        )
        self.assertIn(
            "plugins/fan-watch.xml: expected at most one direct <Support>, found 2",
            result.stderr,
        )

    def test_required_fields_nested_below_supported_tags_do_not_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            wrapper = repository / "plugins/fan-watch.xml"
            wrapper.write_text(
                wrapper.read_text(encoding="utf-8")
                .replace("  <Name>Fan Watch</Name>\n", "")
                .replace(
                    "<Overview>Monitors fan health.</Overview>",
                    "<Overview>Monitors <Name>Fan Watch</Name> health.</Overview>",
                ),
                encoding="utf-8",
            )
            result = run_validator(repository)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "expected exactly one direct <Name>, found 0",
            result.stderr,
        )

    def test_mastodon_url_does_not_trigger_todo_placeholder_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            profile = repository / "ca_profile.xml"
            profile.write_text(
                profile.read_text(encoding="utf-8").replace(
                    "https://project.invalid/",
                    "https://mastodon.social/@fanwatch",
                ),
                encoding="utf-8",
            )
            result = run_validator(repository)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_placeholders_are_rejected_in_license_markdown_and_svg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            (repository / "LICENSE").write_text(
                "Copyright {{YEAR}} {{COPYRIGHT_HOLDER}}\n", encoding="utf-8"
            )
            (repository / "DESCRIPTION.md").write_text(
                "{{ONE_SENTENCE_VALUE_PROPOSITION}}\n", encoding="utf-8"
            )
            (repository / "icon.svg").write_text(
                "<svg><title>{{APPLICATION_NAME}}</title></svg>\n", encoding="utf-8"
            )
            result = run_validator(repository)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("LICENSE contains a placeholder or TODO", result.stderr)
            self.assertIn(
                "DESCRIPTION.md contains a placeholder or TODO", result.stderr
            )
            self.assertIn("icon.svg contains a placeholder or TODO", result.stderr)

    def test_invalid_xml_roots_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            (repository / "ca_profile.xml").write_text(
                "<Profile>wrong root</Profile>\n", encoding="utf-8"
            )
            (repository / "plugins/fan-watch.xml").write_text(
                "<Application/>\n", encoding="utf-8"
            )
            result = run_validator(repository)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("expected <CommunityApplications> root", result.stderr)
            self.assertIn("expected <Plugin> root", result.stderr)

    def test_malformed_icon_png_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            (repository / "icon.png").write_bytes(b"not a png")
            result = run_validator(repository)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("icon.png: not a valid PNG", result.stderr)

    def test_beta_false_is_an_advisory_projection_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            wrapper = repository / "plugins/fan-watch.xml"
            wrapper.write_text(
                wrapper.read_text(encoding="utf-8").replace(
                    "</Plugin>", "  <Beta>false</Beta>\n</Plugin>"
                ),
                encoding="utf-8",
            )
            result = run_validator(repository)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("only true survives feed projection", result.stderr)

    def test_redirects_resolve_and_pin_each_destination(self) -> None:
        first = validator.ResolvedHTTPSURL(
            url="https://downloads.invalid/fan-watch.plg",
            hostname="downloads.invalid",
            port=443,
            request_target="/fan-watch.plg",
            addresses=((socket.AF_INET, "8.8.8.8"),),
        )
        second = validator.ResolvedHTTPSURL(
            url="https://cdn.invalid/fan-watch.plg",
            hostname="cdn.invalid",
            port=443,
            request_target="/fan-watch.plg",
            addresses=((socket.AF_INET, "1.1.1.1"),),
        )
        resolver = mock.Mock(side_effect=(first, second))
        requester = mock.Mock(
            side_effect=((302, "https://cdn.invalid/fan-watch.plg"), (200, None))
        )
        errors: list[str] = []
        validator.check_url(
            "plugin",
            first.url,
            errors,
            resolver=resolver,
            requester=requester,
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            [call.args[0] for call in requester.call_args_list], [first, second]
        )

    def test_plugin_manifest_fetch_pins_redirects_and_matches_wrapper_url(self) -> None:
        wrapper_url = "https://downloads.invalid/fan-watch.plg"
        first = validator.ResolvedHTTPSURL(
            url=wrapper_url,
            hostname="downloads.invalid",
            port=443,
            request_target="/fan-watch.plg",
            addresses=((socket.AF_INET, "8.8.8.8"),),
        )
        second = validator.ResolvedHTTPSURL(
            url="https://cdn.invalid/releases/fan-watch.plg",
            hostname="cdn.invalid",
            port=443,
            request_target="/releases/fan-watch.plg",
            addresses=((socket.AF_INET, "1.1.1.1"),),
        )
        manifest = f"""<?xml version="1.0"?>
<!DOCTYPE PLUGIN [
<!ENTITY pluginURL "{wrapper_url}">
]>
<PLUGIN name="fan-watch" pluginURL="&pluginURL;"/>
""".encode()
        resolver = mock.Mock(side_effect=(first, second))
        requester = mock.Mock(
            side_effect=(
                (302, second.url, b""),
                (200, None, manifest),
            )
        )
        errors: list[str] = []
        matched = validator.fetch_and_compare_plugin_manifest(
            "plugins/fan-watch.xml",
            wrapper_url,
            errors,
            resolver=resolver,
            requester=requester,
        )
        self.assertTrue(matched)
        self.assertEqual(errors, [])
        self.assertEqual(
            [call.args[0] for call in requester.call_args_list], [first, second]
        )

    def test_plugin_manifest_url_mismatch_is_rejected(self) -> None:
        errors: list[str] = []
        matched = validator.compare_plugin_manifest_url(
            "plugins/fan-watch.xml",
            "https://downloads.invalid/fan-watch.plg",
            (
                b'<PLUGIN name="fan-watch" '
                b'pluginURL="https://downloads.invalid/other.plg"/>'
            ),
            errors,
        )
        self.assertFalse(matched)
        self.assertIn("does not exactly match", errors[0])

    def test_authorized_network_mode_compares_each_plugin_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            with (
                mock.patch.object(
                    sys, "argv", [str(VALIDATOR), str(repository), "--check-urls"]
                ),
                mock.patch.object(validator, "check_url", return_value=True),
                mock.patch.object(
                    validator,
                    "fetch_and_compare_plugin_manifest",
                    return_value=True,
                ) as compare_manifest,
            ):
                result = validator.main()
        self.assertEqual(result, 0)
        compare_manifest.assert_called_once()
        self.assertEqual(
            compare_manifest.call_args.args[:2],
            (
                Path("plugins/fan-watch.xml"),
                "https://downloads.invalid/fan-watch.plg",
            ),
        )

    def test_network_mode_does_not_fetch_ambiguous_plugin_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = materialize_repository(Path(tmp))
            wrapper = repository / "plugins/fan-watch.xml"
            wrapper.write_text(
                wrapper.read_text(encoding="utf-8").replace(
                    "</Plugin>",
                    "  <PluginURL>https://downloads.invalid/duplicate.plg</PluginURL>\n"
                    "</Plugin>",
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    sys, "argv", [str(VALIDATOR), str(repository), "--check-urls"]
                ),
                mock.patch.object(validator, "check_url", return_value=True),
                mock.patch.object(
                    validator,
                    "fetch_and_compare_plugin_manifest",
                    return_value=True,
                ) as compare_manifest,
            ):
                result = validator.main()
        self.assertNotEqual(result, 0)
        compare_manifest.assert_not_called()

    def test_skill_documents_network_manifest_url_comparison(self) -> None:
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        guide_text = (SKILL_DIR / "references/submission-guide.md").read_text(
            encoding="utf-8"
        )
        for text in (skill_text, guide_text):
            self.assertIn("--check-urls", text)
            self.assertIn("exactly matches", text)
            self.assertIn("manifest", text)

    def test_skill_frontmatter_explicitly_excludes_docker_container_apps(self) -> None:
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = skill_text.split("---", 2)[1]
        self.assertIn(
            "Do not use for Docker or container application submissions",
            frontmatter,
        )
        self.assertIn("Unraid plugins only", frontmatter)

    def test_openai_short_description_is_unraid_plugin_specific(self) -> None:
        metadata = (SKILL_DIR / "agents/openai.yaml").read_text(encoding="utf-8")
        short_description = next(
            line for line in metadata.splitlines() if "short_description:" in line
        )
        self.assertIn("Unraid plugin", short_description)
        self.assertIn("Community Applications", short_description)

    def test_pinned_connection_uses_validated_ip_and_original_tls_name(self) -> None:
        class FakeSocket:
            def __init__(self) -> None:
                self.timeout = None
                self.connected = None

            def settimeout(self, timeout):
                self.timeout = timeout

            def connect(self, address):
                self.connected = address

            def close(self):
                return None

        class FakeContext:
            def __init__(self) -> None:
                self.server_hostname = None

            def wrap_socket(self, sock, *, server_hostname):
                self.server_hostname = server_hostname
                return sock

        raw_socket = FakeSocket()
        context = FakeContext()
        connection = validator.PinnedHTTPSConnection(
            "downloads.invalid",
            443,
            (socket.AF_INET, "8.8.8.8"),
            timeout=15,
            context=context,
        )
        with (
            mock.patch.object(validator.socket, "socket", return_value=raw_socket),
            mock.patch.object(
                validator.socket,
                "getaddrinfo",
                side_effect=AssertionError(
                    "pinned connection must not resolve DNS again"
                ),
            ),
        ):
            connection.connect()
        self.assertEqual(raw_socket.connected, ("8.8.8.8", 443))
        self.assertEqual(context.server_hostname, "downloads.invalid")

    def test_dns_resolution_rejects_any_non_public_answer(self) -> None:
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]
        with mock.patch.object(
            validator.socket, "getaddrinfo", return_value=answers
        ) as resolver:
            with self.assertRaisesRegex(
                ValueError, "resolves to non-public address 127.0.0.1"
            ):
                validator.resolve_public_https_url(
                    "https://downloads.invalid/fan-watch.plg"
                )
        resolver.assert_called_once_with(
            "downloads.invalid", 443, type=socket.SOCK_STREAM
        )


if __name__ == "__main__":
    unittest.main()
