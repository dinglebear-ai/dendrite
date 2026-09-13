"""Shared PR-report naming, identity, state, and digest primitives."""
from __future__ import annotations

import hashlib
import re

SCHEMA_VERSION = "2"
STATES = {"PASS", "FAIL", "BLOCKED", "NOT RUN", "NOT APPLICABLE", "UNKNOWN", "STALE"}
BLOCKING_STATES = STATES - {"PASS", "NOT APPLICABLE"}
ID_PREFIXES = {
    "coverage": "REQ", "authorship": "CLM", "decisions": "DEC",
    "testing": "TEST", "evidence-manifest": "E", "risks": "RISK",
    "review-threads": "REV", "followup": "FUP", "disagreements": "DIS",
}


def slug(value: str) -> str:
    """Friendly lowercase slug. It is deliberately lossy; collision suffixes restore safety."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def repository_dir(repository: str) -> str:
    return slug(repository)


def branch_stem(branch: str) -> str:
    return slug(branch)


def artifact_id(repository: str, branch: str) -> str:
    exact = (repository + "\0" + branch).encode()
    return "pr-" + hashlib.sha256(exact).hexdigest()[:20]
