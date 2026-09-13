---
name: homelab-map
description: Load or refresh the authoritative personal homelab context layer whenever a prompt concerns named hosts, service placement, topology, storage, networking, proxies, MCP services, backups, or current infrastructure drift. Use for NASHOST, DEVHOST, Edgehost, Backuphost, Winhost, Laptophost, HomeLAN, "where does this service run", "map the homelab", "refresh inventory", or "check declared versus observed state". Prefer version-controlled configuration for desired state, the ~/docs generators for observed domain inventories, and ~/.homelab for the compiled overview.
allowed-tools: Read, Bash
---

# Homelab Map

Use the homelab knowledge system as a layered context source, not a static list copied into this skill.

## Stable host roles

- **NASHOST**: primary Unraid storage and application host; also owns the DEVHOST VM.
- **DEVHOST**: development, AI, MCP, indexing, and automation hub.
- **Edgehost**: edge and utility services, including SWAG and authentication-adjacent services.
- **Backuphost**: backup and replication target.
- **Winhost / winhost-wsl**: Windows and WSL GPU workstation surfaces.
- **Laptophost / laptophost-wsl**: mobile development workstation surfaces.

Treat exact versions, counts, IPs, ports, health, and service placement as point-in-time facts that require current evidence.

## Source precedence

Use the source that owns the question:

1. **Desired state**: version-controlled Compose, SWAG, and non-secret configuration in the homelab repository.
2. **Observed state**: generated domain inventories under `~/docs/generated/`.
3. **Compiled overview**: `~/.homelab/homelab.md`, `homelab.json`, and `context-sources.json`.
4. **Rationale and history**: ADRs, standards, service docs, reports, plans, maintenance logs, and code-session logs under `~/docs`.
5. **Live verification**: direct read-only query when the decision depends on current runtime health and the generated snapshot is stale.

A historical log never overrides current desired or observed state. A running container does not prove that its configuration is version-controlled.

## Refresh

Run the context refresh when current infrastructure facts matter:

```bash
python3 <skill-dir>/scripts/refresh-context.py
```

The refresh process:

1. runs the existing specialized `~/docs/scripts` collectors in dependency order;
2. regenerates the compiled `~/.homelab` map using the existing live collector;
3. writes `~/.homelab/context-sources.json` with source paths, freshness, checksums, collector results, and Git state for the declared homelab repository.

Use `--skip-collect` to compile from existing docs snapshots, `--skip-live-map` to refresh only specialized inventories and the source manifest, and `--strict` when any failed collector must fail the whole run.

## Existing specialized inventories

Prefer the narrowest generated source:

- containers and Compose projects: `generated/homelab/docker.*`
- SWAG routes and upstreams: `generated/homelab/proxies.*`
- hosts and devices: `generated/homelab/devices.*`
- health: `generated/homelab/health.*`
- Unraid and storage: `generated/homelab/unraid.*`
- UniFi and Tailscale: `generated/net/unifi.*`, `generated/net/tailscale.*`
- MCP gateway and servers: `generated/mcp/`
- repository fleet: `generated/dev/` and workspace inventory pages

Read JSON sidecars for machine reasoning and Markdown for human context.

## Drift reasoning

When asked about drift, compare declared and observed state explicitly:

- declared Compose service missing at runtime;
- running container absent from version-controlled Compose;
- proxy config targeting a missing or moved upstream;
- service documentation naming the wrong host;
- generated snapshot older than the freshness required by the task;
- standard claiming enforcement that repository measurement disproves;
- maintenance or session record describing work that was never reflected in desired state.

Report the two conflicting sources, their observation times, and which source owns the intended truth. Do not silently edit either side.

## Operating rules

- `*.nashost.tv` identifies a SWAG route, not necessarily a service running on NASHOST.
- Use host names exactly as configured.
- Public SSH is not assumed; prefer the configured Tailscale and LABBY paths.
- Do not expose secrets from generated JSON, environment files, or live commands.
- Refresh before relying on volatile counts or health claims.
