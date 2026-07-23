# Unraid OS and webGUI plugins (`.plg`)

Use this reference for plugins installed by Unraid's plugin manager. It reconciles the upstream `unraid-api/plugin` builder with `incus-unraid`, `unraid-mcp`, and `unraid/ci-runner-farm`. Re-check a current first-party plugin before relying on exact manifest or webGUI details.

## Contents

- [Runtime model](#runtime-model)
- [Choose a package shape](#choose-a-package-shape)
- [Manifest and packaging](#manifest-and-packaging)
- [Containerized local build loop](#containerized-local-build-loop)
- [Configuration and upgrades](#configuration-and-upgrades)
- [Services and event hooks](#services-and-event-hooks)
- [WebGUI pages](#webgui-pages)
- [PHP/bash boundary](#phpbash-boundary)
- [Bundled runtimes and destructive paths](#bundled-runtimes-and-destructive-paths)
- [Private shared-library runtimes](#private-shared-library-runtimes)
- [Release automation](#release-automation)
- [Testing sequence](#testing-sequence)
- [Upstream evidence used](#upstream-evidence-used)

## Runtime model

An OS plugin combines:

1. a `.plg` XML manifest that Unraid runs during install and boot; and
2. a package, normally a plugin-directory `.tgz` or root-relative Slackware `.txz`, containing webGUI pages, scripts, private runtimes, or other payloads.

The important storage split is:

| Path | Backing | Use |
|---|---|---|
| `/usr/local/emhttp/plugins/<id>/` | tmpfs | Installed code, `.page` files, PHP, scripts, static assets |
| `/var/local/emhttp/<id>/` | tmpfs | Frequently changing runtime state, locks, caches, status |
| `/boot/config/plugins/<id>/` | USB flash | Durable configuration, secrets, cached install package, migrations/known-good config |
| `/mnt/<pool>/<id>/` or appdata | array/pool storage | Large durable runtime state, language overlays, databases, container data |

Code under `/usr/local/emhttp` disappears at reboot and is restored by the `.plg`. Avoid frequent writes to `/boot`: PID files, locks, status caches, polling results, build logs, and health samples belong on tmpfs. Put large persistent runtime state on an explicitly validated array/pool path.

## Choose a package shape

Use the smallest artifact that matches the payload:

| Shape | Use when | Key rule |
|---|---|---|
| Plugin-directory `.tgz` | The payload lives entirely under `/usr/local/emhttp/plugins/<id>/` | Extract only with `-C` into that plugin directory plus `--no-overwrite-dir`; never install it at `/` |
| Slackware `.txz` | The plugin ships a private runtime or files outside the webGUI tree | Stage a full root-relative tree and install with `upgradepkg`; record architecture and libc/runtime compatibility |
| Carry-forward binary `.txz` | A large historical runtime cannot yet be rebuilt from immutable upstream inputs | Extract the prior complete archive, overlay tracked source, and enforce inventory/source-drift/shrinkage checks; call it verifiable, not reproducible |

A typical small repository is:

```text
<id>/
├── build-plg.sh
├── VERSION
├── LICENSE
├── .gitignore
└── src/usr/local/emhttp/plugins/<id>/
    ├── <PagePrefix>.page
    └── include/
        ├── exec.php       # only for live actions
        └── <id>.sh        # only for live actions
```

Use the assets bundled with this skill:

- `assets/build-plg.sh.template`: reproducible `.tgz` plus generated `.plg`
- `assets/LICENSE-MIT.template`: optional root license when MIT is intended
- `assets/page.template`: single-page or xmenu/tabbed webGUI layouts
- `assets/exec.php.template`: CSRF-guarded JSON shim
- `assets/control.sh.template`: action-dispatched bash backend

Replace every placeholder, remove unused sections, and preserve executable bits on shell scripts.
The page asset uses deliberately specific sentinels—`PLUGIN_ID`, `PagePrefix`,
`PLUGIN_TITLE`, `MENU_LABEL`, `ICON_NAME`, `PLUGIN_PAGE_TAG`, and
`PLUGIN_NAMESPACE`—so ordinary page content such as `TITLE`, `MENU`, `ICON`,
or `TAG` is not mistaken for unfinished scaffolding.

## Manifest and packaging

Use a `<PLUGIN>` root with explicit name, author, sortable version, update URL, minimum Unraid version, support destination, and plugin-manager icon. Put the intended OSI-approved license at the repository root. For a webGUI plugin, require a real package `<FILE>` with a `.tgz` or `.txz` name/URL; an empty `<PLUGIN/>` is not a valid release manifest. Keep `pluginURL` on the latest `.plg` release asset so update checks can find it, but pin package URLs to the exact release tag and versioned filename so an old manifest can never fetch new bytes.

The loader's `<MD5>` field is a compatibility requirement, not a modern security boundary. Compute it for Unraid, then verify SHA-256 in the install script before privileged extraction or `upgradepkg`.

The install path must:

- create only the plugin's own config and runtime directories;
- extract package contents only into the plugin directory;
- use `--no-same-owner`, then force `root:root` ownership;
- set directories `0755`, ordinary files `0644`, and executables `0755`;
- preserve user configuration and secrets;
- avoid blocking boot;
- tolerate repeated execution on every boot.

CDATA does not expand XML entities. Inject literal build-time values or use literal paths inside install/remove script CDATA.

Build the `.tgz` reproducibly: stable path order, fixed timestamps, numeric root ownership, and gzip without timestamps. The release artifact must match the integrity value embedded in the `.plg`. Commit policy is project-specific; if CI rebuilds `.tgz`, prove it is byte-identical before publication.

For binary-heavy `.txz` packages, maintain a machine-readable release manifest with package name, SHA-256, architecture, minimum libc, Node/runtime major, and schema compatibility as applicable. Verify required files, archive ownership, embedded manifest, source/archive equality, and unexpected entry-count shrinkage.

## Containerized local build loop

Prefer a maintained containerized builder when the plugin matches, or can deliberately adapt, its source and artifact layout. The current first-party `unraid-api/plugin` harness uses Docker for package assembly, exposes an HTTP server on port 5858, and prints the local installation URL. It does not fully isolate the toolchain: `predocker:build-and-run` builds UI, web, and API release inputs on the host before the container starts, so the host Node version, native modules, environment, and generated-output ownership remain part of the build contract.

In a current `unraid-api` checkout, the reviewed loop is:

```bash
cd <unraid-api-checkout>/plugin
test -f .env || pnpm run env:init
pnpm run env:validate
pnpm run docker:build-and-run
```

Inspect the live `package.json`, `docker-compose.yml`, and printed output before relying on copied commands. In the reviewed version, `docker:run` executes `pnpm build` inside the container and leaves an interactive shell; older documentation also tells the operator to run `pnpm build` after entering the container. Use the URL printed by the builder. In the reviewed live harness the printed root path `/dynamix.unraid.net.plg` worked while the older documented `/plugins/local/dynamix.unraid.net.plg` returned 404.

Before rerunning a bind-mounted builder, inspect ownership of generated outputs. A root-running container can leave directories such as `unraid-ui/dist-wc`, `web/dist`, `api/deploy/release`, or staged plugin output root-owned; the next host-side Vite/build step then fails with `EACCES` before Docker starts. Stop the builder, resolve the exact generated paths, confirm they contain no user-authored files, and restore ownership or remove/rebuild only those outputs. Do not recursively `chown` the repository or hide this failure with a privileged host build.

For the bundled small-plugin asset, run `assets/build-plg.sh.template` after copying and replacing every placeholder. A normal build must emit the `.plg`, a stable unversioned `.tgz` used for reproducibility checks, and the exact versioned `.tgz` named by the manifest's `packageName` entity. Treat a missing versioned artifact, a checksum mismatch, or a URL filename that differs from the emitted file as a release blocker.

Open Plugins on a disposable Unraid development host and install that served URL. The container validates the build environment, packaging code, archive assembly, manifest generation, and local HTTP handoff; it is not an Unraid emulator and cannot prove plugin-manager behavior, dynamix rendering, boot restoration, host ABI compatibility, event hooks, or daemon lifecycle. Keep those assertions behind real-host tests and inspect the Unraid system log on failure.

For an independent plugin, copy concepts rather than blindly copying the first-party tree: pin the builder image/toolchain, mount only required source/build outputs, keep secrets out of the context, build artifacts deterministically, publish the served URL explicitly, and add package/manifest tests that also run non-interactively in CI.

Do not infer reproducibility from a green container build. Build the same commit at least twice with identical declared inputs and compare hashes plus archive listings. The reviewed first-party harness produced different `.txz` hashes across unchanged builds because the generated `vendor_archive.json` entered the tar with a changing mtime; normalize generated-file metadata or otherwise make the archive deterministic before claiming reproducibility.

## Configuration and upgrades

Choose one source of truth for each setting. Two proven models are:

- keep defaults in code and persist only user overrides, minimizing flash writes and migration burden; or
- seed a complete config once, preserve it forever, and apply explicit idempotent migrations.

Never overwrite user configuration on install or upgrade. Preserve config and secrets by default on uninstall, state that behavior in the removal message, and require an explicit purge path for deletion.

Store secrets separately from ordinary `.cfg` values, create them once, restrict the directory and file before content lands, and return only `*_configured` presence flags to routine UI reads. On Unraid's FAT-backed flash, `chmod` is defense in depth; the mount umask is the actual enforcement boundary.

Prefer parsing web-written config as data with an exhaustive key allowlist. If a root-owned config is sourced by lifecycle scripts, its only writers must serialize literal values safely, reject newlines/unknown keys, write atomically, and validate before promotion. Keep a known-good copy when applying settings can break service startup. Use bounded locks and temp-file-plus-rename for concurrent writers; put locks on tmpfs.

Migrations must be versioned, idempotent, and narrow. Patch only recognized old defaults; never rewrite customized files silently. If a custom value cannot be migrated safely, surface a manual action.

## Services and event hooks

For a host daemon, install an Unraid-style `/etc/rc.d/rc.<id>` symlink on every boot. Its `start`, `stop`, `restart`, and `status` paths should:

- detect idempotent already-running/stopped states;
- verify a PID's `/proc/<pid>/cmdline` before signaling it;
- run preflight checks and wait for a real readiness condition;
- roll back partial startup resources after a timeout;
- attempt graceful shutdown before bounded TERM/KILL escalation;
- rotate bounded logs and expose a useful health/status file;
- scope private `PATH`/`LD_LIBRARY_PATH` changes to the service process.

Run ostensibly non-interactive third-party CLIs with stdin redirected from `/dev/null` and a bounded timeout; some commands otherwise wait forever instead of failing. Preflight every helper binary needed for readiness, shutdown, networking, and archive/image handling.

Pick event hooks from the dependency boundary, not by habit:

- use `event/disks_mounted` and `event/unmounting_disks` when state lives on the array;
- use `event/docker_started` and `event/stopping_docker` when the plugin manages Docker resources.

Event hooks must be executable, idempotent, bounded, and safe when dependencies are absent. Retry readiness a finite number of times. Stop stateful services before their backing storage unmounts. Detach long readiness waits and background reconciliation so emhttp/plugin installation is not blocked. An install on an already-running system should start the enabled service immediately rather than waiting for reboot.

## WebGUI pages

A `.page` file has INI-style metadata, `---`, then PHP/HTML. Use a single page unless multiple tabs materially improve the experience. For tabs, use an xmenu container with `Type="xmenu"` and `Tabs="true"`, then children with `Menu="<PagePrefix>:N"`.

Use native dynamix behavior:

- `parse_plugin_cfg('<id>')` to read settings;
- `/update.php` and hidden `#file` for ordinary settings;
- `$var['csrf_token']` for live POSTs;
- `autov()` for cache-busted assets;
- existing jQuery/sweetalert/ACE/filetree libraries instead of bundling duplicates;
- dynamix CSS variables instead of hard-coded theme colors.

For a substantial UI, keep the `.page` file as a thin shell around a Vue/custom-element bundle. Build every emitted file into the OS payload—including hashed lazy chunks—and verify source-build versus staged-bundle equality in CI. Use an ES module for the settings application and a separate tiny bundle for any Main/Dashboard widget; the dashboard loads for every user and should not pull the entire settings application.

Cache-bust stable asset names with `autov()` or an mtime query. Use host theme variables across all Unraid themes. A dashboard page may use `Cond=` for enablement and `Nchan=` plus a publisher under `nchan/` for subscriber-driven status updates instead of permanent browser polling.

All xmenu tabs share one document. Define shared JavaScript/CSS once with `include_once`, make tab dependencies explicit, and stop background polling when the relevant tab is not visible. Fetch clients must reject non-2xx responses and distinguish “unavailable” from a valid empty/zero state.

## PHP/bash boundary

Use a PHP endpoint only when the page performs live actions or needs controlled config writes. Keep it thin:

1. return JSON for every path;
2. rely on the webGUI's global POST CSRF gate when confirmed for that route, or compare the current token with `hash_equals` locally;
3. allowlist actions and identifier shapes;
4. pass every shell argument through `escapeshellarg`;
5. dispatch to one control script;
6. use exit codes for success;
7. create secret/config temp files under `umask 0077`, then atomically rename;
8. clamp numeric values server-side and treat HTML constraints as presentation only;
9. keep stderr out of machine-readable JSON and redact secret-shaped log values.

Keep business logic in the control script. Provide human output for SSH and JSON variants for the UI. Serialize mutating actions with `flock`; advisory locks are released by the kernel after crashes and are safer than sentinel files. Long jobs should run detached, write bounded progress to tmpfs, and expose a polling verb instead of holding a PHP/browser request open.

## Bundled runtimes and destructive paths

If the host lacks the required language/runtime, stage a private relocatable runtime under `/usr/local/<id>/`, smoke-import the installed application with that runtime during packaging, and avoid modifying the host's global loader or login environment. Remove build-only tooling from the shipped runtime when practical. Record architecture/libc compatibility and keep any persistent update overlay on an array/pool path, not RAM or flash. A self-updater must stop the service before replacement, accept only validated release versions, pin its package index/source, verify the installed version, and refuse silent downgrades; provide an explicit reset to the bundled version.

### Private shared-library runtimes

For a binary-heavy runtime such as Incus, stage non-host libraries and their complete SONAME/symlink chains under `/usr/local/<id>/lib`. Source one environment wrapper from the service launcher and export `LD_LIBRARY_PATH=/usr/local/<id>/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}` only into the managed process tree. Put matching private executables and helpers first on `PATH`. Do not add the private directory to `/etc/ld.so.conf*`, run a global `ldconfig` registration, or export it from a login/global environment.

Treat every global-path exception as an explicit, reviewed contract. Incus keeps most libraries private but installs `liblxcfs.so` at `/usr/lib/x86_64-linux-gnu/lxcfs/liblxcfs.so` because lxcfs requires that module at its host loader path. Record exceptions in the package manifest, verify their ownership and removal behavior, and ensure they cannot replace unrelated host libraries.

Preflight the installed tree, not only the build host:

```bash
LD_LIBRARY_PATH=/usr/local/<id>/lib \
  ldd /usr/local/<id>/libexec/<id>/<daemon>
readelf -d /usr/local/<id>/libexec/<id>/<daemon>
```

Fail on unresolved dependencies and inspect `NEEDED`, `RPATH`, and `RUNPATH`. Check each required SONAME first in the private directory and then in the host loader paths; record which side supplies it. Repeat `ldd` and an actual smoke invocation for every dynamically linked helper that the daemon shells out to, not just the daemon itself.

A scoped loader can still create a mixed-toolchain ABI failure: any host executable launched inside that process tree also sees the private libraries first. Incus exposed this when debootstrap fell back to the host `zstdcat`, which then loaded the older bundled `libzstd.so.1` and failed on the missing `POOL_create` symbol. Bundle matching helper binaries and symlinks from the same locked package set as their `.so` files, or prove the host helper is ABI-compatible under the scoped environment. Include this transitive-helper check in preflight and live image/archive tests.

Presence is not enough for helpers such as `distrobuilder`, `debootstrap`, `ar`, `mksquashfs`, `zstd`, and `zstdcat`. Assert mode `0755` (or another deliberate executable mode) in the staged tree and archive listing, extract into a clean directory, assert `test -x`, then run a bounded `--help`, `--version`, or non-destructive smoke command under the exact private `PATH`/`LD_LIBRARY_PATH`. A package contract that checks filenames and `ldd` but not executable mode can pass while the installed workflow fails with permission denied.

Before `rm -rf`, recursive `chown`, bind mounts, or storage creation:

1. canonicalize the configured root (`realpath -m` or equivalent);
2. require a dedicated child directory beneath an allowed storage prefix;
3. reject `/`, system directories, `/boot`, `/mnt/user`, and bare pool/disk roots;
4. verify every derived child remains beneath that canonical root;
5. delete only named plugin-owned children, using non-empty shell guards such as `${root:?}/${child:?}`.

Never pass a secret in argv when `/proc/<pid>/cmdline` can expose it. Prefer stdin/config files or short-lived scoped credentials. Do not put secrets into container build contexts.

## Release automation

Keep internal SemVer separate from the plugin-manager's sortable external version when necessary. A proven external form is `YYYY.MM.DD.HHMM.BUILD-SEMVER`. Validate that the release tag, SemVer source, manifest entities, package filename, and checksum all agree.

Release automation should rebuild from the tag, compare package bytes/content with what the committed `.plg` advertises, then upload both manifest and exact version-pinned package assets. When using release-please, regenerate the `.plg` on its release branch rather than hand-editing versions. Pin CI actions and use least-privilege workflow permissions.

Use the four-stage workflow split observed in `unraid/ci-runner-farm`, adapted and hardened for the plugin:

| Workflow | Purpose | Required gates |
|---|---|---|
| Fast lint | Cheap PR feedback | NUL-safe iteration over tracked shell/PHP files, syntax/static analysis, and config/default/UI parity tests |
| Package build | Prove source-to-artifact assembly | Build from checkout, parse XML, verify MD5 and SHA-256, require the exact manifest-named package, compare extracted payload with source, inspect ownership/modes, rebuild for determinism, and upload the `.plg` plus package as CI artifacts |
| Release preparation | Keep release metadata derived | On the release PR, derive `VERSION` and manifest entities from the release version, regenerate only expected release files, fail on unexpected dirt, and commit through a narrowly scoped bot identity |
| Tag validation and publication | Prove the released bytes | Reusable `workflow_call` validation of tag ↔ internal version ↔ external plugin version ↔ `VERSION` ↔ manifest entities; checkout the tag, rebuild there, compare advertised hashes/content, then upload the `.plg` and exact version-pinned `packageName` asset |

The useful source files are `.github/workflows/lint.yml`, `package-plugins.yml`, `release-please.yml`, and `release.yml`. They demonstrate fast PR linting, a separately inspectable package job, release-PR metadata regeneration, reusable tag validation, and publication of the exact manifest-named asset. Copy the separation of responsibilities and the tag/manifest checks, not the YAML verbatim.

The reviewed workflows also contain gaps that this skill intentionally hardens: their lint loops split `git ls-files` output on whitespace, package comparisons use a shared fixed `/tmp` path, package/release checks verify only MD5, and the release-please workflow grants broad write permissions, permits a privileged bot-token fallback, and cancels superseded runs even though later jobs mutate a release. Replace those patterns with the safeguards below rather than describing them as upstream-proven behavior.

For every workflow:

- pin third-party actions to commit SHAs;
- default to `contents: read`, disable persisted checkout credentials in non-publishing jobs, and grant write scopes only to the job that creates release metadata or uploads assets;
- use concurrency groups and cancel superseded pull-request runs, but do not cancel an in-progress publication after external mutation begins;
- use `git ls-files -z` plus NUL-safe loops instead of whitespace-splitting command substitution;
- use `mktemp -d` and a trap for extracted-package comparisons rather than a shared fixed `/tmp` directory;
- treat an administrative bot token as an explicit branch-protection exception, not the default credential;
- keep CI artifacts and release assets distinct: CI may retain convenient stable names, while publication must upload the exact filename encoded in the tagged manifest.

## Testing sequence

1. Validate names and unresolved placeholders.
2. Run the bundled structural validator.
3. Run shell syntax checks and PHP lint when present.
4. Build twice from identical source and compare package hashes.
5. Parse the generated `.plg` and verify package integrity.
6. Resolve the manifest's `packageName`, require an emitted artifact with that exact basename, and verify both MD5 and SHA-256 against it.
7. Diff the built archive against staged source; inspect paths, root ownership, required inventory, and executable modes.
8. Run UI typecheck/tests/build and verify every emitted asset is staged.
9. Install on a disposable compatible Unraid system.
10. Test fresh install, already-running install, reboot restoration, array/Docker restart, update, failed-update rollback, removal, and configuration preservation.

Do not claim runtime success before step 9.

## Upstream evidence used

- `unraid-api/plugin/README.md`: Docker builder, local serving, install loop, environment validation
- `unraid-api/plugin/plugins/dynamix.unraid.net.plg`: first-party manifest/install/remove implementation
- `unraid-api/plugin/builder/`: packaging and manifest validation code
- `incus-unraid`: hybrid lifecycle, coordinated rollback, binary-package provenance, source/archive contract tests, service/event hardening
- `unraid-mcp/unraid-plugin`: private runtime packaging, settings custom element, write-only secrets, dashboard/Nchan split, array lifecycle
- `unraid/ci-runner-farm`: split lint/package/release workflows, reusable tag validation, release-PR metadata regeneration, exact tag-pinned publication, reproducible packaging, delta config, Docker lifecycle, PHP/bash boundary, safe destructive paths, CA handoff
