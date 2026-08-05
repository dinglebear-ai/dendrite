# hand-off

Load the most recent `log-code-session` artifact from the central knowledge base, with repo-local fallback, and brief the new agent on where prior coding work left off.

## What it does

1. Finds the newest `${HOMELAB_DOCS_ROOT:-$HOME/docs}/sessions/*.md`, falling back to repo-local `docs/sessions/*.md` (or uses one passed as `$ARGUMENTS`).
2. Reads the full file — Next Steps, Open Questions, Files Modified, Errors Encountered.
3. Compares the session's git/PR state to the current state and flags drift (branch mismatch, HEAD moved, PR closed, etc.).
4. Produces a short briefing so the new agent can pick up cleanly.

Pairs with `wrap-session` and `log-code-session`; those workflows write the code-session artifact and this one reads it back.

## Invoke

Triggers: "hand off", "pick up where we left off", "resume the last session", "continue from yesterday", "load the last session log".

## Files

- `SKILL.md` — agent instructions and output template
