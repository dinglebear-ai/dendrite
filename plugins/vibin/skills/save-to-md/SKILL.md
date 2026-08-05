---
name: save-to-md
description: Deprecated compatibility alias for log-code-session. Use when an existing workflow or user still says "save-to-md" or "/save-to-md". Delegate the complete request and arguments to log-code-session, which writes the coding-session artifact without committing, pushing, merging, tracker mutation, or repository cleanup. Prefer log-code-session or wrap-session for all new workflows.
---

# save-to-md compatibility alias

This skill is retained temporarily so existing callers do not break.

1. Invoke `log-code-session` with the same arguments.
2. Do not add any legacy maintenance, commit, push, PR, merge, tracker, worktree, branch-cleanup, or HTML-rendering behavior.
3. Tell the caller that `save-to-md` is deprecated and the canonical skill is `log-code-session`.
