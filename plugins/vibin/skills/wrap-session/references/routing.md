# Session routing

Classify from observed actions, not named hosts or keywords alone.

| Evidence | Route |
|---|---|
| Source, config-in-repo, tests, builds, CI, PRs, releases, packaging, code review | code |
| Live containers, system services, host files, network, DNS, storage, backups, deployments, runtime health | maintenance |
| Repository implementation plus live rollout or operational repair | both |
| Discussion, brainstorming, research with no durable implementation or operation | none |

## Important distinctions

- Reading logs from a host to debug code does not automatically make the route maintenance.
- Editing a Compose file in a repository is code or configuration work. Applying it to a live host and verifying containers is maintenance too.
- A repository-wide standards migration with no live deployment is code.
- A generated inventory refresh with no implementation change is maintenance when it records current infrastructure state.
- Mentioning NASHOST, DEVHOST, Edgehost, or another host is not enough. Classify by work performed.

## Paired artifacts

When the route is both:

- The code log owns implementation, repositories, commits, CI, tests, and code-level decisions.
- The maintenance log owns hosts, services, backups, deployment actions, runtime evidence, rollback, and operational health.
- Cross-link both with one correlation identifier.
