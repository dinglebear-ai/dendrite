# Hybrid Unraid OS and API plugins

Use this reference when one product contains both a classic `.plg` and an `unraid-api-plugin-*` package. The classic layer is not merely an installer wrapper: it owns privileged host lifecycle and must coordinate compatibility and rollback with the API layer.

## Ownership boundary

| Concern | OS `.plg` layer | API package |
|---|---|---|
| Privileged package/runtime installation | Owns | Must not own |
| Boot, array/Docker events, host daemon | Owns | Observes/manages only through supported APIs |
| Durable flash config and secrets | Owns physical lifecycle and migrations | May expose validated API views/updates through host config services |
| NestJS DI, GraphQL, subscriptions, CLI modules | Must not reimplement | Owns |
| Settings/dashboard frontend assets | Normally packages and restores them | Supplies API contract consumed by the frontend |
| Compatibility, activation, rollback, removal | Coordinates both artifacts | Must be independently importable/testable |

Write this ownership table for the specific project before implementing. Choose one configuration source of truth and one component responsible for schema migrations.

## Coordinated release pipeline

1. Build, typecheck, and test the API package.
2. Build every settings/dashboard frontend bundle.
3. Stage `dist/`, package metadata, lockfile, and only locked production dependencies the host does not provide. Dereference build-cache symlinks; never package machine-local absolute links.
4. Place the staged API payload and frontend assets into the exact classic archive version being released.
5. Diff the staged `dist/` and frontend output against fresh source builds in CI.
6. Record the classic package hash plus API version, supported Node major, architecture, minimum libc, and schema compatibility in release metadata.
7. Retain one known-good classic archive and API directory until live verification succeeds.

Do not release the frontend, classic runtime, and GraphQL schema from independent moving references. A coordinated archive prevents the web UI from asking an older backend for fields it does not expose.

## Transactional activation

On install or upgrade:

1. Verify the downloaded classic package with SHA-256 before `upgradepkg` or extraction.
2. Preserve the previous classic package path.
3. Bootstrap/migrate persistent config before starting the API; constructor-time path selection can otherwise bind the process to a development fallback for its lifetime.
4. Copy the API payload to a unique staging directory beside the live target.
5. Back up the current API package and every host loader/config file that will change.
6. Stop the API service before editing both its package manifest and enabled-plugin list.
7. Update JSON with `jq` into a same-directory temporary file, preserve mode/ownership, and rename atomically. Add/remove only this plugin and preserve all other keys/plugins.
8. Atomically move the staged package into place, restart the API, and verify a plugin-specific readiness marker, schema field, or new log segment within a bounded timeout.
9. If verification fails, stop the API, restore the prior package and loader/config files, restart, then roll the classic package back as well. A fresh install with no prior version should remove the unpaired classic package.

Never declare success merely because the API process stayed running; verify that this plugin actually initialized. Decide explicitly whether an absent `unraid-api` runtime yields a supported classic-only mode or a failed install, and report that state clearly.

## Removal

Stop the host service first. Disable/unregister the API package while the API is stopped, remove only this plugin's target and rollback directories, restart the API, then remove the classic runtime/web tree. Preserve durable user config and large runtime state by default, and tell the operator exactly what remains and how to purge it.

Unregistration must handle both a plain package name and any version-suffixed entry without removing another plugin. Test registration twice and removal twice to prove idempotence.

## Compatibility and failure tests

Automate these contracts:

- classic archive contains the exact API `dist/`, metadata, production dependencies, and frontend bundles;
- package/source inventory and checksums match release metadata;
- every required runtime/helper executable has the intended archive mode, survives clean extraction as executable, and passes a bounded non-destructive smoke invocation under the installed environment;
- fresh install creates config before API activation;
- registration preserves unrelated package/config keys and does not duplicate the plugin;
- failed API activation restores API files, loader state, and classic package together;
- uninstall removes only this API plugin and leaves user state intact;
- safe/classic-only mode behaves as documented when the API runtime is absent;
- a disposable Unraid host passes install, reboot, update, deliberate bad-plugin rollback, disable/remove, and reinstall tests.

Run the bundled validator at the hybrid repository root; it auto-detects the classic payload plus immediate child API package, or accept `--type hybrid` explicitly. An empty classic payload is an error, not a successful headless plugin.

## Evidence used

- `incus-unraid/incus.plg`
- `incus-unraid/scripts/build-classic-package.sh`
- `incus-unraid/scripts/verify-classic-package.sh`
- `incus-unraid/source/.../install-api-plugin.sh`
- `incus-unraid/source/.../api-plugin-registration.sh`
- `incus-unraid/tests/classic-contract.sh`
