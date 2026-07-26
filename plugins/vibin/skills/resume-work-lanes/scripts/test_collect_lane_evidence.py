#!/usr/bin/env python3
"""Focused tests for the resume-work-lanes evidence collector."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from collect_lane_evidence import (
    collect,
    cortex_shape_error,
    transcript_paths,
    write_private_output,
)


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
            git(
                repository,
                "commit",
                "-m",
                "chore: initial token=commit-secret-value",
            )
            git(
                repository,
                "remote",
                "add",
                "origin",
                "https://user:remote-credential@github.com/example/sample.git",
            )

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

            with patch.dict(
                os.environ,
                {
                    "CLAUDE_CONFIG_DIR": str(home / ".claude"),
                    "CODEX_HOME": str(home / ".codex"),
                },
            ):
                artifact = collect(
                    workspace,
                    since_hours=24,
                    transcript_limit=10,
                    home=home,
                    cortex_binary=str(root / "missing-cortex"),
                )
            rendered = json.dumps(artifact)

            self.assertEqual(artifact["source_used"], "raw_files_fallback")
            self.assertEqual(len(artifact["sessions"]), 2)
            self.assertEqual(len(artifact["repositories"]), 1)
            self.assertEqual(artifact["repositories"][0]["root"], str(repository))
            self.assertNotIn("do-not-leak-this-value", rendered)
            self.assertNotIn("commit-secret-value", rendered)

            snapshots_by_path = {
                lane["worktree"]["path"]: lane
                for lane in artifact["correlated_lanes"]
                if lane["kind"] == "worktree_snapshot" and lane["worktree"]
            }
            self.assertIn(str(repository), snapshots_by_path)
            self.assertIn(str(lane_one), snapshots_by_path)
            self.assertIn(str(lane_two), snapshots_by_path)
            self.assertIn("dirty_worktree", snapshots_by_path[str(lane_one)]["signals"])
            session_lanes = {
                lane["session_refs"][0]["session_id"]: lane
                for lane in artifact["correlated_lanes"]
                if lane["kind"] == "session_candidate"
            }
            self.assertEqual(
                session_lanes["claude-lane-one"]["session_refs"][0]["match_reason"],
                "cwd",
            )
            self.assertEqual(
                session_lanes["claude-lane-one"]["worktree"]["path"], str(lane_one)
            )
            self.assertEqual(
                session_lanes["codex-main"]["mentioned_worktree_dependencies"],
                [{"path": str(lane_two), "relationship": "mentioned_not_owned"}],
            )

    def test_uses_cortex_as_primary_source_when_its_index_is_healthy(self) -> None:
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
            git(
                repository,
                "remote",
                "add",
                "origin",
                "https://user:remote-credential@github.com/example/sample.git",
            )
            lane = repository / ".worktrees" / "cortex-lane"
            git(repository, "worktree", "add", "-b", "cortex-lane", str(lane))

            transcript = home / ".codex" / "sessions" / "cortex-session.jsonl"
            transcript.parent.mkdir(parents=True)
            transcript.write_text("{}\n", encoding="utf-8")
            (transcript.parent / "inventory-only.jsonl").write_text(
                "{}\n", encoding="utf-8"
            )
            fake_cortex = root / "cortex"
            fake_cortex.write_text(
                f"""#!/usr/bin/env python3
import json
import sys

command = sys.argv[2]
project = {str(lane)!r}
transcript = {str(transcript)!r}
if command == "watchstatus":
    result = {{"health": {{"schema_current": True, "stale_indicators": [], "last_successful_ingest_at": "2099-01-01T00:00:00Z"}}}}
elif command == "projects":
    result = {{"projects": [{{"project": project, "tools": ["codex"], "session_count": 1, "event_count": 12, "first_seen": "2099-01-01T12:00:00Z", "last_seen": "2099-01-01T13:00:00Z"}}]}}
elif command == "blocks":
    result = {{"blocks": [{{"project": project, "tool": "codex", "session_count": 1, "event_count": 12, "bucket_start": "2099-01-01T12:00:00Z", "bucket_end": "2099-01-01T13:00:00Z"}}]}}
elif command == "errors":
    result = []
elif command == "search":
    query = sys.argv[3]
    sessions = []
    if "update_plan" in query:
        sessions = [{{"project": project, "tool": "codex", "session_id": "cortex-session", "first_seen": "2099-01-01T12:00:00Z", "last_seen": "2099-01-01T13:00:00Z", "best_snippet": "Plan token=private-cortex-value still has one pending step"}}]
    result = {{"sessions": sessions}}
elif command == "context":
    result = {{"sessions": ["cortex-session", "inventory-only"], "recent_entries_truncated": True, "recent_entries": [{{"timestamp": "2099-01-01T13:00:00Z", "ai_tool": "codex", "ai_session_id": "cortex-session", "ai_transcript_path": transcript, "message": "Continue password=private-context-value"}}]}}
else:
    raise SystemExit(2)
print(json.dumps(result))
""",
                encoding="utf-8",
            )
            fake_cortex.chmod(0o755)

            isolated_environment = {
                "CLAUDE_CONFIG_DIR": str(home / ".claude"),
                "CODEX_HOME": str(home / ".codex"),
            }
            with patch.dict(os.environ, isolated_environment):
                artifact = collect(
                    workspace,
                    since_hours=24,
                    transcript_limit=10,
                    home=home,
                    cortex_binary=str(fake_cortex),
                )

            self.assertEqual(artifact["source_used"], "cortex")
            self.assertTrue(artifact["cortex"]["usable"])
            self.assertEqual(len(artifact["sessions"]), 2)
            sessions = {
                session["session_id"]: session for session in artifact["sessions"]
            }
            self.assertEqual(sessions["cortex-session"]["evidence_source"], "cortex")
            self.assertEqual(sessions["cortex-session"]["path"], str(transcript))
            self.assertEqual(sessions["cortex-session"]["cortex_queries"], ["plans"])
            self.assertEqual(sessions["cortex-session"]["plan_events"], [])
            self.assertEqual(
                artifact["cortex"]["contexts"][str(lane)]["time_bounded_session_ids"],
                ["cortex-session", "inventory-only"],
            )
            self.assertTrue(sessions["inventory-only"]["inventory_only"])
            self.assertEqual(
                artifact["cortex"]["coverage"][
                    "session_ids_without_time_bounded_evidence"
                ],
                0,
            )
            rendered = json.dumps(artifact)
            self.assertNotIn("private-cortex-value", rendered)
            self.assertNotIn("private-context-value", rendered)
            self.assertNotIn("remote-credential", rendered)
            self.assertEqual(
                artifact["cortex"]["coverage"][
                    "contexts_with_truncated_recent_entries"
                ],
                [str(lane)],
            )
            matched = [
                recovery_lane
                for recovery_lane in artifact["correlated_lanes"]
                if recovery_lane["kind"] == "session_candidate"
                and recovery_lane["session_refs"][0]["session_id"] == "cortex-session"
                and recovery_lane["worktree"]
                and recovery_lane["worktree"]["path"] == str(lane)
            ]
            self.assertEqual(len(matched), 1)
            self.assertEqual(matched[0]["session_refs"][0]["match_reason"], "cwd")

            degraded_script = fake_cortex.read_text(encoding="utf-8").replace(
                '"schema_current": True', '"schema_current": False'
            )
            fake_cortex.write_text(degraded_script, encoding="utf-8")
            with patch.dict(os.environ, isolated_environment):
                degraded = collect(
                    workspace,
                    since_hours=24,
                    transcript_limit=10,
                    home=home,
                    cortex_binary=str(fake_cortex),
                )
            self.assertEqual(
                degraded["source_used"], "cortex_degraded_with_raw_fallback"
            )
            self.assertFalse(degraded["cortex"]["usable"])
            self.assertIn(
                "Cortex transcript schema is not confirmed current",
                degraded["cortex"]["stale_reasons"],
            )

    def test_private_output_is_exclusive_and_mode_0600(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "lane-evidence.json"
            write_private_output(output, '{"ok": true}')
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                write_private_output(output, '{"ok": false}')

            raced_output = Path(temporary) / "raced.json"
            real_link = os.link

            def competing_link(source: str, destination: str) -> None:
                Path(destination).write_text("competitor\n", encoding="utf-8")
                real_link(source, destination)

            with (
                patch("collect_lane_evidence.os.link", side_effect=competing_link),
                self.assertRaises(FileExistsError),
            ):
                write_private_output(raced_output, '{"ok": true}')
            self.assertEqual(raced_output.read_text(encoding="utf-8"), "competitor\n")

    def test_private_output_works_when_posix_fchmod_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "windows-compatible.json"
            with patch.object(os, "fchmod", new=None, create=True):
                write_private_output(output, '{"ok": true}')
            self.assertEqual(output.read_text(encoding="utf-8"), '{"ok": true}\n')

    def test_rejects_successful_but_malformed_cortex_shapes(self) -> None:
        self.assertIsNotNone(cortex_shape_error("watchstatus", {}))
        self.assertIsNotNone(cortex_shape_error("projects", {}))
        self.assertIsNotNone(cortex_shape_error("projects", {"projects": [42]}))
        self.assertIsNotNone(cortex_shape_error("blocks", {"blocks": {}}))
        self.assertIsNotNone(cortex_shape_error("blocks", {"blocks": [42]}))
        self.assertIsNotNone(cortex_shape_error("session_errors", {}))
        self.assertIsNotNone(cortex_shape_error("session_errors", [{}]))
        self.assertIsNotNone(cortex_shape_error("search:plans", {"sessions": {}}))
        self.assertIsNotNone(cortex_shape_error("search:plans", {"sessions": [42]}))
        self.assertIsNotNone(
            cortex_shape_error(
                "context:/workspace",
                {"sessions": [], "recent_entries": {}},
            )
        )
        self.assertIsNotNone(
            cortex_shape_error(
                "context:/workspace",
                {"sessions": [42], "recent_entries": [42]},
            )
        )
        self.assertIsNotNone(
            cortex_shape_error(
                "context:/workspace",
                {"sessions": ["session"], "recent_entries": [{}]},
            )
        )

    def test_raw_discovery_reports_per_tool_truncation_and_custom_homes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            claude_home = root / "custom-claude"
            codex_home = root / "custom-codex"
            (claude_home / "projects").mkdir(parents=True)
            (codex_home / "sessions").mkdir(parents=True)
            for index in range(2):
                (claude_home / "projects" / f"claude-{index}.jsonl").write_text(
                    "{}\n", encoding="utf-8"
                )
                (codex_home / "sessions" / f"codex-{index}.jsonl").write_text(
                    "{}\n", encoding="utf-8"
                )
            with patch.dict(
                os.environ,
                {
                    "CLAUDE_CONFIG_DIR": str(claude_home),
                    "CODEX_HOME": str(codex_home),
                },
            ):
                selected, coverage = transcript_paths(root, cutoff=0, limit=1)
            self.assertEqual(len(selected), 2)
            self.assertTrue(coverage["truncated"])
            self.assertEqual(coverage["omitted"], 2)
            self.assertEqual(coverage["per_tool"]["claude"]["selected"], 1)
            self.assertEqual(coverage["per_tool"]["codex"]["selected"], 1)

    def test_deadline_truncated_transcript_discovery_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, coverage = transcript_paths(
                root,
                cutoff=0,
                limit=10,
                deadline=time.monotonic() - 1,
            )
            self.assertTrue(coverage["deadline_truncated"])
            self.assertTrue(coverage["truncated"])

            with patch(
                "collect_lane_evidence.transcript_paths",
                return_value=([], coverage),
            ):
                artifact = collect(
                    root,
                    since_hours=24,
                    transcript_limit=10,
                    home=root,
                    source="files",
                )
            self.assertEqual(
                artifact["coverage"]["session_inventory_status"], "incomplete"
            )
            self.assertIn(
                "raw transcript discovery hit the deadline",
                artifact["coverage"]["session_limitations"],
            )

    def test_git_only_does_not_scan_transcript_trees(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch(
                "collect_lane_evidence.transcript_paths",
                side_effect=AssertionError("git-only must not scan transcripts"),
            ):
                artifact = collect(
                    root,
                    since_hours=24,
                    transcript_limit=10,
                    home=root,
                    source="git-only",
                )
            self.assertEqual(artifact["source_used"], "git_only")
            self.assertEqual(artifact["sessions"], [])
            self.assertTrue(
                artifact["cortex"] is None
                and artifact["coverage"]["session_inventory_status"]
                == "external_required"
            )

    def test_disappearing_transcript_is_reported_without_sort_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "vanished-session.jsonl"
            coverage = {
                "limit_per_tool": 10,
                "per_tool": {
                    "claude": {
                        "discovered": 0,
                        "selected": 0,
                        "omitted": 0,
                        "truncated": False,
                    },
                    "codex": {
                        "discovered": 1,
                        "selected": 1,
                        "omitted": 0,
                        "truncated": False,
                    },
                },
                "discovered": 1,
                "selected": 1,
                "omitted": 0,
                "truncated": False,
            }
            with patch(
                "collect_lane_evidence.transcript_paths",
                return_value=([(missing, "codex")], coverage),
            ):
                artifact = collect(
                    root,
                    since_hours=24,
                    transcript_limit=10,
                    home=root,
                    source="files",
                )
            self.assertEqual(
                artifact["coverage"]["session_inventory_status"], "incomplete"
            )
            self.assertIn(
                "one or more transcript files disappeared or could not be read",
                artifact["coverage"]["session_limitations"],
            )
            self.assertTrue(artifact["sessions"][0]["read_error"])
            self.assertTrue(artifact["errors"])
            self.assertEqual(
                artifact["correlated_lanes"][0]["session_refs"][0]["modified_at"],
                None,
            )

    def test_explicit_cortex_failure_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = Path(__file__).with_name("collect_lane_evidence.py")
            completed = subprocess.run(
                [
                    "python3",
                    str(script),
                    "--workspace",
                    str(root),
                    "--source",
                    "cortex",
                    "--cortex-binary",
                    str(root / "missing-cortex"),
                    "--overall-timeout",
                    "5",
                    "--stdout",
                    "--compact",
                ],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(completed.returncode, 3)
            self.assertEqual(
                json.loads(completed.stdout)["source_used"], "cortex_unavailable"
            )


if __name__ == "__main__":
    unittest.main()
