#!/usr/bin/env python3
"""Regression tests for the bundled Unraid plugin validator and fallback assets."""

from __future__ import annotations

import json
import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
VALIDATOR = SKILL_DIR / "scripts/validate_unraid_plugin.py"
ASSETS = SKILL_DIR / "assets"


def run(
    *args: str, cwd: Path, check: bool = True, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=True,
        env=env,
    )


def replace_tokens(text: str) -> str:
    replacements = {
        "PLUGIN_ID": "fan-watch",
        "PLUGIN_TITLE": "Fan Watch",
        "PLUGIN_PASCAL": "FanWatch",
        "PLUGIN_NAMESPACE": "fanWatch",
        "AUTHOR_NAME": "Review & QA",
        "OWNER/fan-watch": "example/fan-watch",
        "OWNER/PLUGIN_ID": "example/fan-watch",
        "MIN_UNRAID_VERSION": "6.12.0",
        "ICON_NAME": "tachometer",
        "MENU_LABEL": "Settings",
        "PLUGIN_PAGE_TAG": "system",
        "YEAR": "2026",
        "COPYRIGHT_HOLDER": "Review QA",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def materialize_api(root: Path) -> Path:
    target = root / "unraid-api-plugin-fan-watch"
    shutil.copytree(ASSETS / "api-plugin", target)
    renames = {
        "package.json.template": "package.json",
        "src/index.ts.template": "src/index.ts",
        "test/plugin.spec.ts.template": "test/plugin.spec.ts",
        "LICENSE-MIT.template": "LICENSE",
    }
    for old, new in renames.items():
        source = target / old
        destination = target / new
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
    for path in target.rglob("*"):
        if path.is_file():
            path.write_text(
                replace_tokens(path.read_text(encoding="utf-8")), encoding="utf-8"
            )
    return target


def materialize_os(root: Path) -> Path:
    target = root / "fan-watch"
    payload = target / "src/usr/local/emhttp/plugins/fan-watch"
    payload.mkdir(parents=True)
    (payload / "FanWatch.page").write_text(
        'Menu="Settings"\nTitle="Fan Watch"\n---\nready\n', encoding="utf-8"
    )
    (target / "LICENSE").write_text(
        "MIT License\n\nCopyright 2026 Review QA\n", encoding="utf-8"
    )
    build = target / "build-plg.sh"
    build.write_text(
        replace_tokens((ASSETS / "build-plg.sh.template").read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    build.chmod(0o755)
    (target / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    env = dict(os.environ, DATE="2026.07.22.2200", BUILD_NUMBER="42")
    run("./build-plg.sh", cwd=target, env=env)
    return target


class ValidatorTests(unittest.TestCase):
    def test_fallback_os_build_emits_exact_reproducible_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_os(Path(tmp))
            manifest = (target / "fan-watch.plg").read_text(encoding="utf-8")
            package_name = re.search(
                r'<!ENTITY packageName\s+"([^"]+)">', manifest
            ).group(1)  # type: ignore[union-attr]
            versioned = target / package_name
            self.assertTrue(versioned.is_file())
            self.assertEqual(
                (target / "fan-watch.tgz").read_bytes(), versioned.read_bytes()
            )
            result = run(str(VALIDATOR), str(target), "--type", "os", cwd=target)
            self.assertIn("passed with 0 warning(s)", result.stdout)

            versioned.unlink()
            run("./build-plg.sh", "--tgz-only", cwd=target)
            self.assertTrue(versioned.is_file())

            versioned.write_bytes(versioned.read_bytes() + b"tamper")
            failed = run(
                str(VALIDATOR), str(target), "--type", "os", cwd=target, check=False
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("packageMD5 does not match", failed.stderr)

    def test_fallback_install_preserves_plugin_tree_executable_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_os(Path(tmp))
            payload = target / "src/usr/local/emhttp/plugins/fan-watch"
            for directory in ("bin", "sbin", "libexec"):
                helper = payload / directory / "helper"
                helper.parent.mkdir()
                helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                helper.chmod(0o755)

            env = dict(os.environ, DATE="2026.07.22.2200", BUILD_NUMBER="42")
            run("./build-plg.sh", cwd=target, env=env)
            manifest = (target / "fan-watch.plg").read_text(encoding="utf-8")
            package_name = re.search(
                r'<!ENTITY packageName\s+"([^"]+)">', manifest
            ).group(1)  # type: ignore[union-attr]
            install_match = re.search(
                r'<FILE Run="/bin/bash">\s*<INLINE><!\[CDATA\[(.*?)\]\]></INLINE>',
                manifest,
                re.DOTALL,
            )
            self.assertIsNotNone(install_match)

            install_root = Path(tmp) / "installed-plugin"
            config_root = Path(tmp) / "plugin-config"
            config_root.mkdir()
            shutil.copy2(target / package_name, config_root / package_name)
            install_script = install_match.group(1)  # type: ignore[union-attr]
            install_script = install_script.replace(
                'PLGDIR="/usr/local/emhttp/plugins/fan-watch"',
                f'PLGDIR="{install_root}"',
            ).replace(
                'CFGDIR="/boot/config/plugins/fan-watch"',
                f'CFGDIR="{config_root}"',
            )
            install_script = install_script.replace(
                'chown -R root:root "$PLGDIR"',
                ": # ownership is outside this isolated mode regression",
            )
            run("/bin/bash", "-c", install_script, cwd=target)

            for directory in ("bin", "sbin", "libexec"):
                mode = (install_root / directory / "helper").stat().st_mode & 0o777
                self.assertEqual(mode, 0o755, directory)
            page_mode = (install_root / "FanWatch.page").stat().st_mode & 0o777
            self.assertEqual(page_mode, 0o644)

    def test_page_polling_uses_configured_interval_safely(self) -> None:
        page = replace_tokens((ASSETS / "page.template").read_text(encoding="utf-8"))
        delay_function = re.search(
            r"(function fanWatchPollDelay\(value\)\{.*?^\})",
            page,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(delay_function)
        behavior = run(
            "node",
            "-e",
            delay_function.group(1)  # type: ignore[union-attr]
            + "\nconsole.log(JSON.stringify([5, 30, 600, 4, 601, 'bad', 5.5].map(fanWatchPollDelay)));",
            cwd=SKILL_DIR,
        )
        self.assertEqual(
            json.loads(behavior.stdout),
            [5000, 30000, 600000, 30000, 30000, 30000, 30000],
        )
        self.assertIn("fanWatchScheduleRefresh(d.interval)", page)
        self.assertNotIn("setInterval(", page)

    def test_minimum_unraid_compatibility_is_an_explicit_placeholder(self) -> None:
        raw_build = (ASSETS / "build-plg.sh.template").read_text(encoding="utf-8")
        self.assertIn('MIN_UNRAID="MIN_UNRAID_VERSION"', raw_build)
        self.assertNotIn('min="6.12.0"', raw_build)

        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_os(Path(tmp))
            manifest = (target / "fan-watch.plg").read_text(encoding="utf-8")
            self.assertIn('min="6.12.0"', manifest)

            unconfigured = replace_tokens(raw_build).replace(
                'MIN_UNRAID="6.12.0"', 'MIN_UNRAID="MIN_UNRAID_VERSION"'
            )
            (target / "build-plg.sh").write_text(unconfigured, encoding="utf-8")
            result = run(
                str(VALIDATOR), str(target), "--type", "os", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "build-plg.sh: unresolved scaffold placeholder", result.stderr
            )

    def test_common_web_text_assets_are_scanned_for_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_os(Path(tmp))
            asset_dir = target / "src/usr/local/emhttp/plugins/fan-watch" / "assets"
            asset_dir.mkdir()
            asset_names = (
                "unresolved.js",
                "unresolved.css",
                "unresolved.html",
                "unresolved.tsx",
            )
            for asset_name in asset_names:
                (asset_dir / asset_name).write_text("PLUGIN_TITLE\n", encoding="utf-8")

            result = run(
                str(VALIDATOR), str(target), "--type", "os", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            for asset_name in asset_names:
                self.assertIn(
                    f"assets/{asset_name}: unresolved scaffold placeholder",
                    result.stderr,
                )

    def test_fallback_api_passes_and_missing_host_peer_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("passed with 0 warning(s)", result.stdout)

            entry = target / "src/index.ts"
            entry.write_text(
                'import { x } from "@unraid/shared";\n'
                + entry.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            failed = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn(
                "peerDependencies must include imported host package @unraid/shared",
                failed.stderr,
            )

    def test_hybrid_auto_detection_validates_both_layers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hybrid"
            os_target = materialize_os(root.parent)
            os_target.rename(root)
            materialize_api(root)
            package = root / "unraid-api-plugin-fan-watch/package.json"
            data = json.loads(package.read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "unraid-api-plugin-fan-watch")
            result = run(str(VALIDATOR), str(root), cwd=root)
            self.assertIn("Unraid hybrid plugin validation passed", result.stdout)

    def test_private_runtime_helper_without_execute_mode_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_os(Path(tmp))
            helper = target / "source/usr/local/fan-watch/bin/helper"
            helper.parent.mkdir(parents=True)
            helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            helper.chmod(0o644)
            result = run(
                str(VALIDATOR), str(target), "--type", "os", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "staged private runtime helper is not executable", result.stderr
            )

    def test_placeholder_suffix_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_os(Path(tmp))
            page = target / "src/usr/local/emhttp/plugins/fan-watch/FanWatch.page"
            page.write_text(
                page.read_text(encoding="utf-8") + "VERSION_PLACEHOLDER\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "os", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unresolved scaffold placeholder", result.stderr)

    def test_minimal_os_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_os(Path(tmp))
            (target / "fan-watch.plg").write_text("<PLUGIN/>\n", encoding="utf-8")
            result = run(
                str(VALIDATOR), str(target), "--type", "os", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing required attribute name", result.stderr)
            self.assertIn("no installable package <FILE>", result.stderr)

    def test_page_template_placeholders_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_os(Path(tmp))
            page = target / "src/usr/local/emhttp/plugins/fan-watch/FanWatch.page"
            template = (ASSETS / "page.template").read_text(encoding="utf-8")
            sentinels = (
                "PLUGIN_ID",
                "PagePrefix",
                "PLUGIN_TITLE",
                "MENU_LABEL",
                "ICON_NAME",
                "PLUGIN_PAGE_TAG",
                "PLUGIN_NAMESPACE",
            )
            for sentinel in sentinels:
                with self.subTest(sentinel=sentinel):
                    self.assertIn(sentinel, template)
                    page.write_text(
                        f'Menu="Settings"\nTitle="Fan Watch"\n---\n{sentinel}\n',
                        encoding="utf-8",
                    )
                    result = run(
                        str(VALIDATOR),
                        str(target),
                        "--type",
                        "os",
                        cwd=target,
                        check=False,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unresolved scaffold placeholder", result.stderr)

    def test_generic_page_words_are_not_scaffold_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_os(Path(tmp))
            page = target / "src/usr/local/emhttp/plugins/fan-watch/FanWatch.page"
            page.write_text(
                'Menu="MENU"\nTitle="TITLE"\nIcon="icon-ICON"\nTag="TAG"\n'
                "---\nTITLE MENU ICON TAG are ordinary page content.\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "os", cwd=target, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_extensionless_license_placeholder_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_os(Path(tmp))
            (target / "LICENSE").write_text(
                "Copyright (c) YEAR COPYRIGHT_HOLDER\n", encoding="utf-8"
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "os", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("LICENSE: unresolved scaffold placeholder", result.stderr)

    def test_graphql_operations_and_input_fields_require_security_metadata(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            package_path = target / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["peerDependencies"].update(
                {
                    "@nestjs/graphql": "^13.1.0",
                    "@unraid/shared": "^4.25.2",
                    "class-validator": "^0.14.2",
                }
            )
            package_path.write_text(json.dumps(package), encoding="utf-8")
            (target / "src/index.ts").write_text(
                """
import { Module } from "@nestjs/common";
import { Args, Field, InputType, Query, Resolver } from "@nestjs/graphql";

// UsePermissions is intentionally only a comment.
@InputType()
class UnsafeInput {
  @Field()
  value!: string;
}

@Resolver()
class UnsafeResolver {
  @Query(() => String)
  unsafe(@Args("input") input: UnsafeInput): string {
    return input.value;
  }
}

@Module({ providers: [UnsafeResolver] })
class FanWatchApiModule {}

export const adapter = "nestjs";
export const ApiModule = FanWatchApiModule;
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "resolver operation unsafe has no explicit per-operation @UsePermissions decorator",
                result.stderr,
            )
            self.assertIn(
                "GraphQL input field UnsafeInput.value has no class-validator decorator",
                result.stderr,
            )

    def test_secured_graphql_operation_and_validated_input_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            package_path = target / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["peerDependencies"].update(
                {
                    "@nestjs/graphql": "^13.1.0",
                    "@unraid/shared": "^4.25.2",
                    "class-validator": "^0.14.2",
                }
            )
            package_path.write_text(json.dumps(package), encoding="utf-8")
            (target / "src/index.ts").write_text(
                """
import { Module } from "@nestjs/common";
import { Args, Field, InputType, Query, Resolver } from "@nestjs/graphql";
import { UsePermissions } from "@unraid/shared";
import { IsString } from "class-validator";

@InputType()
class SafeInput {
  @Field()
  @IsString()
  value!: string;
}

@Resolver()
class SafeResolver {
  @Query(() => String)
  @UsePermissions()
  safe(@Args("input") input: SafeInput): string {
    return input.value;
  }
}

@Module({ providers: [SafeResolver] })
class FanWatchApiModule {}

export const adapter = "nestjs";
export const ApiModule = FanWatchApiModule;
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(str(VALIDATOR), str(target), "--type", "api", cwd=target)
            self.assertIn("passed with 0 warning(s)", result.stdout)

    def test_local_fake_use_permissions_decorator_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            package_path = target / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["peerDependencies"]["@nestjs/graphql"] = "^13.1.0"
            package_path.write_text(json.dumps(package), encoding="utf-8")
            (target / "src/index.ts").write_text(
                """
import { Module } from "@nestjs/common";
import { Query, Resolver } from "@nestjs/graphql";

function UsePermissions(): MethodDecorator {
  return () => undefined;
}

@Resolver()
class UnsafeResolver {
  @Query(() => String)
  @UsePermissions()
  unsafe(): string {
    return "unsafe";
  }
}

@Module({ providers: [UnsafeResolver] })
class FanWatchApiModule {}

export const adapter = "nestjs";
export const ApiModule = FanWatchApiModule;
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "resolver operation unsafe has no explicit per-operation @UsePermissions decorator",
                result.stderr,
            )

    def test_initialized_and_accessor_input_fields_require_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            package_path = target / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["peerDependencies"]["@nestjs/graphql"] = "^13.1.0"
            package_path.write_text(json.dumps(package), encoding="utf-8")
            (target / "src/index.ts").write_text(
                """
import { Module } from "@nestjs/common";
import { Field, InputType } from "@nestjs/graphql";

@InputType()
class UnsafeInput {
  @Field()
  initialized = "unsafe";

  @Field()
  get accessorBacked(): string {
    return this.initialized;
  }
}

@Module({})
class FanWatchApiModule {}

export const adapter = "nestjs";
export const ApiModule = FanWatchApiModule;
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "GraphQL input field UnsafeInput.initialized has no class-validator decorator",
                result.stderr,
            )
            self.assertIn(
                "GraphQL input field UnsafeInput.accessorBacked has no class-validator decorator",
                result.stderr,
            )

    def test_validated_initialized_and_accessor_input_fields_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            package_path = target / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["peerDependencies"].update(
                {
                    "@nestjs/graphql": "^13.1.0",
                    "class-validator": "^0.14.2",
                }
            )
            package_path.write_text(json.dumps(package), encoding="utf-8")
            (target / "src/index.ts").write_text(
                """
import { Module } from "@nestjs/common";
import { Field, InputType } from "@nestjs/graphql";
import { IsString } from "class-validator";

@InputType()
class SafeInput {
  @Field()
  @IsString()
  initialized = "safe";

  @Field()
  @IsString()
  get accessorBacked(): string {
    return this.initialized;
  }
}

@Module({})
class FanWatchApiModule {}

export const adapter = "nestjs";
export const ApiModule = FanWatchApiModule;
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_class_decorator_is_rejected_even_with_contract_shaped_test(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            package_path = target / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["peerDependencies"].update(
                {
                    "@nestjs/graphql": "^13.1.0",
                    "@unraid/shared": "^4.25.2",
                }
            )
            package_path.write_text(json.dumps(package), encoding="utf-8")
            (target / "src/index.ts").write_text(
                """
import { Module } from "@nestjs/common";
import { Query, Resolver } from "@nestjs/graphql";
import { UsePermissions } from "@unraid/shared";

function FanWatchPermissions(): ClassDecorator {
  return (target) => {
    for (const name of Object.getOwnPropertyNames(target.prototype)) {
      if (name === "constructor") continue;
      const descriptor = Object.getOwnPropertyDescriptor(target.prototype, name);
      if (!descriptor || typeof descriptor.value !== "function") continue;
      UsePermissions()(target.prototype, name, descriptor);
    }
  };
}

@FanWatchPermissions()
@Resolver()
class SafeResolver {
  @Query(() => String)
  safe(): string {
    return "ok";
  }
}

@Module({ providers: [SafeResolver] })
class FanWatchApiModule {}

export const adapter = "nestjs";
export const ApiModule = FanWatchApiModule;
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (target / "src/safe.resolver.test.ts").write_text(
                """
const methods = Object.getOwnPropertyNames(SafeResolver.prototype).filter(
  (name) => name !== "constructor",
);
expect(appliedPermissions.map((entry) => entry.key).sort()).toEqual(methods.sort());
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "resolver operation safe has no explicit per-operation @UsePermissions decorator",
                result.stderr,
            )

    def test_aliased_graphql_operation_without_permission_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            package_path = target / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["peerDependencies"]["@nestjs/graphql"] = "^13.1.0"
            package_path.write_text(json.dumps(package), encoding="utf-8")
            (target / "src/index.ts").write_text(
                """
import { Module } from "@nestjs/common";
import { Query as GqlQuery, Resolver as GqlResolver } from "@nestjs/graphql";

@GqlResolver()
class UnsafeResolver {
  @GqlQuery(() => String)
  unsafe(): string {
    return "unsafe";
  }
}

@Module({ providers: [UnsafeResolver] })
class FanWatchApiModule {}

export const adapter = "nestjs";
export const ApiModule = FanWatchApiModule;
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "resolver operation unsafe has no explicit per-operation @UsePermissions decorator",
                result.stderr,
            )

    def test_namespace_graphql_decorators_enforce_permissions_and_input_validation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            package_path = target / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["peerDependencies"].update(
                {
                    "@nestjs/graphql": "^13.1.0",
                    "@unraid/shared": "^4.25.2",
                    "class-validator": "^0.14.2",
                }
            )
            package_path.write_text(json.dumps(package), encoding="utf-8")
            (target / "src/index.ts").write_text(
                """
import { Module } from "@nestjs/common";
import * as Gql from "@nestjs/graphql";

@Gql.InputType()
class UnsafeInput {
  @Gql.Field()
  value!: string;
}

@Gql.Resolver()
class UnsafeResolver {
  @Gql.Query(() => String)
  unsafe(@Gql.Args("input") input: UnsafeInput): string {
    return input.value;
  }
}

@Module({ providers: [UnsafeResolver] })
class FanWatchApiModule {}

export const adapter = "nestjs";
export const ApiModule = FanWatchApiModule;
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "resolver operation unsafe has no explicit per-operation @UsePermissions decorator",
                result.stderr,
            )
            self.assertIn(
                "GraphQL input field UnsafeInput.value has no class-validator decorator",
                result.stderr,
            )

    def test_aliased_input_type_and_field_require_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            package_path = target / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["peerDependencies"].update(
                {
                    "@nestjs/graphql": "^13.1.0",
                    "@unraid/shared": "^4.25.2",
                    "class-validator": "^0.14.2",
                }
            )
            package_path.write_text(json.dumps(package), encoding="utf-8")
            (target / "src/index.ts").write_text(
                """
import { Module } from "@nestjs/common";
import {
  Field as GqlField,
  InputType as GqlInputType,
  Query,
  Resolver,
} from "@nestjs/graphql";
import { UsePermissions } from "@unraid/shared";

@GqlInputType()
class UnsafeInput {
  @GqlField()
  value!: string;
}

@Resolver()
class SafeResolver {
  @Query(() => String)
  @UsePermissions()
  safe(): string {
    return "ok";
  }
}

@Module({ providers: [SafeResolver] })
class FanWatchApiModule {}

export const adapter = "nestjs";
export const ApiModule = FanWatchApiModule;
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "GraphQL input field UnsafeInput.value has no class-validator decorator",
                result.stderr,
            )

    def test_namespace_graphql_decorators_with_explicit_security_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            package_path = target / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["peerDependencies"].update(
                {
                    "@nestjs/graphql": "^13.1.0",
                    "@unraid/shared": "^4.25.2",
                    "class-validator": "^0.14.2",
                }
            )
            package_path.write_text(json.dumps(package), encoding="utf-8")
            (target / "src/index.ts").write_text(
                """
import { Module } from "@nestjs/common";
import * as Gql from "@nestjs/graphql";
import * as Shared from "@unraid/shared";
import * as Validation from "class-validator";

@Gql.InputType()
class SafeInput {
  @Gql.Field()
  @Validation.IsString()
  value!: string;
}

@Gql.Resolver()
class SafeResolver {
  @Gql.Query(() => String)
  @Shared.UsePermissions()
  safe(@Gql.Args("input") input: SafeInput): string {
    return input.value;
  }
}

@Module({ providers: [SafeResolver] })
class FanWatchApiModule {}

export const adapter = "nestjs";
export const ApiModule = FanWatchApiModule;
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("passed with 0 warning(s)", result.stdout)

    def test_class_level_use_permissions_is_not_per_operation_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            package_path = target / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["peerDependencies"].update(
                {
                    "@nestjs/graphql": "^13.1.0",
                    "@unraid/shared": "^4.25.2",
                }
            )
            package_path.write_text(json.dumps(package), encoding="utf-8")
            (target / "src/index.ts").write_text(
                """
import { Module } from "@nestjs/common";
import { Query, Resolver } from "@nestjs/graphql";
import { UsePermissions } from "@unraid/shared";

@UsePermissions()
@Resolver()
class UnsafeResolver {
  @Query(() => String)
  unsafe(): string {
    return "unsafe";
  }
}

@Module({ providers: [UnsafeResolver] })
class FanWatchApiModule {}

export const adapter = "nestjs";
export const ApiModule = FanWatchApiModule;
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "resolver operation unsafe has no explicit per-operation @UsePermissions decorator",
                result.stderr,
            )

    def test_api_and_cli_module_exports_reject_non_constructor_initializers(
        self,
    ) -> None:
        invalid_cases = {
            "ApiModule object literal": ("ApiModule", "", "{}"),
            "ApiModule factory call": (
                "ApiModule",
                "function createModule(): object { return {}; }",
                "createModule()",
            ),
            "ApiModule arrow function": (
                "ApiModule",
                "",
                "() => FanWatchApiModule",
            ),
            "ApiModule non-class binding": (
                "ApiModule",
                "const fakeModule = {};",
                "fakeModule",
            ),
            "CliModule object literal": ("CliModule", "", "{}"),
        }
        for label, (export_name, prelude, initializer) in invalid_cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                target = materialize_api(Path(tmp))
                (target / "src/index.ts").write_text(
                    f"""
import {{ Module }} from "@nestjs/common";

{prelude}

@Module({{}})
class FanWatchApiModule {{}}

export const adapter = "nestjs";
export const {export_name} = {initializer};
""".strip()
                    + "\n",
                    encoding="utf-8",
                )
                result = run(
                    str(VALIDATOR),
                    str(target),
                    "--type",
                    "api",
                    cwd=target,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    f"{export_name} must be initialized with a class constructor",
                    result.stderr,
                )

    def test_imported_api_module_class_constructor_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            (target / "src/plugin.module.ts").write_text(
                """
import { Module } from "@nestjs/common";

@Module({})
export class FanWatchApiModule {}
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (target / "src/index.ts").write_text(
                """
import { FanWatchApiModule } from "./plugin.module.js";

export const adapter = "nestjs";
export const ApiModule = FanWatchApiModule;
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("passed with 0 warning(s)", result.stdout)

    def test_inline_api_module_class_expression_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            (target / "src/index.ts").write_text(
                """
export const adapter = "nestjs";
export const ApiModule = class FanWatchApiModule {};
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("passed with 0 warning(s)", result.stdout)

    def test_esm_class_and_alias_module_exports_pass(self) -> None:
        valid_entries = {
            "export class ApiModule": """
export const adapter = "nestjs";
export class ApiModule {}
""",
            "local export alias": """
export const adapter = "nestjs";
class FanWatchApiModule {}
export { FanWatchApiModule as ApiModule };
""",
            "export class CliModule": """
export const adapter = "nestjs";
export class CliModule {}
""",
        }
        for label, entry_content in valid_entries.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                target = materialize_api(Path(tmp))
                (target / "src/index.ts").write_text(
                    entry_content.strip() + "\n", encoding="utf-8"
                )
                result = run(
                    str(VALIDATOR),
                    str(target),
                    "--type",
                    "api",
                    cwd=target,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_reexported_module_class_alias_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            (target / "src/plugin.module.ts").write_text(
                "export class FanWatchApiModule {}\n", encoding="utf-8"
            )
            (target / "src/index.ts").write_text(
                """
export const adapter = "nestjs";
export { FanWatchApiModule as ApiModule } from "./plugin.module.js";
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_non_constructor_module_export_alias_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            (target / "src/index.ts").write_text(
                """
export const adapter = "nestjs";
const fakeModule = {};
export { fakeModule as ApiModule };
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "ApiModule must be initialized with a class constructor",
                result.stderr,
            )

    def test_reexported_non_constructor_module_alias_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            (target / "src/plugin.module.ts").write_text(
                "export const fakeModule = {};\n", encoding="utf-8"
            )
            (target / "src/index.ts").write_text(
                """
export const adapter = "nestjs";
export { fakeModule as ApiModule } from "./plugin.module.js";
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "ApiModule must be initialized with a class constructor",
                result.stderr,
            )

    def test_fake_class_permission_decorator_is_rejected_even_with_contract_shaped_test(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_api(Path(tmp))
            package_path = target / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["peerDependencies"].update(
                {
                    "@nestjs/graphql": "^13.1.0",
                    "@unraid/shared": "^4.25.2",
                }
            )
            package_path.write_text(json.dumps(package), encoding="utf-8")
            (target / "src/index.ts").write_text(
                """
import { Module } from "@nestjs/common";
import { Query, Resolver } from "@nestjs/graphql";
import { UsePermissions } from "@unraid/shared";

function FakePermissions(): ClassDecorator {
  return (target) => {
    void UsePermissions;
    void Object.getOwnPropertyNames(target.prototype);
    void Object.getOwnPropertyDescriptor(target.prototype, "unsafe");
  };
}

@FakePermissions()
@Resolver()
class UnsafeResolver {
  @Query(() => String)
  unsafe(): string {
    return "unsafe";
  }
}

@Module({ providers: [UnsafeResolver] })
class FanWatchApiModule {}

export const adapter = "nestjs";
export const ApiModule = FanWatchApiModule;
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (target / "src/unsafe.resolver.test.ts").write_text(
                """
const methods = Object.getOwnPropertyNames(UnsafeResolver.prototype);
expect(appliedPermissions.map((entry) => entry.key).sort()).toEqual(methods.sort());
""".strip()
                + "\n",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "api", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "resolver operation unsafe has no explicit per-operation @UsePermissions decorator",
                result.stderr,
            )

    def test_indented_txz_entities_and_archive_modes_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = materialize_os(Path(tmp))
            archive = target / "packages/fan-watch-runtime.txz"
            archive.parent.mkdir()
            content = b"#!/bin/sh\nexit 0\n"
            with tarfile.open(archive, "w:xz") as package:
                member = tarfile.TarInfo("usr/local/fan-watch/bin/helper")
                member.mode = 0o644
                member.size = len(content)
                package.addfile(member, io.BytesIO(content))
            artifact = archive.read_bytes()
            manifest = target / "runtime.plg"
            manifest.write_text(
                f"""<?xml version="1.0"?>
<!DOCTYPE PLUGIN [
  <!ENTITY name "fan-watch">
  <!ENTITY txz "&name;-runtime.txz">
  <!ENTITY md5 "{hashlib.md5(artifact).hexdigest()}">
  <!ENTITY sha256 "{hashlib.sha256(artifact).hexdigest()}">
]>
<PLUGIN name="&name;" version="0.1.0"/>
""",
                encoding="utf-8",
            )
            result = run(
                str(VALIDATOR), str(target), "--type", "os", cwd=target, check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "private runtime helper is not executable in archive", result.stderr
            )


if __name__ == "__main__":
    unittest.main()
