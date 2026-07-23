# Unraid API plugins (NestJS/npm)

Use this reference for packages dynamically loaded by `@unraid/api`. It is distinct from an OS `.plg`, although a product may use both.

## Contents

- [Runtime contract](#runtime-contract)
- [Prefer the live generator inside unraid-api](#prefer-the-live-generator-inside-unraid-api)
- [Package contract](#package-contract)
- [GraphQL and authorization](#graphql-and-authorization)
- [Configuration and host integration](#configuration-and-host-integration)
- [Install and lifecycle](#install-and-lifecycle)
- [Testing sequence](#testing-sequence)
- [Upstream evidence used](#upstream-evidence-used)

## Runtime contract

The API reads enabled package names from `api.plugins`, finds them among its installed dependencies/peer dependencies, dynamically imports each package, and validates its exports. A valid package must export:

```ts
export const adapter = "nestjs";
export const ApiModule = PluginModule; // or export CliModule, or both
```

`ApiModule` and `CliModule` must be class constructors. At least one is required. The bundled validator accepts `export const` initialized from a class expression or local/imported class, direct `export class ApiModule` / `CliModule`, local export aliases, and class re-export aliases from relative TypeScript modules. It rejects object literals, factory calls, arrow functions, functions, and local or re-exported non-class bindings. Use NestJS modules, dependency injection, resolvers, and services normally; use `.js` suffixes in relative TypeScript imports for ESM compatibility.

Some current hosts also consume an optional `graphqlSchemaExtension` export. Do not add it mechanically: inspect the target API's plugin interface and schema-loader behavior. When present, treat it as a second schema source that must stay exactly aligned with decorator-based resolver operations.

## Prefer the live generator inside `unraid-api`

The upstream checkout contains `packages/unraid-api-plugin-generator`, whose binary is `create-api-plugin`. At the snapshot reviewed for this skill, the package was not available from the public npm registry, so do not assume `npx @unraid/create-api-plugin` works.

When a current checkout is available:

```bash
cd <unraid-api-checkout>
pnpm --filter @unraid/create-api-plugin build
node packages/unraid-api-plugin-generator/dist/index.js <name> --dir <parent> --package-manager pnpm
```

Inspect the current generator help and output before relying on these exact commands. The bundled `assets/api-plugin/` files are a minimal fallback for environments without the checkout.

Treat generator output as a starting point, not a deployable result. The reviewed generator creates `<parent>/unraid-api-plugin-<name>` even when passed only `<name>`. The active local template now lists its imported NestJS, GraphQL, and configuration packages as peers, but it can still omit publish exports/types, license files, real tests, and target-specific permission metadata. Reconcile every imported host package against the active branch instead of preserving historical repairs mechanically. Run the bundled validator on the generated directory, repair every error, review every warning, then complete the build/pack/host sequence below.

For the fallback, copy that asset tree, rename `package.json.template`, `src/index.ts.template`, `test/plugin.spec.ts.template`, and `LICENSE-MIT.template` by removing `.template`, then replace `PLUGIN_ID` (kebab-case), `PLUGIN_PASCAL` (PascalCase), `PLUGIN_TITLE` (human-readable), `YEAR`, and `COPYRIGHT_HOLDER`. Use the MIT asset only when MIT is intended; otherwise replace it and the package identifier with another OSI-approved license. Align all dependency ranges with the target runtime before installing.

## Package contract

Use a package name such as `unraid-api-plugin-<id>` and provide:

- ESM (`"type": "module"`);
- built entry point and declarations through `main`/`types`, conditional `exports`, or both;
- `files` limited to publishable output;
- TypeScript build and test scripts;
- compatible Unraid/API version metadata if the current ecosystem consumes it;
- an OSI-approved license;
- every imported NestJS, GraphQL, configuration, validation, and Unraid runtime library as a peer dependency when the host provides it;
- ordinary direct dependencies only for libraries the plugin itself must ship, such as a protocol client not provided by the host.

Do not blindly copy version ranges from this skill. Read the target `unraid-api` package and its live generator/examples, then align exact or compatible ranges deliberately. Duplicate NestJS/GraphQL framework instances can break decorators, metadata, or dependency injection.

For CI outside an `unraid-api` checkout, install real published peer packages with `--no-save` as a best-effort typecheck proxy. Stub a private host package such as `@unraid/shared` only when it is unavailable publicly, keep that stub CI-only, and remember that this does not prove compatibility with the actual server.

For a private workspace plugin inside `unraid-api`, follow the upstream vendoring path in addition to the package contract:

1. add the workspace path to the build vendoring configuration;
2. add it to Vite workspace dependency handling;
3. add it as an optional `workspace:*` peer dependency of the API;
4. build it before the production API pack step.

Do not apply that private-workspace path to ordinary external packages.

## Minimal module

The bundled fallback exports an inert `ApiModule` with no resolver. This is intentional: a version-neutral scaffold cannot safely guess the target host's permission metadata. After inspecting the compatible host, add only the resolver/CLI surfaces the feature needs, keep GraphQL names specific to the plugin, and add `CliModule` only for actual API CLI commands.

Configuration should use `ConfigModule.forFeature`. If persistence relies on `@unraid/shared`, verify that service's current public contract and include the package in the appropriate dependency set; do not retain a generated import that the package metadata cannot satisfy.

## GraphQL and authorization

Follow the target API's resolver authorization convention. Require an explicit `UsePermissions` decorator imported from `@unraid/shared` or one of its subpaths on every `@Query`, `@Mutation`, `@Subscription`, and `@ResolveField` method. A same-named local function or import from another package is not host authorization metadata. Class-wide permission decorators are rejected even when a test appears to compare resolver methods with applied metadata: a static validator cannot prove that runtime decorator code or a contract-shaped test is genuine. The reviewed Incus example's class-wide helper must therefore be migrated to explicit method decorators before it is expected to pass this validator. Do not assume webGUI session authentication automatically grants a plugin resolver permission metadata.

The host's global validation pipe may run in whitelist mode. Put an appropriate `class-validator` decorator on every `@InputType` field, including optional fields, initialized properties with inferred types, and accessor-backed fields. A GraphQL `@Field()` decorator alone can be stripped or rejected as an unknown property. The validator recognizes direct imports, named aliases, and namespace-qualified decorators such as `@Gql.InputType()` and `@Gql.Field()`.

If the plugin exports hand-written SDL through `graphqlSchemaExtension`, add a contract test that parses it and compares every Query, Mutation, Subscription, argument, nullability, and return type against reflected resolver definitions. Avoid generic field names that can collide with core or another plugin.

Bound privileged and long-lived operations:

- validate identifiers and canonicalize paths again immediately before crossing the privilege boundary;
- apply concurrency, duration, byte, log-tail, and retained-record limits;
- run work that can outlive HTTP/proxy timeouts as a background job with status polling;
- tear down subscriptions, file watchers, timers, sockets, and sessions in module-destroy hooks;
- return specific partial failures rather than dropping failed sources silently.

## Configuration and host integration

Use the current host's config path contract. If `@unraid/shared` exposes `ConfigFilePersister` or `PATHS_CONFIG_MODULES`, derive the JSON path from it; do not hardcode a convenient development path that differs on Unraid.

For a hybrid that shares a classic `.cfg` and API JSON:

1. designate one file as the system source of truth;
2. bootstrap it before the API process constructs its config services;
3. parse it as data, update both representations atomically, and update in-memory `ConfigService` state;
4. serialize cross-process writers with a bounded lock;
5. re-arm file watchers after rename-replace writes;
6. return only derived presence flags for secrets, never the secret itself.

Prefer a direct bounded Unix-socket/API client to shelling out when the managed daemon exposes a stable local API. Keep host-level install, boot, package, and service lifecycle in the OS plugin rather than in a NestJS module.

## Install and lifecycle

On a compatible test server, inspect live help before running commands. The reviewed upstream CLI exposes:

```bash
unraid-api plugins install <package>     # aliases: i, add
unraid-api plugins list
unraid-api plugins remove <package>      # alias: rm
```

Unbundled install uses npm as an exact saved peer dependency, updates API configuration, rebuilds the vendor archive, and normally restarts the service. `--bundled` is for upstream-known workspace packages, not arbitrary third-party plugins. Safe mode skips plugin discovery.

## Testing sequence

1. Run the bundled structural validator.
2. Install dependencies with the selected package manager.
3. Type-check/build and ensure `dist/index.js` plus declarations exist.
4. Run unit tests for resolvers/services and config behavior.
5. Run resolver-authorization, input-validation, schema/SDL contract, config-concurrency, and cleanup tests when those surfaces exist.
6. Import the built package in Node and verify `adapter`, `ApiModule`/`CliModule`, optional extension exports, and absence of top-level side effects.
7. Pack it and inspect the exact publish payload for missing declarations, licenses, or accidental fixtures.
8. Run the package manager's production-dependency audit plus a full advisory review. Distinguish runtime findings from dev-tool findings; do not run a forced automatic upgrade that changes major versions without reviewing compatibility.
9. Install it through `unraid-api plugins install` on a compatible disposable server.
10. Verify list, API startup, GraphQL/CLI behavior, logs, disable/remove, restart, and recovery from an invalid plugin.

Do not treat a successful `tsc` build as proof that the host accepted the plugin schema or dependency graph.

## Upstream evidence used

- `api/docs/developer/api-plugins.md`: peer-dependency and private-workspace vendoring contract
- `packages/unraid-api-plugin-generator`: scaffold and current package conventions
- `api/src/unraid-api/plugin/plugin.interface.ts`: runtime export schema
- `api/src/unraid-api/plugin/plugin.service.ts`: discovery/import behavior
- `api/src/unraid-api/plugin/plugin-management.service.ts`: install/remove and bundled distinction
- `api/src/unraid-api/cli/plugins/plugin.command.ts`: CLI lifecycle
- `packages/unraid-api-plugin-health` and `unraid-api-plugin-connect`: minimal and production examples
- `incus-unraid/unraid-api-plugin-incus`: permissions, validation-pipe behavior, SDL/resolver contract tests, shared classic/API config, bounded Unix-socket services, and coordinated deployment
