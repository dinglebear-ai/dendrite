#!/usr/bin/env python3
"""Plans a five-model LM Studio bake-off without loading or unloading models.

The plan command is deliberately read-only: it invokes only ``lms ls --json``,
requires the five reviewed local aliases to resolve to their exact selected
variants, and emits backend-native load profiles for the lifecycle helper.
It does not rank models or claim that a plan is benchmark evidence.
"""

import argparse
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


class BakeoffError(RuntimeError):
    """A fail-closed inventory or command contract violation."""


CONTEXT_LENGTH = 32_768
MAX_PACKET_INPUT_TOKENS = 20_480
MAX_PACKET_OUTPUT_TOKENS = 8_192
CONTEXT_RUNTIME_RESERVE_TOKENS = 4_096
if (
    MAX_PACKET_INPUT_TOKENS
    + MAX_PACKET_OUTPUT_TOKENS
    + CONTEXT_RUNTIME_RESERVE_TOKENS
    != CONTEXT_LENGTH
):
    raise RuntimeError("the fixed packet envelope must exactly fit the served context")
MODEL_SPECS = (
    {
        "model_key": "qwen/qwen3.6-35b-a3b",
        "selected_variant": "qwen/qwen3.6-35b-a3b@4bit",
        "format": "safetensors",
        "quantization": "4bit",
        "quantization_bits": 4,
        "path": "qwen/qwen3.6-35b-a3b",
        "indexed_model_identifier": "qwen/qwen3.6-35b-a3b",
        "backend": "MLX",
        "artifact_size_bytes": 20_429_364_306,
        "max_context_length": 262_144,
    },
    {
        "model_key": "meta/muse-glimmer",
        "selected_variant": "meta/muse-glimmer@q4_k_m",
        "format": "gguf",
        "quantization": "Q4_K_M",
        "quantization_bits": 4,
        "path": "meta/muse-glimmer",
        "indexed_model_identifier": "meta/muse-glimmer",
        "backend": "GGUF",
        "artifact_size_bytes": 18_157_122_004,
        "max_context_length": 131_072,
    },
    {
        "model_key": "google/gemma-4-31b",
        "selected_variant": "google/gemma-4-31b@4bit",
        "format": "safetensors",
        "quantization": "4bit",
        "quantization_bits": 4,
        "path": "google/gemma-4-31b",
        "indexed_model_identifier": "google/gemma-4-31b",
        "backend": "MLX",
        "artifact_size_bytes": 18_444_515_810,
        "max_context_length": 262_144,
    },
    {
        "model_key": "google/gemma-4-26b-a4b-qat",
        "selected_variant": "google/gemma-4-26b-a4b-qat@4bit",
        "format": "safetensors",
        "quantization": "4bit",
        "quantization_bits": 4,
        "path": "google/gemma-4-26b-a4b-qat",
        "indexed_model_identifier": "google/gemma-4-26b-a4b-qat",
        "backend": "MLX",
        "artifact_size_bytes": 15_641_333_028,
        "max_context_length": 262_144,
    },
    {
        "model_key": "qwen/qwen3.8-27b",
        "selected_variant": "qwen/qwen3.8-27b@q4_k_m",
        "format": "gguf",
        "quantization": "Q4_K_M",
        "quantization_bits": 4,
        "path": "qwen/qwen3.8-27b",
        "indexed_model_identifier": "qwen/qwen3.8-27b",
        "backend": "GGUF",
        "artifact_size_bytes": 17_742_040_464,
        "max_context_length": 262_144,
    },
)


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise BakeoffError("inventory JSON contains a duplicate key")
        value[key] = item
    return value


def _minimal_environment():
    allowed = ("HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TMP", "TEMP")
    return {key: os.environ[key] for key in allowed if key in os.environ}


def _read_inventory(lms_cli):
    path = Path(lms_cli).expanduser().resolve()
    try:
        mode = path.stat().st_mode
    except OSError as error:
        raise BakeoffError("lms CLI is unavailable") from error
    if not stat.S_ISREG(mode) or not os.access(path, os.X_OK):
        raise BakeoffError("lms CLI must be an executable regular file")
    try:
        completed = subprocess.run(
            [str(path), "ls", "--json"],
            check=False,
            capture_output=True,
            env=_minimal_environment(),
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BakeoffError("read-only model inventory failed") from error
    if completed.returncode != 0:
        raise BakeoffError("read-only model inventory exited non-zero")
    if len(completed.stdout) > 8 * 1024 * 1024:
        raise BakeoffError("read-only model inventory is unexpectedly large")
    try:
        rows = json.loads(
            completed.stdout.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BakeoffError("read-only model inventory is not strict JSON") from error
    if not isinstance(rows, list):
        raise BakeoffError("read-only model inventory must be an array")
    return rows


def _load_profiles(backend):
    if backend == "GGUF":
        base = {
            "contextLength": CONTEXT_LENGTH,
            "flashAttention": True,
            "gpu": {"ratio": "max"},
            "llamaKCacheQuantizationType": False,
            "llamaVCacheQuantizationType": False,
            "maxParallelPredictions": 1,
            "speculativeDraftMtp": False,
            "speculativeDraftSimple": False,
            "useFp16ForKVCache": True,
        }
        q8 = dict(base)
        q8["llamaKCacheQuantizationType"] = "q8_0"
        q8["llamaVCacheQuantizationType"] = "q8_0"
        return {
            "f16": {"load_config": base},
            "q8_0": {"load_config": q8},
        }
    if backend == "MLX":
        return {"mlx-native": {"load_config": {
            "contextLength": CONTEXT_LENGTH,
            "maxParallelPredictions": 1,
            "mlxDiskCache": False,
            "mlxKvCacheQuantization": False,
        }}}
    raise BakeoffError("unsupported backend profile")


def _validate_model_row(row, spec):
    if not isinstance(row, dict):
        raise BakeoffError("candidate inventory row must be an object")
    if row.get("type") != "llm" or row.get("deviceIdentifier") is not None:
        raise BakeoffError("candidate must be a local-only LLM")
    if row.get("selectedVariant") != spec["selected_variant"]:
        raise BakeoffError(
            "candidate selected variant does not match the reviewed exact variant"
        )
    variants = row.get("variants")
    if not isinstance(variants, list) or variants.count(spec["selected_variant"]) != 1:
        raise BakeoffError("candidate selected variant is missing or ambiguous")
    quantization = row.get("quantization")
    if (
        row.get("format") != spec["format"]
        or not isinstance(quantization, dict)
        or quantization.get("name") != spec["quantization"]
        or quantization.get("bits") != spec["quantization_bits"]
        or row.get("path") != spec["path"]
        or row.get("indexedModelIdentifier")
        != spec["indexed_model_identifier"]
    ):
        raise BakeoffError("candidate format or quantization changed")
    for field in ("path", "indexedModelIdentifier"):
        if not isinstance(row.get(field), str) or not row[field]:
            raise BakeoffError("candidate artifact identity is incomplete")
    for field in ("sizeBytes", "maxContextLength"):
        if not isinstance(row.get(field), int) or isinstance(row[field], bool) or row[field] <= 0:
            raise BakeoffError("candidate artifact size or context is invalid")
    if row["sizeBytes"] != spec["artifact_size_bytes"]:
        raise BakeoffError("candidate artifact size differs from the reviewed exact variant")
    if row["maxContextLength"] != spec["max_context_length"]:
        raise BakeoffError(
            "candidate native context differs from the reviewed exact variant"
        )
    if row["maxContextLength"] < CONTEXT_LENGTH:
        raise BakeoffError("candidate cannot support the bake-off context length")


def build_plan(rows):
    models = []
    for spec in MODEL_SPECS:
        matches = [row for row in rows if isinstance(row, dict) and row.get("modelKey") == spec["model_key"]]
        if len(matches) != 1:
            raise BakeoffError("candidate model key is missing or ambiguous")
        row = matches[0]
        _validate_model_row(row, spec)
        models.append({
            "model_key": spec["model_key"],
            "selected_variant": spec["selected_variant"],
            "backend": spec["backend"],
            "format": spec["format"],
            "quantization": spec["quantization"],
            "size_bytes": row["sizeBytes"],
            "max_context_length": row["maxContextLength"],
            "indexed_model_identifier": row["indexedModelIdentifier"],
            "profiles": _load_profiles(spec["backend"]),
        })
    return {
        "schema_version": 1,
        "mode": "read-only-plan",
        "mutation_performed": False,
        "ranking_claimed": False,
        "context_length": CONTEXT_LENGTH,
        "packet_envelope": {
            "max_input_tokens": MAX_PACKET_INPUT_TOKENS,
            "max_output_tokens": MAX_PACKET_OUTPUT_TOKENS,
            "runtime_reserve_tokens": CONTEXT_RUNTIME_RESERVE_TOKENS,
        },
        "lifecycle_boundary": (
            "SDK 1.5.0 exposes no abort signal for unload. A deadline must retain "
            "the recovery journal and prohibit a subsequent load until exact stable "
            "state is established."
        ),
        "load_capacity_policy": (
            "The exact reviewed artifact size, profile-specific KV-cache projection, "
            "and 4 GiB runtime reserve must fit reclaimable physical/Metal memory. "
            "Swap is only a separate 2 GiB safety floor and is never counted as load "
            "capacity."
        ),
        "artifact_fingerprint_scope": (
            "Pre/post lifecycle fingerprints bind normalized SDK downloaded-model "
            "identity metadata, including exact selected variant, path, size, format, "
            "quantization, and context. They are not model-file content hashes."
        ),
        "models": models,
        "boundary": (
            "This inventory plan performs no model lifecycle operation or inference; "
            "it is not comparative quality evidence."
        ),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="emit a zero-mutation inventory plan")
    plan.add_argument(
        "--lms-cli",
        default=str(Path.home() / ".lmstudio" / "bin" / "lms"),
    )
    plan.add_argument("--json", action="store_true", help="emit strict JSON")
    return parser.parse_args(argv)


def main(argv=None):
    try:
        args = parse_args(argv)
        if args.command != "plan":
            raise BakeoffError("unsupported command")
        plan = build_plan(_read_inventory(args.lms_cli))
        if not args.json:
            raise BakeoffError("plan currently requires --json")
        print(json.dumps(plan, sort_keys=True, separators=(",", ":")))
        return 0
    except BakeoffError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
