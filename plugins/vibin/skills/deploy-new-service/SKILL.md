---
name: deploy-new-service
description: Orchestrate a new homelab service from declared configuration through live verification. Use when the user says "deploy a new service", "add this app to the homelab", "create the compose stack", "put this behind SWAG", or requests a complete service rollout. Create version-controlled Compose and documentation, invoke create-swag-config when needed, validate desired state, deploy to the selected host, verify runtime health, update inventory, and finish with wrap-session. Never place real secrets in Git and never overwrite or remove an existing deployment without explicit authorization.
allowed-tools: Read, Write, Edit, Bash
---

# Deploy New Service

Build the service as one independent Compose project inside the homelab source-of-truth repository, then deploy it to the selected host.

## Phases

1. **Discover**: identify service, target host, ports, storage, networks, authentication, public exposure, health checks, backup needs, and upstream documentation.
2. **Pattern match**: inspect neighboring services on the target host and the homelab standards. Do not invent paths, networks, or IPs.
3. **Declare**: create the Compose file, `.env.example`, service README, non-secret config, inventory entry, and rollback notes.
4. **Proxy**: when public or routed access is required, invoke `create-swag-config`. Keep SWAG config with the SWAG deployment's tracked configuration.
5. **Validate**: run Compose parsing, secret scanning, path checks, external-network checks, image or config validation, and nginx validation when applicable.
6. **Safety**: confirm persistent-data paths, backup or snapshot requirements, collision-free ports, and rollback steps before live changes.
7. **Deploy**: apply only the selected service. Do not restart unrelated stacks.
8. **Verify**: check container health, logs, network reachability, application behavior, proxy response, authentication, and persistence.
9. **Record**: refresh inventory and invoke `wrap-session`; a normal rollout should produce both a code-session log and a maintenance log.

## Guardrails

- Real credentials remain in the approved secret store or host-local env file.
- Do not commit appdata, databases, certificates, backups, logs, or runtime state.
- Do not expose a service publicly by default.
- Do not treat a running container as sufficient verification.
- Stop and report when upstream requirements conflict with host standards or available resources.
