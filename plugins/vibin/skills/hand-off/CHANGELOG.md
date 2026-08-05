# Changelog

All notable changes to the `hand-off` skill are recorded here. Format roughly follows [Keep a Changelog](https://keepachangelog.com/).

## Unreleased
- Load the newest code-session artifact from `${HOMELAB_DOCS_ROOT:-$HOME/docs}/sessions` before falling back to repo-local history.
- Replace `save-to-md` terminology with `log-code-session` and `wrap-session`.
- Keep drift detection against the current branch, HEAD, worktree, PR, and dirty state.

## [0.1.1] - 2026-05-17
- Fixed the `Latest session files` glob to fall back to `pwd` when not in a git repo (was silently looking at `/docs/sessions/*.md`, absolute root).
- Documented that `$ARGUMENTS` can be used to load an older session log instead of the most recent.
- Added README.

## [0.1.0] - Initial
- Initial skill version.
