# log-code-session

Creates a curated, append-only record of a coding session. It captures repository state, implementation work, decisions, changed files, tests, CI, errors, verification, risks, and follow-ups.

The skill writes one Markdown artifact and stops. It does not commit, push, merge, mutate trackers, move plans, or clean branches and worktrees.

Use `wrap-session` when the session may include both coding and live homelab maintenance.
