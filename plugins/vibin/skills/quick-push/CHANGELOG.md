# Changelog

All notable changes to the `quick-push` skill are recorded here. Format roughly follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]
- Removed automatic session logging and cross-repository knowledge-base staging.
- Defined `quick-push` as a repository publishing workflow only.
- Route final session capture through `wrap-session` after commit, push, PR, CI, and verification state are known.
- Preserve repo-root staging, version synchronization, changelog handling, and safe dirty-set review.

## [0.1.1] - 2026-05-17
- Concretized step 2.7 version-sync verification: replaced hand-wavy "search for stale old-version references" with a concrete `git grep -F "<old_version>"` command across common manifest/doc extensions.
- Clarified step 3 / step 4 sequencing used by this historical version.
- Added README.

## [0.1.0] - Initial
- Initial skill version.
