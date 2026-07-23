---
name: create-unraid-plugin
description: >-
  Create, scaffold, develop, test, and package every supported Unraid plugin architecture: (1)
  an Unraid OS/webGUI plugin distributed as a .plg with dynamix .page UI,
  PHP/bash backend, flash-safe persistence, and reproducible packaging; or (2)
  an Unraid API plugin distributed as a NestJS/npm peer-dependency package
  exporting adapter and ApiModule/CliModule; or (3) a coordinated hybrid with
  classic host lifecycle plus API/GraphQL functionality. Use when a user asks
  to create, scaffold, develop, review, audit, explain, migrate, package, test,
  repair, or troubleshoot an Unraid plugin implementation; build a .plg; add
  an Unraid Settings page or host service; create an Unraid API plugin; extend
  @unraid/api; inspect an existing plugin's architecture or build workflow; or
  coordinate a hybrid plugin. Do not use for Community Applications metadata,
  listing, moderation, or submission alone; use submit-unraid-community-app
  after the plugin itself works.
---

# Create an Unraid Plugin

Create the correct plugin architecture, prove it locally, and distinguish static validation from real Unraid runtime evidence.

## Choose the plugin type first

Determine the type from the requested integration surface. If ambiguous, ask one concise question before writing files.

| Type | Choose when | Runtime and artifact |
|---|---|---|
| **Unraid OS plugin** | Add or modify webGUI pages, settings, host services, event hooks, boot behavior, packages, or system integration | Unraid plugin manager installs a `.plg`; code is extracted into `/usr/local/emhttp/plugins/<id>/` and persistent state lives under `/boot/config/plugins/<id>/` |
| **Unraid API plugin** | Add NestJS modules, GraphQL resolvers, CLI modules, or services loaded by `@unraid/api` | npm-compatible ESM package, normally named `unraid-api-plugin-<id>`, installed and enabled as an Unraid API peer dependency |

Some products need both: use an OS `.plg` as the installation/lifecycle shell and an API plugin package for NestJS/GraphQL functionality. Keep their artifacts, version compatibility, tests, and removal behavior independently verifiable.

## Load only the relevant reference

- For `.plg`, dynamix/webGUI, PHP/bash, event-hook, or host-service work, read [references/os-plugin.md](references/os-plugin.md).
- For NestJS, GraphQL, npm peer-dependency, `ApiModule`, or `CliModule` work, read [references/api-plugin.md](references/api-plugin.md).
- For a hybrid, read both plus [references/hybrid-plugin.md](references/hybrid-plugin.md), then design ownership and rollback before scaffolding.

Treat the live target repository and installed Unraid/API version as authoritative. The bundled references are portable snapshots of the upstream `unraid-api` documentation, builder, generator, schemas, and worked examples; re-check upstream when versions or contracts may have changed.

## Common workflow

1. **Inspect before scaffolding.** Resolve the target directory, existing files, requested capabilities, supported Unraid versions, author, license, release destination, and whether a related plugin already exists. Preserve unrelated dirt. Never overwrite an existing plugin directory without confirmation.
2. **Define the boundary.** State which type is being built, what it owns, what it must not own, its readiness/event dependency, and any hybrid handoff. Do not put host lifecycle logic into an API package merely because it can run Node, and do not reimplement GraphQL module loading in PHP/bash.
3. **Use the maintained scaffold when available.** For API plugins inside a current `unraid-api` checkout, prefer its local `packages/unraid-api-plugin-generator`; it is not assumed to be published on npm. For OS plugins, adapt the bundled minimal assets or a current first-party `.plg` builder after reviewing it.
4. **Create the smallest complete skeleton.** Include build metadata, types/exports, a real entry point, tests, license, and only the UI/backend/config pieces the feature requires. Choose plugin-directory `.tgz`, root-relative `.txz`, or hybrid coordinated packaging deliberately. Do not add optional daemons, secrets, settings pages, or persistence preemptively.
5. **Implement security at every boundary.** Validate names before building paths; treat config and requests as untrusted; allowlist actions and identifiers; avoid shell interpolation; never log or commit secrets; and use least privilege.
6. **Validate the structure.** Run:

   ```bash
   python3 <skill-dir>/scripts/validate_unraid_plugin.py <target>
   ```

   Pass `--type os`, `--type api`, or `--type hybrid` only when auto-detection is ambiguous. Hybrid validation checks the classic root and each immediate child `unraid-api-plugin-*` package together. Fix errors and review warnings.
7. **Build and test with the plugin's real toolchain.** For OS plugins, parse/build the `.plg`, verify package integrity/reproducibility, and use a maintained containerized builder when the target layout supports it; then install/update/remove on a disposable Unraid system. A Docker build proves packaging and can serve the local manifest, but it does not emulate Unraid. For API plugins, install dependencies, type-check/build, run behavior tests, then install with the actual `unraid-api plugins` CLI on a compatible test server.
8. **Report evidence precisely.** List created files, plugin type, commands run, supported versions, validation/build/test results, runtime tests actually performed, and remaining release or deployment work. Never turn a successful static build into a claim that Unraid loaded the plugin.

## Evidence levels

Keep these claims separate in implementation notes and the final report:

| Evidence | What it proves | What it does not prove |
|---|---|---|
| Local validator, lint, unit tests, archive inspection, repeated-build hashes | Source structure, syntax, selected behavior, and package determinism | Plugin-manager execution, webGUI behavior, host ABI, boot/events, service lifecycle |
| Containerized plugin builder plus served manifest URL | Declared host/container build path, archive/manifest assembly, and local HTTP handoff | Full toolchain isolation or that Unraid can install, render, start, update, or remove the plugin |
| Disposable compatible Unraid host | Actual `.plg` install/update/remove, dynamix UI, event/boot behavior, host paths, permissions, ABI, and service readiness | Compatibility with Unraid/API versions or architectures not tested |
| Compatible `unraid-api` host | Dynamic import, dependency graph, schema/CLI registration, permissions, restart, disable/remove | Classic OS lifecycle unless the hybrid `.plg` is tested too |

## Hybrid plugin rules

Use the OS `.plg` to install/remove persistent system integration and to place or enable the API package. Use the API package to export NestJS modules and API/GraphQL/CLI functionality. Specify:

- which artifact owns version compatibility;
- how the `.plg` obtains an exact API-package version;
- how install, boot, upgrade, rollback, disable, and remove behave;
- whether API restart is required after enable/disable;
- how a partial failure is surfaced and recovered;
- which configuration is shared and which layer owns its schema.

Do not silently vendor a workspace API package into an unrelated external plugin. Upstream `unraid-api` has a special bundled-workspace vendoring path; third-party packages normally follow the runtime npm install path and must be explicitly listed in API configuration.

## Guardrails

- Keep OS plugin runtime churn off USB flash; reserve `/boot/config/plugins/<id>/` for durable configuration, secrets, and cached install artifacts.
- Keep secrets out of ordinary `.cfg`, web pages, `.plg` XML, npm metadata, argv, logs, build contexts, and committed fixtures; prefer dedicated restricted files and presence flags.
- Require CSRF protection and strict command/input validation for web-callable OS-plugin backends.
- Require `adapter = "nestjs"` plus at least one exported `ApiModule` or `CliModule` for API plugins.
- Use ESM-compatible `.js` import specifiers in API-plugin TypeScript.
- Keep shared NestJS/GraphQL runtime libraries as compatible peer dependencies to avoid duplicate framework instances.
- Require explicit per-operation current-host permission metadata imported from `@unraid/shared` on API resolvers and `class-validator` coverage on every GraphQL input field when the target API uses whitelist validation; do not accept same-named local functions or class-wide decorators as static proof.
- Do not guess API or Unraid compatibility ranges. Derive them from the target runtime and current upstream package versions.
- Do not run public submission, npm publication, GitHub release creation, server installation, or other external writes without authorization.
- Hand a working OS `.plg` to `submit-unraid-community-app` for CA metadata and portal submission; creation and submission are separate gates.
