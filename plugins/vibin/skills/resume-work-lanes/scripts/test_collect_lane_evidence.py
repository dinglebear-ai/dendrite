#!/usr/bin/env python3
"""Focused tests for the resume-work-lanes evidence collector."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from collect_lane_evidence import collect


def git(path: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class CollectLaneEvidenceTests(unittest.TestCase):
    def test_correlates_sessions_and_all_worktrees_without_leaking_secrets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            workspace = home / "workspace"
            repository = workspace / "sample"
            repository.mkdir(parents=True)
            git(repository, "init", "-b", "main")
            git(repository, "config", "user.name", "Skill Test")
            git(repository, "config", "user.email", "skill-test@example.invalid")
            (repository / "README.md").write_text("base\n", encoding="utf-8")
            git(repository, "add", "README.md")
            git(repository, "commit", "-m", "chore: initial")

            lanes = repository / ".worktrees"
            lane_one = lanes / "lane-one"
            lane_two = lanes / "lane-two"
            git(repository, "worktree", "add", "-b", "lane-one", str(lane_one))
            git(repository, "worktree", "add", "-b", "lane-two", str(lane_two))
            (lane_one / "unfinished.txt").write_text("in progress\n", encoding="utf-8")

            claude_path = (
                home / ".claude" / "projects" / "sample" / "claude-session.jsonl"
            )
            claude_path.parent.mkdir(parents=True)
            claude_events = [
                {
                    "type": "user",
                    "sessionId": "claude-lane-one",
                    "cwd": str(lane_one),
                    "timestamp": "2026-07-25T12:00:00Z",
                    "message": {
                        "role": "user",
                        "content": "Continue lane one token=do-not-leak-this-value",
                    },
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-07-25T12:01:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Task",
                                "input": {"description": "Implement lane one"},
                            }
                        ],
                    },
                },
            ]
            claude_path.write_text(
                "".join(json.dumps(event) + "\n" for event in claude_events),
                encoding="utf-8",
            )

            codex_path = (
                home / ".codex" / "sessions" / "2026" / "07" / "codex-session.jsonl"
            )
            codex_path.parent.mkdir(parents=True)
            codex_events = [
                {
                    "type": "session_meta",
                    "timestamp": "2026-07-25T13:00:00Z",
                    "payload": {"id": "codex-main", "cwd": str(repository)},
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-07-25T13:01:00Z",
                    "payload": {
                        "type": "function_call",
                        "name": "functions.update_plan",
                        "arguments": {
                            "plan": [
                                {"step": f"Inspect {lane_two}", "status": "pending"}
                            ]
                        },
                    },
                },
            ]
            codex_path.write_text(
                "".join(json.dumps(event) + "\n" for event in codex_events),
                encoding="utf-8",
            )

            artifact = collect(
                workspace, since_hours=24, transcript_limit=10, home=home
            )
            rendered = json.dumps(artifact)

            self.assertEqual(len(artifact["sessions"]), 2)
            self.assertEqual(len(artifact["repositories"]), 1)
            self.assertEqual(artifact["repositories"][0]["root"], str(repository))
            self.assertNotIn("do-not-leak-this-value", rendered)

            lanes_by_path = {
                lane["worktree"]["path"]: lane
                for lane in artifact["correlated_lanes"]
                if lane["worktree"]
            }
            self.assertIn(str(repository), lanes_by_path)
            self.assertIn(str(lane_one), lanes_by_path)
            self.assertIn(str(lane_two), lanes_by_path)
            self.assertIn("dirty_worktree", lanes_by_path[str(lane_one)]["signals"])
            self.assertEqual(
                lanes_by_path[str(lane_one)]["session_refs"][0]["match_reason"],
                "cwd",
            )
            self.assertEqual(
                lanes_by_path[str(lane_two)]["session_refs"][0]["match_reason"],
                "transcript",
            )


if __name__ == "__main__":
    unittest.main()
