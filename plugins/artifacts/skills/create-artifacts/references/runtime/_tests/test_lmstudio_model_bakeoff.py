"""Behavior tests for the fail-closed LM Studio model bake-off lifecycle."""

import json
import hashlib
import os
import stat
import subprocess
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BAKEOFF = ROOT / "scripts" / "lmstudio-model-bakeoff.py"
LIFECYCLE = ROOT / "scripts" / "lmstudio-model-lifecycle.cjs"
NODE_BINARY = subprocess.check_output(
    ["node", "-p", "process.execPath"], text=True
).strip()

MODEL_ROWS = [
    {
        "type": "llm",
        "modelKey": "qwen/qwen3.6-35b-a3b",
        "format": "safetensors",
        "path": "qwen/qwen3.6-35b-a3b",
        "sizeBytes": 20_429_364_306,
        "indexedModelIdentifier": "qwen/qwen3.6-35b-a3b",
        "deviceIdentifier": None,
        "quantization": {"name": "4bit", "bits": 4},
        "variants": ["qwen/qwen3.6-35b-a3b@4bit"],
        "selectedVariant": "qwen/qwen3.6-35b-a3b@4bit",
        "maxContextLength": 262_144,
    },
    {
        "type": "llm",
        "modelKey": "meta/muse-glimmer",
        "format": "gguf",
        "path": "meta/muse-glimmer",
        "sizeBytes": 18_157_122_004,
        "indexedModelIdentifier": "meta/muse-glimmer",
        "deviceIdentifier": None,
        "quantization": {"name": "Q4_K_M", "bits": 4},
        "variants": ["meta/muse-glimmer@q4_k_m"],
        "selectedVariant": "meta/muse-glimmer@q4_k_m",
        "maxContextLength": 131_072,
    },
    {
        "type": "llm",
        "modelKey": "google/gemma-4-31b",
        "format": "safetensors",
        "path": "google/gemma-4-31b",
        "sizeBytes": 18_444_515_810,
        "indexedModelIdentifier": "google/gemma-4-31b",
        "deviceIdentifier": None,
        "quantization": {"name": "4bit", "bits": 4},
        "variants": ["google/gemma-4-31b@4bit"],
        "selectedVariant": "google/gemma-4-31b@4bit",
        "maxContextLength": 262_144,
    },
    {
        "type": "llm",
        "modelKey": "google/gemma-4-26b-a4b-qat",
        "format": "safetensors",
        "path": "google/gemma-4-26b-a4b-qat",
        "sizeBytes": 15_641_333_028,
        "indexedModelIdentifier": "google/gemma-4-26b-a4b-qat",
        "deviceIdentifier": None,
        "quantization": {"name": "4bit", "bits": 4},
        "variants": ["google/gemma-4-26b-a4b-qat@4bit"],
        "selectedVariant": "google/gemma-4-26b-a4b-qat@4bit",
        "maxContextLength": 262_144,
    },
    {
        "type": "llm",
        "modelKey": "qwen/qwen3.8-27b",
        "format": "gguf",
        "path": "qwen/qwen3.8-27b",
        "sizeBytes": 17_742_040_464,
        "indexedModelIdentifier": "qwen/qwen3.8-27b",
        "deviceIdentifier": None,
        "quantization": {"name": "Q4_K_M", "bits": 4},
        "variants": ["qwen/qwen3.8-27b@q4_k_m"],
        "selectedVariant": "qwen/qwen3.8-27b@q4_k_m",
        "maxContextLength": 262_144,
    },
]


def run_node(source, *args, timeout=20):
    environment = os.environ.copy()
    if args:
        environment["HOME"] = str(args[0])
    return subprocess.run(
        [NODE_BINARY, "-e", source, str(LIFECYCLE), *map(str, args)],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )


FAKE_TRANSACTION_RUNNER = r"""
const fs = require("node:fs");
const crypto = require("node:crypto");
const lifecycle = require(process.argv[1]);
const work = process.argv[2];
const scenario = process.argv[3];
let journalPath = `${work}/.lmstudio-model-lifecycle-recovery.json`;
let lockPath = `${work}/.lmstudio-model-lifecycle.lock`;
if (scenario === "alternate-lock-path") lockPath = `${work}/alternate.lock`;
if (scenario === "symlink-parent") {
  fs.mkdirSync(`${work}/actual-state`);
  fs.symlinkSync(`${work}/actual-state`, `${work}/linked-state`);
  journalPath = `${work}/linked-state/recovery.json`;
  lockPath = `${work}/linked-state/transaction.lock`;
}
const rows = JSON.parse(fs.readFileSync(`${work}/rows.json`, "utf8"));
const trace = [];
const fullTrace = [];
const originalUnlinkSync = fs.unlinkSync;
const originalFsyncSync = fs.fsyncSync;
let failedMutationBoundarySync = false;
if (scenario === "mutation-boundary-directory-fsync-failure") {
  fs.fsyncSync = descriptor => {
    const statValue = fs.fstatSync(descriptor);
    if (statValue.isDirectory() && fs.existsSync(journalPath)) {
      const journal = JSON.parse(fs.readFileSync(journalPath, "utf8"));
      if (journal.mutation_started && journal.operation_pending !== null
          && !failedMutationBoundarySync) {
        failedMutationBoundarySync = true;
        throw new Error("fsync mutation boundary interrupted");
      }
    }
    return originalFsyncSync(descriptor);
  };
}
let failOwnedUnload = [
  "recover-owned", "recover-unowned", "recovery-owned-unload-timeout",
  "recovery-restore-timeout", "callback-and-cleanup-error",
  "recover-live-process-group", "recover-ambiguous-process-group",
  "recover-replaced-instance", "recover-replaced-config",
  "recover-restore-insufficient-headroom",
  "recover-binding-mutation-before-restore",
  "recover-malformed-process-group",
].includes(scenario) || scenario.startsWith("recover-malformed-initial-");
let failRestore = false;
let restoreTimeoutOnce = scenario === "restore-load-timeout" || scenario === "recover-stale-lock";
let inRecovery = false;
let fakeProcessGroupAlive = scenario === "recover-live-process-group"
  || scenario === "recover-ambiguous-process-group";
const testProcessGroupRecord = {
  leader_pid: 4242,
  pgid: 4242,
  uid: process.getuid(),
  leader_start_time: "Sun Aug 30 12:00:00 2026",
  leader_executable: fs.realpathSync(process.execPath),
  token: "c".repeat(64),
};
const loaded = [];
let inventoryReads = 0;
let runtimeIdentityReads = 0;
const runtimeIdentity = {
  sdk: {
    name: "@lmstudio/sdk", version: "1.5.0",
    entry_sha256: "f657b4df6408212756deb8001bb66540c1072818879dc298740f9e05de237ef3",
    closure_sha256: "a5ca5d8499398a31eee23963b77c320594092698222fd6010ae5a56b5b925dcc",
    dependency_closure_sha256: "8eb5d5bafa79d0f7ba2f341615b3faeb07fd4919116bd63aab8fd09503fdbe20",
  },
  helper: {sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
  backends: {
    GGUF: {
      name: "llama.cpp-mac-arm64-apple-metal-advsimd", version: "2.31.2",
      primary_file: "libllama-common.0.3.0.dylib",
      primary_sha256: "cb2af513d90ce7913605138089d0c85a941ca57b625e84798473672f76981549",
      manifest_sha256: "55f5f12ebb829498bceb5c1d73b3831d5c9d3a102426fd64887c8e97cbba6d80",
      closure_sha256: "080991a78008280a043d27b908f4d0264240dd935736d74258d4c9ab757e4629",
    },
    MLX: {
      name: "mlx-llm-mac-arm64-apple-metal-nax-advsimd", version: "1.11.0",
      primary_file: "libllm_engine.dylib",
      primary_sha256: "0f5cd7c2f2253d6f1648c1809c63c556c14d0d94061af68e4ba3477a53d986cb",
      manifest_sha256: "39f21df46847eb9e05f542db597027fe585d829d2d12ed7fe909bf3b0f3eace2",
      closure_sha256: "b81597a447b38ba61b5cb17c7e2336a4e7cafc9e90506adc629154a5b2a75783",
    },
  },
};
if (scenario === "backend-binary-mismatch") runtimeIdentity.backends.GGUF.primary_sha256 = "0".repeat(64);
if (scenario === "artifact-identity-mismatch") rows[1].quantization.bits = 5;

function clone(value) { return JSON.parse(JSON.stringify(value)); }
function sortValue(value) {
  if (Array.isArray(value)) return value.map(sortValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, sortValue(value[key])]));
  }
  return value;
}
function canonicalSha256(value) {
  return crypto.createHash("sha256").update(JSON.stringify(sortValue(value))).digest("hex");
}
function sourceFor(key) {
  const row = rows.find(candidate => candidate.modelKey === key);
  if (!row) throw new Error(`missing source ${key}`);
  return row;
}
function addLoaded(key, identifier, config, instance, ttlMs = null) {
  const row = sourceFor(key);
  const record = {
    info: {
      modelKey: row.modelKey,
      identifier,
      indexedModelIdentifier: row.indexedModelIdentifier,
      selectedVariant: row.selectedVariant,
      instanceReference: instance,
      deviceIdentifier: null,
      contextLength: config.contextLength,
      ttlMs,
      lastUsedTime: null,
    },
    config: clone(config),
    processingReads: 0,
  };
  record.handle = {
    async getModelInfo() {
      fullTrace.push(`get-info:${record.info.identifier}`);
      return clone(record.info);
    },
    async getLoadConfig() {
      fullTrace.push(`get-config:${record.info.identifier}`);
      return clone(record.config);
    },
    async getInstanceProcessingState() {
      fullTrace.push(`get-processing:${record.info.identifier}`);
      record.processingReads += 1;
      if ((scenario === "busy-before-initial-unload"
          && record.info.identifier === "initial-model" && record.processingReads === 3)
          || (scenario === "busy-before-owned-unload"
            && record.info.identifier.startsWith("codex-bakeoff-")
            && record.processingReads === 3)) {
        return {status: "processing", queued: 1};
      }
      return {status: "idle", queued: 0};
    },
    async unload() {
      trace.push(`unload:${record.info.identifier}`);
      fullTrace.push(`unload:${record.info.identifier}`);
      if (scenario === "unload-timeout-ambiguous" && record.info.identifier === "initial-model") {
        record.info.identifier = "unowned-model";
        return await new Promise(() => {});
      }
      if (scenario === "owned-unload-timeout" && record.info.identifier.startsWith("codex-bakeoff-")) {
        return await new Promise(() => {});
      }
      if (scenario === "load-error-created-owned-unload-timeout"
          && record.info.identifier.startsWith("codex-bakeoff-")) {
        return await new Promise(() => {});
      }
      if (scenario === "recovery-owned-unload-timeout" && inRecovery
          && record.info.identifier.startsWith("codex-bakeoff-")) {
        return await new Promise(() => {});
      }
      if (record.info.identifier.startsWith("codex-bakeoff-") && failOwnedUnload) {
        failOwnedUnload = false;
        throw new Error("owned unload interrupted");
      }
      loaded.splice(loaded.indexOf(record), 1);
    },
  };
  loaded.push(record);
  return record.handle;
}

const initialConfig = {
  contextLength: 65536,
  maxParallelPredictions: 1,
  gpu: {ratio: "max"},
  flashAttention: true,
  speculativeDraftMtp: false,
  speculativeDraftSimple: false,
  useFp16ForKVCache: true,
  llamaKCacheQuantizationType: false,
  llamaVCacheQuantizationType: false,
};
if (scenario !== "zero-initial") {
  addLoaded("qwen/qwen3.8-27b", "initial-model", initialConfig, "instance-initial", 30000);
}
if (scenario === "initial-extra-config") loaded[0].config.unreviewedOption = true;
if (scenario === "initial-config-context-mismatch") {
  loaded[0].config.contextLength = 32768;
}

const testRuntimeIdentity = async backends => {
  runtimeIdentityReads += 1;
  if (scenario === "target-engine-toctou" && runtimeIdentityReads === 2) {
    runtimeIdentity.helper.sha256 = "b".repeat(64);
  }
  fullTrace.push(`runtime-identity:${backends.join(",")}`);
  return clone(runtimeIdentity);
};
const client = {
  llm: {
    async listLoaded() {
      fullTrace.push(`list-loaded:${loaded.map(row => row.info.identifier).join(",") || "zero"}`);
      return loaded.map(row => row.handle);
    },
    async load(specifier, options) {
      trace.push(`load:${specifier}:${options.identifier}`);
      fullTrace.push(`load:${specifier}:${options.identifier}`);
      if (!options.signal) throw new Error("load omitted AbortSignal");
      if (options.signal && options.signal.aborted) throw new Error("load aborted");
      const row = rows.find(candidate => candidate.selectedVariant === specifier);
      if (!row) throw new Error(`unknown exact variant ${specifier}`);
      if (scenario === "load-timeout" && options.identifier.startsWith("codex-bakeoff-")) {
        return await new Promise((resolve, reject) => {
          options.signal.addEventListener("abort", () => reject(new Error("load aborted")), {once: true});
        });
      }
      if (scenario === "load-error-created-owned-unload-timeout"
          && options.identifier.startsWith("codex-bakeoff-")) {
        addLoaded(row.modelKey, options.identifier, options.config,
          `instance-${options.identifier}`, null);
        throw new Error("target load failed after creating owned instance");
      }
      if (restoreTimeoutOnce && options.identifier === "initial-model") {
        restoreTimeoutOnce = false;
        return await new Promise(() => {});
      }
      if (scenario === "recovery-restore-timeout" && inRecovery
          && options.identifier === "initial-model") {
        return await new Promise(() => {});
      }
      if (failRestore && options.identifier === "initial-model") {
        throw new Error("restore interrupted");
      }
      const ttlMs = options.ttl === undefined ? null : options.ttl * 1000;
      const effectiveConfig = clone(options.config);
      if (scenario === "effective-config-mismatch"
          && options.identifier.startsWith("codex-bakeoff-")) {
        effectiveConfig.flashAttention = false;
      }
      if (scenario === "target-extra-config"
          && options.identifier.startsWith("codex-bakeoff-")) {
        effectiveConfig.unreviewedOption = true;
      }
      const returnedHandle = addLoaded(row.modelKey, options.identifier, effectiveConfig,
        `instance-${options.identifier}`, ttlMs);
      if (scenario === "returned-handle-replaced"
          && options.identifier.startsWith("codex-bakeoff-")) {
        const original = loaded.pop();
        addLoaded(row.modelKey, options.identifier, effectiveConfig,
          "replacement-instance", ttlMs);
        return original.handle;
      }
      return returnedHandle;
    },
  },
  system: {
    async listDownloadedModels(domain) {
      inventoryReads += 1;
      fullTrace.push(`inventory:${domain}`);
      if (domain !== "llm") throw new Error("domain was not local llm");
      if (scenario === "target-artifact-toctou" && inventoryReads === 2) {
        rows.find(row => row.modelKey === "meta/muse-glimmer").sizeBytes += 1;
      }
      if (scenario === "post-restore-artifact-toctou" && inventoryReads === 5) {
        rows.find(row => row.modelKey === "qwen/qwen3.8-27b").sizeBytes += 1;
      }
      if (scenario === "recover-binding-mutation-before-restore"
          && inRecovery && loaded.length === 0) {
        rows.find(row => row.modelKey === "qwen/qwen3.8-27b").sizeBytes += 1;
      }
      return clone(rows);
    },
  },
  runtime: {engine: {async getSelections() {
    fullTrace.push("engine-selections");
    return new Map([
      ["GGUF", {name: "llama.cpp-mac-arm64-apple-metal-advsimd", version: "2.31.2"}],
      ["MLX", {name: "mlx-llm-mac-arm64-apple-metal-nax-advsimd", version: "1.11.0"}],
    ]);
  }}},
};

let resourceSampleCount = 0;
const targetModelKey = scenario === "mlx-profile" ? "google/gemma-4-31b" : "meta/muse-glimmer";
const profileName = scenario === "mlx-profile"
  ? "mlx-native" : scenario === "q8-profile" ? "q8_0" : "f16";
let callbackConfig = null;
let callbackOwnership = null;
let callbackTimeoutMs = null;
let journalContainsSdkPath = null;
const safeResources = async () => {
  resourceSampleCount += 1;
  fullTrace.push("resource-probe");
  return {
    free_memory_percent: (scenario === "pressure"
      || (scenario === "pressure-after-load" && resourceSampleCount === 3)) ? 5 : 40,
    swap_free_bytes: scenario === "insufficient-physical-huge-swap"
      ? 1024 * 1024 * 1024 * 1024 : 3 * 1024 * 1024 * 1024,
    pages_throttled: 0,
    load_1m: 2,
    logical_cpus: 18,
    total_memory_bytes: (
      (scenario === "insufficient-projected-headroom"
        || scenario === "insufficient-physical-huge-swap") && resourceSampleCount === 2
      || scenario === "recover-restore-insufficient-headroom"
        && inRecovery && loaded.length === 0
    ) ? 32 * 1024 * 1024 * 1024 : 128 * 1024 * 1024 * 1024,
  };
};

(async () => {
  let firstError = null;
  let result = null;
  if (scenario === "recover-pre-mutation") {
    fs.writeFileSync(journalPath, JSON.stringify({
      schema_version: 2,
      transaction_id: "abc123",
      target_model_key: "meta/muse-glimmer",
      selected_variant: "meta/muse-glimmer@q4_k_m",
      profile: "f16",
      owned_identifier: "codex-bakeoff-abc123-meta-muse-glimmer",
      initial_snapshot: null,
      artifact_fingerprints_pre: null,
      engine_binding_pre: null,
      phase: "journal_created",
      mutation_started: false,
      operation_pending: null,
    }) + "\n", {mode: 0o600});
    fs.chmodSync(journalPath, 0o600);
    fs.writeFileSync(lockPath, JSON.stringify({
      schema_version: 1, kind: "lmstudio-model-lifecycle-lock-v1", pid: 999999,
    }) + "\n", {mode: 0o600});
    fs.chmodSync(lockPath, 0o600);
  } else try {
    result = await lifecycle.offlineTestDriver.runTransaction({
      client,
      testRuntimeIdentity,
      endpoint: "ws://127.0.0.1:1234",
      targetModelKey,
      profileName,
      transactionId: "abc123",
      journalPath,
      lockPath,
      resourceProbe: safeResources,
      idleSampleDelayMs: 0,
      timeouts: {loadMs: 15, unloadMs: 15},
      ...(scenario === "custom-callback-timeout" ? {callbackTimeoutMs: 3600000}
        : scenario === "callback-never-settles" ? {callbackTimeoutMs: 15} : {}),
      callback: async ({identifier, effectiveSnapshot, registerProcessGroup}) => {
        trace.push(`callback:${identifier}`);
        fullTrace.push(`callback:${identifier}`);
        callbackConfig = clone(effectiveSnapshot.load_config);
        const callbackJournal = JSON.parse(fs.readFileSync(journalPath, "utf8"));
        journalContainsSdkPath = fs.readFileSync(journalPath, "utf8")
          .includes("/offline-test-only/@lmstudio/sdk/dist/index.cjs");
        callbackOwnership = clone(callbackJournal.owned_target_ownership ?? null);
        callbackTimeoutMs = callbackJournal.callback_timeout_ms ?? null;
        if (scenario === "callback-group-remains") {
          registerProcessGroup({...testProcessGroupRecord, token: "d".repeat(64)});
        }
        const mode = fs.statSync(journalPath).mode & 0o777;
        if (mode !== 0o600) throw new Error(`journal mode ${mode.toString(8)}`);
        if (scenario === "callback-error" || scenario === "callback-and-cleanup-error") {
          throw new Error("callback interrupted");
        }
        if (scenario === "callback-never-settles") return await new Promise(() => {});
        if (scenario === "artifact-change") rows[1].sizeBytes += 1;
        if (scenario === "owned-replaced-before-cleanup") {
          loaded[0].info.instanceReference = "replacement-instance";
        }
        if (scenario === "owned-config-replaced-before-cleanup") {
          loaded[0].config.flashAttention = false;
        }
        if (scenario === "runtime-binding-change") runtimeIdentity.helper.sha256 = "b".repeat(64);
        if (scenario === "journal-removal-failure") {
          fs.unlinkSync = file => {
            if (file === journalPath) throw new Error("journal unlink interrupted");
            return originalUnlinkSync(file);
          };
        }
        return {ok: true};
      },
    });
  } catch (error) {
    firstError = {message: error.message, audit: error.lifecycleAudit || null};
  }

  let recovery = null;
  if ([
    "recover-owned", "recover-unowned", "recover-stale-lock",
    "recovery-owned-unload-timeout", "recovery-restore-timeout", "recover-pre-mutation",
    "recover-live-process-group", "recover-ambiguous-process-group",
    "recover-replaced-instance", "recover-replaced-config",
    "recover-restore-insufficient-headroom",
    "recover-binding-mutation-before-restore",
    "recover-malformed-process-group",
  ].includes(scenario) || scenario.startsWith("recover-malformed-initial-")) {
    if (scenario === "recover-unowned" && loaded.length === 1) {
      loaded[0].info.identifier = "unowned-model";
    }
    if (scenario === "recover-replaced-instance" && loaded.length === 1) {
      loaded[0].info.instanceReference = "replacement-instance";
    }
    if (scenario === "recover-replaced-config" && loaded.length === 1) {
      loaded[0].config.flashAttention = false;
    }
    if (scenario.startsWith("recover-malformed-initial-")) {
      const journal = JSON.parse(fs.readFileSync(journalPath, "utf8"));
      const initial = journal.initial_snapshot;
      if (scenario === "recover-malformed-initial-context") {
        initial.load_config.contextLength = 32768;
      } else if (scenario === "recover-malformed-initial-variant") {
        initial.selected_variant = "meta/muse-glimmer@q4_k_m";
      } else if (scenario === "recover-malformed-initial-indexed") {
        initial.indexed_model_identifier = "meta/muse-glimmer";
      } else if (scenario === "recover-malformed-initial-ttl") {
        initial.ttl_ms = -1;
      } else if (scenario === "recover-malformed-initial-device") {
        initial.device_identifier = "remote-host";
      } else if (scenario === "recover-malformed-initial-missing") {
        journal.initial_snapshot = null;
      } else if (scenario === "recover-malformed-initial-oversized-context") {
        initial.context_length = 262145;
        initial.load_config.contextLength = 262145;
      }
      journal.initial_snapshot_sha256 = canonicalSha256(journal.initial_snapshot);
      fs.writeFileSync(journalPath, JSON.stringify(journal) + "\n", {mode: 0o600});
      fs.chmodSync(journalPath, 0o600);
    }
    if (scenario === "recover-stale-lock") {
      fs.writeFileSync(lockPath, JSON.stringify({
        schema_version: 1,
        kind: "lmstudio-model-lifecycle-lock-v1",
        pid: 999999,
      }) + "\n", {mode: 0o600});
      fs.chmodSync(lockPath, 0o600);
    }
    if (scenario === "recover-live-process-group" || scenario === "recover-ambiguous-process-group") {
      const journal = JSON.parse(fs.readFileSync(journalPath, "utf8"));
      journal.callback_process_group = testProcessGroupRecord;
      fs.writeFileSync(journalPath, JSON.stringify(journal) + "\n", {mode: 0o600});
      fs.chmodSync(journalPath, 0o600);
    }
    if (scenario === "recover-malformed-process-group") {
      const journal = JSON.parse(fs.readFileSync(journalPath, "utf8"));
      journal.callback_process_group = {
        pgid: 4242, uid: process.getuid(), token: "c".repeat(64),
      };
      fs.writeFileSync(journalPath, JSON.stringify(journal) + "\n", {mode: 0o600});
      fs.chmodSync(journalPath, 0o600);
    }
    inRecovery = true;
    try {
      recovery = await lifecycle.offlineTestDriver.recover({
        client, testRuntimeIdentity, journalPath, lockPath, resourceProbe: safeResources,
        idleSampleDelayMs: 0, timeouts: {loadMs: 15, unloadMs: 15},
        processGroupProbe: async record => {
          trace.push(`process-group-probe:${record.pgid}`);
          fullTrace.push(`process-group-probe:${record.pgid}`);
          return {
            alive: fakeProcessGroupAlive,
            owned: scenario !== "recover-ambiguous-process-group",
          };
        },
        processGroupTerminate: async record => {
          trace.push(`process-group-terminate:${record.pgid}`);
          fullTrace.push(`process-group-terminate:${record.pgid}`);
          fakeProcessGroupAlive = false;
        },
      });
    } catch (error) {
      recovery = {error: error.message, audit: error.lifecycleAudit || null};
    }
  }
  console.log(JSON.stringify({
    result,
    firstError,
    recovery,
    trace,
    fullTrace,
    loaded: loaded.map(row => row.info.identifier),
    loadedTtls: loaded.map(row => row.info.ttlMs),
    callbackConfig,
    callbackOwnership,
    callbackTimeoutMs,
    journalContainsSdkPath,
    journalExists: fs.existsSync(journalPath),
    lockExists: fs.existsSync(lockPath),
  }));
  fs.unlinkSync = originalUnlinkSync;
  fs.fsyncSync = originalFsyncSync;
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""


FAKE_PARK_RUNNER = r"""
const fs = require("node:fs");
const lifecycle = require(process.argv[1]);
const work = process.argv[2];
const scenario = process.argv[3];
const journalPath = `${work}/.lmstudio-model-lifecycle-recovery.json`;
const lockPath = `${work}/.lmstudio-model-lifecycle.lock`;
const rows = JSON.parse(fs.readFileSync(`${work}/rows.json`, "utf8"));
const trace = [];
const loaded = [];
let pendingSeenAtUnload = null;
let failNextListAfterUnload = false;
let resourceReads = 0;
let engineReads = 0;

const runtimeIdentity = {
  sdk: {
    name: "@lmstudio/sdk", version: "1.5.0",
    entry_sha256: "f657b4df6408212756deb8001bb66540c1072818879dc298740f9e05de237ef3",
    closure_sha256: "a5ca5d8499398a31eee23963b77c320594092698222fd6010ae5a56b5b925dcc",
    dependency_closure_sha256: "8eb5d5bafa79d0f7ba2f341615b3faeb07fd4919116bd63aab8fd09503fdbe20",
  },
  helper: {sha256: "a".repeat(64)},
  backends: {
    GGUF: {
      name: "llama.cpp-mac-arm64-apple-metal-advsimd", version: "2.31.2",
      primary_file: "libllama-common.0.3.0.dylib",
      primary_sha256: "cb2af513d90ce7913605138089d0c85a941ca57b625e84798473672f76981549",
      manifest_sha256: "55f5f12ebb829498bceb5c1d73b3831d5c9d3a102426fd64887c8e97cbba6d80",
      closure_sha256: "080991a78008280a043d27b908f4d0264240dd935736d74258d4c9ab757e4629",
    },
    MLX: {
      name: "mlx-llm-mac-arm64-apple-metal-nax-advsimd", version: "1.11.0",
      primary_file: "libllm_engine.dylib",
      primary_sha256: "0f5cd7c2f2253d6f1648c1809c63c556c14d0d94061af68e4ba3477a53d986cb",
      manifest_sha256: "39f21df46847eb9e05f542db597027fe585d829d2d12ed7fe909bf3b0f3eace2",
      closure_sha256: "b81597a447b38ba61b5cb17c7e2336a4e7cafc9e90506adc629154a5b2a75783",
    },
  },
};

function clone(value) { return JSON.parse(JSON.stringify(value)); }
function sourceFor(key) {
  const row = rows.find(candidate => candidate.modelKey === key);
  if (!row) throw new Error(`missing source ${key}`);
  return row;
}
function addLoaded(key, identifier, instanceReference) {
  const row = sourceFor(key);
  const config = row.format === "gguf" ? {
    contextLength: 65536,
    maxParallelPredictions: 1,
    gpu: {ratio: "max"},
    flashAttention: true,
    speculativeDraftMtp: false,
    speculativeDraftSimple: false,
    useFp16ForKVCache: true,
    llamaKCacheQuantizationType: false,
    llamaVCacheQuantizationType: false,
  } : {
    contextLength: 65536,
    maxParallelPredictions: 1,
    mlxDiskCache: false,
    mlxKvCacheQuantization: false,
  };
  const record = {
    info: {
      modelKey: row.modelKey,
      identifier,
      indexedModelIdentifier: row.indexedModelIdentifier,
      selectedVariant: row.selectedVariant,
      instanceReference,
      deviceIdentifier: null,
      contextLength: 65536,
      ttlMs: null,
      lastUsedTime: null,
    },
    config,
    processingReads: 0,
  };
  record.handle = {
    async getModelInfo() {
      trace.push(`info:${record.info.identifier}`);
      return clone(record.info);
    },
    async getLoadConfig() {
      trace.push(`config:${record.info.identifier}`);
      return clone(record.config);
    },
    async getInstanceProcessingState() {
      record.processingReads += 1;
      trace.push(`processing:${record.info.identifier}:${record.processingReads}`);
      if (scenario === "busy-before-unload" && record.processingReads === 3) {
        return {status: "processing", queued: 1};
      }
      return {status: "idle", queued: 0};
    },
    async unload() {
      trace.push(`unload:${record.info.identifier}`);
      pendingSeenAtUnload = clone(JSON.parse(fs.readFileSync(journalPath, "utf8")));
      if (scenario === "unload-timeout") return await new Promise(() => {});
      if (scenario === "settled-unload-error" || scenario === "recover-no-mutation"
          || scenario === "recover-unknown") {
        throw new Error("park unload rejected");
      }
      loaded.splice(loaded.indexOf(record), 1);
      if (scenario === "recover-zero") failNextListAfterUnload = true;
      if (scenario === "artifact-change") row.sizeBytes += 1;
    },
  };
  loaded.push(record);
  return record;
}

if (scenario !== "zero-loaded") {
  const parked = addLoaded("meta/muse-glimmer", "parked-model", "instance-parked");
  if (scenario === "wrong-variant") parked.info.selectedVariant = "meta/muse-glimmer@q5_k_m";
  if (scenario === "remote-model") parked.info.deviceIdentifier = "remote-host";
}
if (scenario === "multiple-loaded") {
  addLoaded("qwen/qwen3.8-27b", "second-model", "instance-second");
}

const testRuntimeIdentity = async backends => {
  trace.push(`runtime:${backends.join(",")}`);
  return clone(runtimeIdentity);
};
const client = {
  llm: {
    async listLoaded() {
      trace.push(`list:${loaded.map(row => row.info.identifier).join(",") || "zero"}`);
      if (failNextListAfterUnload) {
        failNextListAfterUnload = false;
        throw new Error("simulated crash after settled unload");
      }
      return loaded.map(row => row.handle);
    },
    async load() {
      trace.push("FORBIDDEN-LOAD");
      throw new Error("park must never load");
    },
  },
  system: {
    async listDownloadedModels(domain) {
      trace.push(`inventory:${domain}`);
      return clone(rows);
    },
  },
  runtime: {engine: {async getSelections() {
    engineReads += 1;
    trace.push("engine");
    if (scenario === "model-appears-after-zero" && engineReads === 2) {
      addLoaded("qwen/qwen3.8-27b", "late-model", "instance-late");
    }
    return new Map([
      ["GGUF", {name: "llama.cpp-mac-arm64-apple-metal-advsimd", version: "2.31.2"}],
      ["MLX", {name: "mlx-llm-mac-arm64-apple-metal-nax-advsimd", version: "1.11.0"}],
    ]);
  }}},
};

const resources = async () => {
  resourceReads += 1;
  trace.push(`resource:${resourceReads}`);
  return {
    free_memory_percent: 1,
    swap_free_bytes: 0,
    pages_throttled: scenario === "pages-throttled" ? 1 : 0,
    load_1m: 2,
    logical_cpus: 18,
  };
};

(async () => {
  let result = null;
  let firstError = null;
  try {
    result = await lifecycle.offlineTestDriver.park({
      client,
      testRuntimeIdentity,
      journalPath,
      lockPath,
      resourceProbe: resources,
      idleSampleDelayMs: 0,
      timeouts: {unloadMs: 15},
    });
  } catch (error) {
    firstError = {message: error.message, audit: error.lifecycleAudit || null};
  }

  let recovery = null;
  if (["recover-zero", "recover-no-mutation", "recover-unknown", "unload-timeout"].includes(scenario)
      && fs.existsSync(journalPath)) {
    if (scenario === "recover-unknown" && loaded.length === 1) {
      loaded[0].info.identifier = "unknown-model";
    }
    if (scenario === "unload-timeout" && fs.existsSync(lockPath)) {
      fs.writeFileSync(lockPath, JSON.stringify({
        schema_version: 1,
        kind: "lmstudio-model-lifecycle-lock-v1",
        pid: 999999,
      }) + "\n", {mode: 0o600});
      fs.chmodSync(lockPath, 0o600);
    }
    try {
      recovery = await lifecycle.offlineTestDriver.recover({
        client,
        testRuntimeIdentity,
        journalPath,
        lockPath,
        resourceProbe: resources,
        idleSampleDelayMs: 0,
        timeouts: {unloadMs: 15, loadMs: 15},
      });
    } catch (error) {
      recovery = {error: error.message, audit: error.lifecycleAudit || null};
    }
  }

  console.log(JSON.stringify({
    result,
    firstError,
    recovery,
    trace,
    pendingSeenAtUnload,
    loaded: loaded.map(row => row.info.identifier),
    journal: fs.existsSync(journalPath)
      ? JSON.parse(fs.readFileSync(journalPath, "utf8")) : null,
    journalExists: fs.existsSync(journalPath),
    lockExists: fs.existsSync(lockPath),
  }));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""


class ModelBakeoffPlanTests(unittest.TestCase):
    def test_plan_reads_inventory_once_and_emits_backend_native_profiles(self):
        """Catches a dry-run that mutates LM Studio or claims GGUF settings for MLX."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = root / "calls.jsonl"
            cli = root / "lms"
            cli.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$*\" >> {calls!s}\n"
                "[ \"$1\" = ls ] && [ \"$2\" = --json ] || exit 91\n"
                "printf '%s\\n' '" + json.dumps(MODEL_ROWS) + "'\n"
            )
            cli.chmod(0o755)

            completed = subprocess.run(
                ["python3", str(BAKEOFF), "plan", "--lms-cli", str(cli), "--json"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(calls.read_text().splitlines(), ["ls --json"])
            plan = json.loads(completed.stdout)
            self.assertEqual(plan["context_length"], 32_768)
            self.assertEqual(plan["packet_envelope"], {
                "max_input_tokens": 20_480,
                "max_output_tokens": 8_192,
                "runtime_reserve_tokens": 4_096,
            })
            self.assertIn("no abort signal", plan["lifecycle_boundary"].lower())
            self.assertIn("never counted", plan["load_capacity_policy"].lower())
            self.assertIn("physical/metal", plan["load_capacity_policy"].lower())
            self.assertIn("metadata", plan["artifact_fingerprint_scope"].lower())
            self.assertEqual([row["model_key"] for row in plan["models"]], [
                "qwen/qwen3.6-35b-a3b", "meta/muse-glimmer",
                "google/gemma-4-31b", "google/gemma-4-26b-a4b-qat",
                "qwen/qwen3.8-27b",
            ])
            gguf = next(row for row in plan["models"] if row["model_key"] == "meta/muse-glimmer")
            self.assertEqual(gguf["profiles"]["f16"]["load_config"], {
                "contextLength": 32_768,
                "flashAttention": True,
                "gpu": {"ratio": "max"},
                "llamaKCacheQuantizationType": False,
                "llamaVCacheQuantizationType": False,
                "maxParallelPredictions": 1,
                "speculativeDraftMtp": False,
                "speculativeDraftSimple": False,
                "useFp16ForKVCache": True,
            })
            self.assertEqual(gguf["profiles"]["q8_0"]["load_config"]["llamaVCacheQuantizationType"], "q8_0")
            mlx = next(row for row in plan["models"] if row["model_key"] == "google/gemma-4-31b")
            self.assertEqual(mlx["profiles"], {"mlx-native": {"load_config": {
                "contextLength": 32_768,
                "maxParallelPredictions": 1,
                "mlxDiskCache": False,
                "mlxKvCacheQuantization": False,
            }}})

    def test_plan_rejects_a_changed_or_ambiguous_selected_variant(self):
        """Catches alias resolution that could benchmark a different downloaded artifact."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cli = root / "lms"
            bad_rows = [dict(row) for row in MODEL_ROWS]
            bad_rows[-1]["selectedVariant"] = "qwen/qwen3.8-27b@q5_k_m"
            cli.write_text(
                "#!/bin/sh\nprintf '%s\\n' '" + json.dumps(bad_rows) + "'\n"
            )
            cli.chmod(0o755)
            completed = subprocess.run(
                ["python3", str(BAKEOFF), "plan", "--lms-cli", str(cli), "--json"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("selected variant", completed.stderr.lower())

    def test_plan_rejects_inconsistent_quantization_bits_and_artifact_identifiers(self):
        """Catches a reviewed alias attached to a different local artifact identity."""

        for field, value, expected_message in (
            ("bits", 5, "quantization"),
            ("path", "other/artifact", "quantization"),
            ("indexedModelIdentifier", "other/artifact", "quantization"),
            ("sizeBytes", MODEL_ROWS[1]["sizeBytes"] + 1, "artifact size"),
            (
                "maxContextLength",
                MODEL_ROWS[1]["maxContextLength"] + 1,
                "native context",
            ),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                cli = Path(directory) / "lms"
                bad_rows = json.loads(json.dumps(MODEL_ROWS))
                if field == "bits":
                    bad_rows[1]["quantization"][field] = value
                else:
                    bad_rows[1][field] = value
                cli.write_text("#!/bin/sh\nprintf '%s\\n' '" + json.dumps(bad_rows) + "'\n")
                cli.chmod(0o755)
                completed = subprocess.run(
                    ["python3", str(BAKEOFF), "plan", "--lms-cli", str(cli), "--json"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(expected_message, completed.stderr.lower())

    def test_mutation_command_refuses_before_sdk_discovery_without_explicit_flag(self):
        """Catches even a read-only SDK connection preceding mutation authorization."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = subprocess.run(
                [
                    NODE_BINARY, str(LIFECYCLE), "run",
                    "--target", "meta/muse-glimmer", "--profile", "f16",
                    "--transaction-id", "abc123",
                    "--journal", str(root / "recovery.json"),
                    "--lock", str(root / "transaction.lock"),
                    "--", "/usr/bin/true",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"HOME": str(root), "PATH": "/usr/bin:/bin"},
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("requires --allow-model-mutation", completed.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_park_refuses_before_sdk_discovery_without_explicit_flag(self):
        """Catches pressure relief connecting to LM Studio without explicit mutation consent."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = subprocess.run(
                [NODE_BINARY, str(LIFECYCLE), "park"],
                check=False,
                capture_output=True,
                text=True,
                env={"HOME": str(root), "PATH": "/usr/bin:/bin"},
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("requires --allow-model-mutation", completed.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_unreviewed_sdk_closure_is_rejected_before_its_entry_executes(self):
        """Catches requiring an altered SDK before its reviewed entry and closure are verified."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sdk = (
                root
                / ".lmstudio"
                / "extensions"
                / "plugins"
                / "fixture"
                / "node_modules"
                / "@lmstudio"
                / "sdk"
            )
            (sdk / "dist").mkdir(parents=True)
            marker = root / "sdk-entry-executed"
            (sdk / "package.json").write_text(
                json.dumps({"name": "@lmstudio/sdk", "version": "1.5.0"})
            )
            (sdk / "dist" / "index.cjs").write_text(
                "require('node:fs').writeFileSync("
                + json.dumps(str(marker))
                + ", 'executed'); module.exports = {LMStudioClient: class {}};\n"
            )
            completed = subprocess.run(
                [NODE_BINARY, str(LIFECYCLE), "plan"],
                check=False,
                capture_output=True,
                text=True,
                env={"HOME": str(root), "PATH": "/usr/bin:/bin"},
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("reviewed", completed.stderr.lower())
            self.assertIn("sdk", completed.stderr.lower())
            self.assertFalse(marker.exists())

    def test_altered_sdk_transitive_dependency_closure_is_rejected_before_client_use(self):
        """Catches verifying only the SDK package while executing altered dependencies."""

        entries = sorted(
            Path.home().glob(
                ".lmstudio/extensions/plugins/**/@lmstudio/sdk/dist/index.cjs"
            )
        )
        self.assertTrue(entries, "reviewed local SDK fixture is unavailable")
        source_node_modules = entries[0].parents[3]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = (
                root
                / ".lmstudio"
                / "extensions"
                / "plugins"
                / "fixture"
                / "node_modules"
            )
            shutil.copytree(source_node_modules, destination)
            dependency = destination / "chalk" / "package.json"
            dependency.write_text(dependency.read_text() + "\n")
            completed = subprocess.run(
                [NODE_BINARY, str(LIFECYCLE), "plan"],
                check=False,
                capture_output=True,
                text=True,
                env={"HOME": str(root), "PATH": "/usr/bin:/bin"},
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("sdk", completed.stderr.lower())
            self.assertIn("dependency closure", completed.stderr.lower())


class ModelLifecycleTests(unittest.TestCase):
    def run_scenario(self, scenario):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rows.json").write_text(json.dumps(MODEL_ROWS))
            completed = run_node(FAKE_TRANSACTION_RUNNER, root, scenario)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            return json.loads(completed.stdout)

    def test_success_uses_the_full_owned_transaction_and_restores_exact_state(self):
        """Catches skipped cleanup, broad unloads, or failure to restore the original identifier."""

        output = self.run_scenario("success")
        self.assertIsNone(output["firstError"])
        self.assertEqual(output["trace"], [
            "unload:initial-model",
            "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
            "callback:codex-bakeoff-abc123-meta-muse-glimmer",
            "unload:codex-bakeoff-abc123-meta-muse-glimmer",
            "load:qwen/qwen3.8-27b@q4_k_m:initial-model",
        ])
        self.assertEqual(output["fullTrace"], [
            "resource-probe",
            "list-loaded:initial-model",
            "get-info:initial-model",
            "get-config:initial-model",
            "get-processing:initial-model",
            "list-loaded:initial-model",
            "get-info:initial-model",
            "get-config:initial-model",
            "get-processing:initial-model",
            "inventory:llm",
            "engine-selections",
            "runtime-identity:GGUF",
            "list-loaded:initial-model",
            "get-info:initial-model",
            "get-config:initial-model",
            "get-processing:initial-model",
            "list-loaded:initial-model",
            "get-info:initial-model",
            "get-config:initial-model",
            "get-processing:initial-model",
            "unload:initial-model",
            "list-loaded:zero",
            "resource-probe",
            "inventory:llm",
            "engine-selections",
            "runtime-identity:GGUF",
            "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
            "get-info:codex-bakeoff-abc123-meta-muse-glimmer",
            "get-config:codex-bakeoff-abc123-meta-muse-glimmer",
            "get-processing:codex-bakeoff-abc123-meta-muse-glimmer",
            "list-loaded:codex-bakeoff-abc123-meta-muse-glimmer",
            "get-info:codex-bakeoff-abc123-meta-muse-glimmer",
            "get-config:codex-bakeoff-abc123-meta-muse-glimmer",
            "get-processing:codex-bakeoff-abc123-meta-muse-glimmer",
            "resource-probe",
            "callback:codex-bakeoff-abc123-meta-muse-glimmer",
            "list-loaded:codex-bakeoff-abc123-meta-muse-glimmer",
            "get-info:codex-bakeoff-abc123-meta-muse-glimmer",
            "get-config:codex-bakeoff-abc123-meta-muse-glimmer",
            "get-processing:codex-bakeoff-abc123-meta-muse-glimmer",
            "list-loaded:codex-bakeoff-abc123-meta-muse-glimmer",
            "get-info:codex-bakeoff-abc123-meta-muse-glimmer",
            "get-config:codex-bakeoff-abc123-meta-muse-glimmer",
            "get-processing:codex-bakeoff-abc123-meta-muse-glimmer",
            "unload:codex-bakeoff-abc123-meta-muse-glimmer",
            "list-loaded:zero",
            "inventory:llm",
            "resource-probe",
            "inventory:llm",
            "engine-selections",
            "runtime-identity:GGUF",
            "load:qwen/qwen3.8-27b@q4_k_m:initial-model",
            "list-loaded:initial-model",
            "get-info:initial-model",
            "get-config:initial-model",
            "get-processing:initial-model",
            "inventory:llm",
            "engine-selections",
            "runtime-identity:GGUF",
        ])
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertEqual(output["loadedTtls"], [30_000])
        self.assertFalse(output["journalExists"])
        self.assertFalse(output["lockExists"])
        self.assertIn("metadata", output["result"]["artifact_fingerprint_scope"].lower())
        self.assertEqual(output["result"]["phases"], [
            "lock_acquired", "journal_created", "host_gate_pre",
            "snapshot_idle_1", "snapshot_idle_2", "snapshot_captured",
            "artifact_fingerprint_pre", "engine_bound_pre",
            "initial_idle_revalidated", "initial_unload_started", "initial_unloaded", "zero_verified",
            "host_gate_target", "target_binding_revalidated", "target_load_started",
            "target_loaded", "target_verified",
            "host_gate_post_load",
            "callback_started", "callback_completed", "owned_idle_revalidated", "owned_unload_started",
            "owned_unloaded", "zero_verified_after_owned_cleanup",
            "artifact_fingerprint_post", "host_gate_restore",
            "initial_restore_binding_revalidated", "initial_restore_started",
            "initial_restored", "restore_verified", "engine_bound_post",
            "artifact_fingerprint_final", "journal_removed", "lock_released",
        ])

    def test_transaction_endpoint_must_match_the_client_creation_receipt(self):
        """Catches endpoint A being supplied beside a client constructed for endpoint B."""

        with tempfile.TemporaryDirectory() as directory:
            runner = r"""
const lifecycle = require(process.argv[1]);
const work = process.argv[2];
const client = {};
(async () => {
  let message = null;
  try {
    await lifecycle.offlineTestDriver.runTransaction({
      client,
      testRuntimeIdentity: async () => ({}),
      testClientEndpoint: "ws://127.0.0.1:4321",
      endpoint: "ws://127.0.0.1:1234",
      targetModelKey: "meta/muse-glimmer",
      profileName: "f16",
      transactionId: "abc123",
      journalPath: `${work}/.lmstudio-model-lifecycle-recovery.json`,
      lockPath: `${work}/.lmstudio-model-lifecycle.lock`,
      callback: async () => {},
    });
  } catch (error) { message = error.message; }
  console.log(JSON.stringify({message}));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
            completed = run_node(runner, Path(directory))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertIn("endpoint", result["message"].lower())
            self.assertIn("receipt", result["message"].lower())

    def test_production_exports_have_no_endpoint_attestation_or_client_runtime_identity_seam(self):
        """Catches test capabilities remaining callable through the production transaction API."""

        runner = r"""
const lifecycle = require(process.argv[1]);
console.log(JSON.stringify({
  attest: typeof lifecycle.attestTestClientEndpoint,
  run: typeof lifecycle.runLifecycleTransaction,
  park: typeof lifecycle.parkLoadedCandidate,
  recover: typeof lifecycle.recoverLifecycleTransaction,
  command: typeof lifecycle.commandCallback,
}));
"""
        completed = run_node(runner)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {
            "attest": "undefined",
            "run": "undefined",
            "park": "undefined",
            "recover": "undefined",
            "command": "undefined",
        })

    def test_callback_timeout_cli_is_bounded_and_propagated_to_the_journal(self):
        """Catches a long bake-off timeout being ignored or allowed without a finite ceiling."""

        runner = r"""
const lifecycle = require(process.argv[1]);
const results = [];
for (const value of ["0", "7200001", "1.5", "not-a-number"]) {
  try {
    lifecycle.offlineTestDriver.parseCli(["run", "--callback-timeout-ms", value]);
    results.push(null);
  } catch (error) { results.push(error.message); }
}
const valid = lifecycle.offlineTestDriver.parseCli([
  "run", "--callback-timeout-ms", "3600000",
]);
const wrongCommands = [];
for (const command of ["plan", "park", "recover"]) {
  try {
    lifecycle.offlineTestDriver.parseCli([command, "--callback-timeout-ms", "3600000"]);
    wrongCommands.push(null);
  } catch (error) { wrongCommands.push(error.message); }
}
console.log(JSON.stringify({results, valid: valid.callbackTimeoutMs, wrongCommands}));
"""
        completed = run_node(runner)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        parsed = json.loads(completed.stdout)
        self.assertTrue(all("timeout" in value.lower() for value in parsed["results"]))
        self.assertEqual(parsed["valid"], 3_600_000)
        self.assertTrue(
            all("only valid for run" in value.lower() for value in parsed["wrongCommands"])
        )

        output = self.run_scenario("custom-callback-timeout")
        self.assertIsNone(output["firstError"])
        self.assertEqual(output["callbackTimeoutMs"], 3_600_000)
        self.assertEqual(output["result"]["callback_timeout_ms"], 3_600_000)

    def test_complete_owned_projection_is_durable_before_callback(self):
        """Catches a callback starting before exact target ownership is crash-recoverable."""

        output = self.run_scenario("success")
        self.assertFalse(output["journalContainsSdkPath"])
        self.assertNotIn("/offline-test-only/@lmstudio/sdk/dist/index.cjs", json.dumps(output["result"]))
        self.assertEqual(output["callbackOwnership"], {
            "model_key": "meta/muse-glimmer",
            "identifier": "codex-bakeoff-abc123-meta-muse-glimmer",
            "indexed_model_identifier": "meta/muse-glimmer",
            "selected_variant": "meta/muse-glimmer@q4_k_m",
            "instance_reference": (
                "instance-codex-bakeoff-abc123-meta-muse-glimmer"
            ),
            "device_identifier": None,
            "context_length": 32_768,
            "ttl_ms": None,
            "load_config": output["callbackConfig"],
        })

    def test_cleanup_never_unloads_a_same_name_replacement_instance_or_config(self):
        """Catches identifier-only cleanup deleting a replacement loaded after verification."""

        for scenario in (
            "owned-replaced-before-cleanup",
            "owned-config-replaced-before-cleanup",
        ):
            with self.subTest(scenario=scenario):
                output = self.run_scenario(scenario)
                self.assertIn("ownership", output["firstError"]["message"].lower())
                self.assertEqual(
                    output["trace"].count(
                        "unload:codex-bakeoff-abc123-meta-muse-glimmer"
                    ),
                    0,
                )
                self.assertEqual(
                    output["loaded"],
                    ["codex-bakeoff-abc123-meta-muse-glimmer"],
                )
                self.assertTrue(output["journalExists"])

    def test_load_return_handle_must_match_the_sole_loaded_instance_before_ownership(self):
        """Catches load returning A while listLoaded exposes same-name replacement B."""

        output = self.run_scenario("returned-handle-replaced")
        self.assertIn("load-returned", output["firstError"]["message"].lower())
        self.assertNotIn(
            "callback:codex-bakeoff-abc123-meta-muse-glimmer", output["trace"]
        )
        self.assertNotIn(
            "unload:codex-bakeoff-abc123-meta-muse-glimmer", output["trace"]
        )
        self.assertEqual(output["loaded"], ["codex-bakeoff-abc123-meta-muse-glimmer"])
        self.assertTrue(output["journalExists"])

    def test_exact_bindings_are_recaptured_at_every_load_and_after_restore(self):
        """Catches artifact/engine TOCTOU between the initial binding and any later load."""

        cases = {
            "target-artifact-toctou": "target model artifact fingerprint changed",
            "target-engine-toctou": "target model engine binding changed",
            "post-restore-artifact-toctou": "post-restoration binding artifact fingerprint changed",
        }
        for scenario, message in cases.items():
            with self.subTest(scenario=scenario):
                output = self.run_scenario(scenario)
                self.assertIn(message, output["firstError"]["message"].lower())
                if scenario.startswith("target-"):
                    self.assertNotIn(
                        "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
                        output["trace"],
                    )
                    self.assertFalse(any(item.startswith("callback:") for item in output["trace"]))
                self.assertIsNone(output["result"])
                self.assertTrue(output["journalExists"])

        recovery = self.run_scenario("recover-binding-mutation-before-restore")
        self.assertIn("immediately before load", recovery["recovery"]["error"].lower())
        self.assertNotIn(
            "load:qwen/qwen3.8-27b@q4_k_m:initial-model", recovery["trace"]
        )
        self.assertTrue(recovery["journalExists"])

    def test_outer_transaction_deadline_contains_an_arbitrary_unsettled_callback(self):
        """Catches non-command callbacks bypassing the validated transaction deadline."""

        output = self.run_scenario("callback-never-settles")
        self.assertIn("callback exceeded its deadline", output["firstError"]["message"].lower())
        self.assertEqual(output["loaded"], ["codex-bakeoff-abc123-meta-muse-glimmer"])
        self.assertTrue(output["journalExists"])
        self.assertTrue(output["lockExists"])

    def test_callback_interruption_still_cleans_owned_model_and_restores(self):
        """Catches a thrown benchmark callback that strands its model or loses prior state."""

        output = self.run_scenario("callback-error")
        self.assertIn("callback interrupted", output["firstError"]["message"])
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertFalse(output["journalExists"])
        self.assertEqual(output["trace"][-2:], [
            "unload:codex-bakeoff-abc123-meta-muse-glimmer",
            "load:qwen/qwen3.8-27b@q4_k_m:initial-model",
        ])
        self.assertIn("callback_failed", output["firstError"]["audit"]["phases"])
        self.assertIn("transaction_failed_recovered", output["firstError"]["audit"]["phases"])

    def test_registered_callback_group_blocks_all_post_callback_model_mutation(self):
        """Catches unloading or restoring while an owned benchmark descendant may still run."""

        output = self.run_scenario("callback-group-remains")
        self.assertIn("callback process group", output["firstError"]["message"].lower())
        self.assertEqual(output["trace"], [
            "unload:initial-model",
            "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
            "callback:codex-bakeoff-abc123-meta-muse-glimmer",
        ])
        self.assertEqual(output["loaded"], ["codex-bakeoff-abc123-meta-muse-glimmer"])
        self.assertTrue(output["journalExists"])
        self.assertTrue(output["lockExists"])

    def test_zero_initial_state_is_restored_to_exact_zero(self):
        """Catches a transaction that invents a restore model when the initial state was empty."""

        output = self.run_scenario("zero-initial")
        self.assertIsNone(output["firstError"])
        self.assertEqual(output["trace"], [
            "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
            "callback:codex-bakeoff-abc123-meta-muse-glimmer",
            "unload:codex-bakeoff-abc123-meta-muse-glimmer",
        ])
        self.assertEqual(output["loaded"], [])
        self.assertFalse(output["journalExists"])
        self.assertFalse(output["lockExists"])

    def test_q8_profile_is_effective_only_as_gguf_kv_cache_quantization(self):
        """Catches a q8 profile that changes model quantization or omits GGUF safety fields."""

        output = self.run_scenario("q8-profile")
        self.assertIsNone(output["firstError"])
        self.assertEqual(output["callbackConfig"], {
            "contextLength": 32_768,
            "maxParallelPredictions": 1,
            "gpu": {"ratio": "max"},
            "flashAttention": True,
            "speculativeDraftMtp": False,
            "speculativeDraftSimple": False,
            "useFp16ForKVCache": True,
            "llamaKCacheQuantizationType": "q8_0",
            "llamaVCacheQuantizationType": "q8_0",
        })

    def test_mlx_profile_uses_only_backend_native_cache_controls(self):
        """Catches claiming Flash, GPU offload, or F16 KV controls for an MLX load."""

        output = self.run_scenario("mlx-profile")
        self.assertIsNone(output["firstError"])
        self.assertEqual(output["callbackConfig"], {
            "contextLength": 32_768,
            "maxParallelPredictions": 1,
            "mlxDiskCache": False,
            "mlxKvCacheQuantization": False,
        })
        for forbidden in ("gpu", "flashAttention", "useFp16ForKVCache"):
            self.assertNotIn(forbidden, output["callbackConfig"])

    def test_target_load_requires_projected_artifact_cache_and_runtime_headroom(self):
        """Catches a load gate that treats a percentage floor as enough for a large model."""

        output = self.run_scenario("insufficient-projected-headroom")
        self.assertIn("projected", output["firstError"]["message"].lower())
        self.assertNotIn(
            "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
            output["trace"],
        )
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertFalse(output["journalExists"])

    def test_swap_is_never_counted_as_physical_or_metal_load_capacity(self):
        """Catches a huge swap pool masking insufficient reclaimable physical memory."""

        output = self.run_scenario("insufficient-physical-huge-swap")
        self.assertIn("projected", output["firstError"]["message"].lower())
        self.assertNotIn(
            "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
            output["trace"],
        )
        self.assertEqual(output["loaded"], ["initial-model"])

    def test_initial_snapshot_relationship_is_validated_before_its_unload(self):
        """Catches capturing an unrestorable config/context pair and then unloading it."""

        output = self.run_scenario("initial-config-context-mismatch")
        self.assertIn("initial", output["firstError"]["message"].lower())
        self.assertEqual(output["trace"], [])
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertFalse(output["journalExists"])

    def test_effective_config_mismatch_is_never_guessed_owned_before_callback(self):
        """Catches unloading a config-mismatched instance without durable exact ownership."""

        output = self.run_scenario("effective-config-mismatch")
        self.assertIn("strict reviewed", output["firstError"]["message"].lower())
        self.assertNotIn("callback:codex-bakeoff-abc123-meta-muse-glimmer", output["trace"])
        self.assertIn("ownership", output["firstError"]["message"].lower())
        self.assertEqual(output["loaded"], ["codex-bakeoff-abc123-meta-muse-glimmer"])
        self.assertNotIn(
            "unload:codex-bakeoff-abc123-meta-muse-glimmer", output["trace"]
        )
        self.assertTrue(output["journalExists"])

    def test_initial_and_target_configs_reject_every_unreviewed_extra_key(self):
        """Catches subset validation accepting SDK-effective options outside the allowlist."""

        initial = self.run_scenario("initial-extra-config")
        self.assertIn("strict reviewed", initial["firstError"]["message"].lower())
        self.assertEqual(initial["trace"], [])
        self.assertEqual(initial["loaded"], ["initial-model"])

        target = self.run_scenario("target-extra-config")
        self.assertIn("strict reviewed", target["firstError"]["message"].lower())
        self.assertFalse(any(item.startswith("callback:") for item in target["trace"]))
        self.assertNotIn(
            "unload:codex-bakeoff-abc123-meta-muse-glimmer", target["trace"]
        )
        self.assertTrue(target["journalExists"])

    def test_callback_and_cleanup_failures_are_both_reported(self):
        """Catches a callback error masking the more urgent fact that restoration failed."""

        output = self.run_scenario("callback-and-cleanup-error")
        message = output["firstError"]["message"].lower()
        self.assertIn("callback interrupted", message)
        self.assertIn("owned unload interrupted", message)
        self.assertIn("recovery failure", message)
        self.assertEqual(output["loaded"], ["codex-bakeoff-abc123-meta-muse-glimmer"])
        self.assertTrue(output["journalExists"])

    def test_recovery_only_unloads_the_journal_owned_identifier_then_restores(self):
        """Catches recovery that uses unload-all or fails to resume after interrupted cleanup."""

        output = self.run_scenario("recover-owned")
        self.assertIn("owned unload interrupted", output["firstError"]["message"])
        self.assertTrue(output["recovery"])
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertFalse(output["journalExists"])
        self.assertFalse(output["lockExists"])
        self.assertEqual(output["trace"], [
            "unload:initial-model",
            "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
            "callback:codex-bakeoff-abc123-meta-muse-glimmer",
            "unload:codex-bakeoff-abc123-meta-muse-glimmer",
            "unload:codex-bakeoff-abc123-meta-muse-glimmer",
            "load:qwen/qwen3.8-27b@q4_k_m:initial-model",
        ])

    def test_recovery_refuses_an_unowned_loaded_identifier_without_unloading_it(self):
        """Catches recovery treating model-key similarity as proof of transaction ownership."""

        output = self.run_scenario("recover-unowned")
        self.assertIn("ownership", output["recovery"]["error"].lower())
        self.assertEqual(output["trace"], [
            "unload:initial-model",
            "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
            "callback:codex-bakeoff-abc123-meta-muse-glimmer",
            "unload:codex-bakeoff-abc123-meta-muse-glimmer",
        ])
        self.assertEqual(output["loaded"], ["unowned-model"])
        self.assertTrue(output["journalExists"])
        self.assertFalse(output["lockExists"])

    def test_recovery_never_unloads_a_same_name_replacement_instance_or_config(self):
        """Catches recovery treating model and identifier equality as ownership proof."""

        for scenario in ("recover-replaced-instance", "recover-replaced-config"):
            with self.subTest(scenario=scenario):
                output = self.run_scenario(scenario)
                self.assertIn("ownership", output["recovery"]["error"].lower())
                self.assertEqual(
                    output["trace"].count(
                        "unload:codex-bakeoff-abc123-meta-muse-glimmer"
                    ),
                    1,
                )
                self.assertEqual(
                    output["loaded"],
                    ["codex-bakeoff-abc123-meta-muse-glimmer"],
                )
                self.assertTrue(output["journalExists"])

    def test_recovery_validates_the_complete_initial_snapshot_before_model_mutation(self):
        """Catches malformed restored-state metadata being trusted after a valid digest."""

        for suffix in (
            "context",
            "variant",
            "indexed",
            "ttl",
            "device",
            "missing",
            "oversized-context",
        ):
            scenario = f"recover-malformed-initial-{suffix}"
            with self.subTest(scenario=scenario):
                output = self.run_scenario(scenario)
                self.assertIn("initial", output["recovery"]["error"].lower())
                self.assertEqual(
                    output["trace"].count(
                        "unload:codex-bakeoff-abc123-meta-muse-glimmer"
                    ),
                    1,
                )
                self.assertNotIn(
                    "load:qwen/qwen3.8-27b@q4_k_m:initial-model",
                    output["trace"],
                )
                self.assertEqual(
                    output["loaded"],
                    ["codex-bakeoff-abc123-meta-muse-glimmer"],
                )
                self.assertTrue(output["journalExists"])

    def test_recovery_restore_requires_projected_headroom_before_loading(self):
        """Catches crash recovery restoring a large model without post-load headroom."""

        output = self.run_scenario("recover-restore-insufficient-headroom")
        self.assertIn("projected", output["recovery"]["error"].lower())
        self.assertNotIn(
            "load:qwen/qwen3.8-27b@q4_k_m:initial-model",
            output["trace"],
        )
        self.assertEqual(output["loaded"], [])
        self.assertTrue(output["journalExists"])

    def test_recovery_terminates_a_positively_owned_callback_group_before_model_mutation(self):
        """Catches stale-lock recovery unloading while a crash-orphaned callback still runs."""

        output = self.run_scenario("recover-live-process-group")
        self.assertNotIn("error", output["recovery"])
        terminate_index = output["trace"].index("process-group-terminate:4242")
        recovered_unload_index = len(output["trace"]) - 2
        self.assertLess(terminate_index, recovered_unload_index)
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertFalse(output["journalExists"])
        self.assertFalse(output["lockExists"])

    def test_recovery_retains_exclusivity_for_an_ambiguous_callback_group(self):
        """Catches killing an unproven PID or mutating models while callback ownership is ambiguous."""

        output = self.run_scenario("recover-ambiguous-process-group")
        self.assertIn("unsettled", output["recovery"]["error"].lower())
        self.assertNotIn("process-group-terminate:4242", output["trace"])
        self.assertEqual(output["trace"].count(
            "unload:codex-bakeoff-abc123-meta-muse-glimmer"
        ), 1)
        self.assertEqual(output["loaded"], ["codex-bakeoff-abc123-meta-muse-glimmer"])
        self.assertTrue(output["journalExists"])
        self.assertTrue(output["lockExists"])

    def test_recovery_rejects_a_malformed_group_record_before_any_new_model_mutation(self):
        """Catches incomplete durable leader identity reaching probe, termination, or unload."""

        output = self.run_scenario("recover-malformed-process-group")
        self.assertIn("process-group", output["recovery"]["error"].lower())
        self.assertEqual(
            output["trace"].count(
                "unload:codex-bakeoff-abc123-meta-muse-glimmer"
            ),
            1,
        )
        self.assertFalse(any(item.startswith("process-group-") for item in output["trace"]))
        self.assertTrue(output["journalExists"])

    def test_pressure_gate_refuses_before_any_model_mutation(self):
        """Catches a low-memory run that starts unloading before validating host safety."""

        output = self.run_scenario("pressure")
        self.assertIn("free memory", output["firstError"]["message"].lower())
        self.assertEqual(output["trace"], [])
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertFalse(output["journalExists"])
        self.assertFalse(output["lockExists"])

    def test_initial_model_is_rechecked_idle_immediately_before_unload(self):
        """Catches unloading from a stale idle sample taken before fingerprint hashing."""

        output = self.run_scenario("busy-before-initial-unload")
        self.assertIn("idle", output["firstError"]["message"].lower())
        self.assertEqual(output["trace"], [])
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertFalse(output["journalExists"])

    def test_owned_model_is_rechecked_idle_immediately_before_cleanup_unload(self):
        """Catches interrupting work that became active after the benchmark callback returned."""

        output = self.run_scenario("busy-before-owned-unload")
        self.assertIn("idle", output["firstError"]["message"].lower())
        self.assertEqual(output["trace"], [
            "unload:initial-model",
            "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
            "callback:codex-bakeoff-abc123-meta-muse-glimmer",
        ])
        self.assertEqual(output["loaded"], ["codex-bakeoff-abc123-meta-muse-glimmer"])
        self.assertTrue(output["journalExists"])

    def test_mutation_boundary_directory_fsync_failure_issues_no_sdk_operation(self):
        """Catches issuing an unload before the pending-operation record is crash-durable."""

        output = self.run_scenario("mutation-boundary-directory-fsync-failure")
        self.assertIn("fsync mutation boundary interrupted", output["firstError"]["message"])
        self.assertEqual(output["trace"], [])
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertFalse(output["journalExists"])

    def test_post_load_pressure_gate_prevents_callback_and_restores(self):
        """Catches starting inference after model loading exhausts the host safety margin."""

        output = self.run_scenario("pressure-after-load")
        self.assertIn("free memory", output["firstError"]["message"].lower())
        self.assertEqual(output["trace"], [
            "unload:initial-model",
            "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
            "unload:codex-bakeoff-abc123-meta-muse-glimmer",
            "load:qwen/qwen3.8-27b@q4_k_m:initial-model",
        ])
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertFalse(output["journalExists"])
        self.assertFalse(output["lockExists"])

    def test_canonical_state_paths_refuse_symlink_parent_redirection(self):
        """Catches lock/journal redirection through a caller-selected symlink directory."""

        output = self.run_scenario("symlink-parent")
        self.assertIn("canonical", output["firstError"]["message"].lower())
        self.assertEqual(output["trace"], [])
        self.assertEqual(output["loaded"], ["initial-model"])

    def test_transaction_refuses_an_alternate_lock_path_before_mutation(self):
        """Catches two callers bypassing exclusivity by choosing different lock names."""

        output = self.run_scenario("alternate-lock-path")
        self.assertIn("canonical", output["firstError"]["message"].lower())
        self.assertEqual(output["trace"], [])
        self.assertEqual(output["loaded"], ["initial-model"])

    def test_load_deadline_aborts_load_and_restores_initial_model(self):
        """Catches unbounded loads and verifies the SDK AbortSignal is actually tripped."""

        output = self.run_scenario("load-timeout")
        self.assertIn("deadline", output["firstError"]["message"].lower())
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertFalse(output["journalExists"])
        self.assertEqual(output["trace"], [
            "unload:initial-model",
            "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
            "load:qwen/qwen3.8-27b@q4_k_m:initial-model",
        ])

    def test_unload_deadline_with_ambiguous_state_never_starts_a_load(self):
        """Catches racing a non-abortable timed-out unload with target or restore loading."""

        output = self.run_scenario("unload-timeout-ambiguous")
        self.assertIn("unsettled", output["firstError"]["message"].lower())
        self.assertEqual(output["trace"], ["unload:initial-model"])
        self.assertEqual(output["loaded"], ["unowned-model"])
        self.assertTrue(output["journalExists"])
        self.assertTrue(output["lockExists"])

    def test_owned_unload_timeout_retains_lock_and_never_starts_restore(self):
        """Catches explicit recovery racing a still-running owned-model unload."""

        output = self.run_scenario("owned-unload-timeout")
        self.assertIn("unsettled", output["firstError"]["message"].lower())
        self.assertEqual(output["trace"], [
            "unload:initial-model",
            "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
            "callback:codex-bakeoff-abc123-meta-muse-glimmer",
            "unload:codex-bakeoff-abc123-meta-muse-glimmer",
        ])
        self.assertEqual(output["loaded"], ["codex-bakeoff-abc123-meta-muse-glimmer"])
        self.assertTrue(output["journalExists"])
        self.assertTrue(output["lockExists"])

    def test_load_failure_with_created_instance_never_guesses_ownership(self):
        """Catches unloading an instance created by a rejected load without verified ownership."""

        output = self.run_scenario("load-error-created-owned-unload-timeout")
        self.assertIn("ownership", output["firstError"]["message"].lower())
        self.assertEqual(output["trace"], [
            "unload:initial-model",
            "load:meta/muse-glimmer@q4_k_m:codex-bakeoff-abc123-meta-muse-glimmer",
        ])
        self.assertEqual(output["loaded"], ["codex-bakeoff-abc123-meta-muse-glimmer"])
        self.assertTrue(output["journalExists"])
        self.assertFalse(output["lockExists"])

    def test_restore_load_timeout_retains_lock_for_explicit_stale_recovery(self):
        """Catches releasing exclusivity while an aborted restore load remains unsettled."""

        output = self.run_scenario("restore-load-timeout")
        self.assertIn("unsettled", output["firstError"]["message"].lower())
        self.assertEqual(output["loaded"], [])
        self.assertTrue(output["journalExists"])
        self.assertTrue(output["lockExists"])
        self.assertEqual(output["trace"][-2:], [
            "unload:codex-bakeoff-abc123-meta-muse-glimmer",
            "load:qwen/qwen3.8-27b@q4_k_m:initial-model",
        ])

    def test_stale_lock_recovery_refuses_a_durably_uncertain_sdk_operation(self):
        """Catches state samples being mistaken for completion of a late SDK operation."""

        output = self.run_scenario("recover-stale-lock")
        self.assertIn("unsettled", output["firstError"]["message"].lower())
        self.assertIn("crash-uncertain", output["recovery"]["error"].lower())
        self.assertEqual(output["loaded"], [])
        self.assertTrue(output["journalExists"])
        self.assertTrue(output["lockExists"])

    def test_recovery_removes_a_proven_pre_mutation_crash_journal(self):
        """Catches a crash before the first unload permanently wedging future runs."""

        output = self.run_scenario("recover-pre-mutation")
        self.assertNotIn("error", output["recovery"])
        self.assertEqual(output["trace"], [])
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertFalse(output["journalExists"])
        self.assertFalse(output["lockExists"])

    def test_recovery_owned_unload_timeout_retains_its_lock(self):
        """Catches a second recovery racing the first recovery's unsettled unload."""

        output = self.run_scenario("recovery-owned-unload-timeout")
        self.assertIn("unsettled", output["recovery"]["error"].lower())
        self.assertEqual(output["loaded"], ["codex-bakeoff-abc123-meta-muse-glimmer"])
        self.assertTrue(output["journalExists"])
        self.assertTrue(output["lockExists"])

    def test_recovery_restore_timeout_retains_its_lock(self):
        """Catches a second recovery racing the first recovery's unsettled restore load."""

        output = self.run_scenario("recovery-restore-timeout")
        self.assertIn("unsettled", output["recovery"]["error"].lower())
        self.assertEqual(output["loaded"], [])
        self.assertTrue(output["journalExists"])
        self.assertTrue(output["lockExists"])

    def test_artifact_fingerprint_change_fails_after_safe_cleanup_and_restore(self):
        """Catches accepting a model artifact identity that changes during the transaction."""

        output = self.run_scenario("artifact-change")
        self.assertIn("artifact fingerprint changed", output["firstError"]["message"].lower())
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertTrue(output["journalExists"])

    def test_reviewed_backend_binary_mismatch_refuses_before_model_mutation(self):
        """Catches accepting a backend that kept its advertised engine name and version."""

        output = self.run_scenario("backend-binary-mismatch")
        self.assertIn("runtime identity", output["firstError"]["message"].lower())
        self.assertEqual(output["trace"], [])
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertFalse(output["journalExists"])

    def test_inconsistent_artifact_quantization_bits_refuses_before_mutation(self):
        """Catches an exact alias whose SDK artifact metadata names a different quantization."""

        output = self.run_scenario("artifact-identity-mismatch")
        self.assertIn("artifact identity changed", output["firstError"]["message"].lower())
        self.assertEqual(output["trace"], [])
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertFalse(output["journalExists"])

    def test_runtime_helper_identity_change_fails_after_safe_restore(self):
        """Catches the harness or dependency identity changing during a benchmark run."""

        output = self.run_scenario("runtime-binding-change")
        self.assertIn("engine binding changed", output["firstError"]["message"].lower())
        self.assertEqual(output["loaded"], [])
        self.assertTrue(output["journalExists"])

    def test_journal_removal_failure_still_releases_lock_and_returns_audit(self):
        """Catches an unlink error bypassing the lock-finalization path."""

        output = self.run_scenario("journal-removal-failure")
        self.assertIn("journal unlink interrupted", output["firstError"]["message"].lower())
        self.assertIsNotNone(output["firstError"]["audit"])
        self.assertEqual(output["loaded"], ["initial-model"])
        self.assertTrue(output["journalExists"])
        self.assertFalse(output["lockExists"])


class ModelParkTests(unittest.TestCase):
    def run_scenario(self, scenario, timeout=20):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rows.json").write_text(json.dumps(MODEL_ROWS))
            completed = run_node(FAKE_PARK_RUNNER, root, scenario, timeout=timeout)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            return json.loads(completed.stdout)

    def test_park_unloads_only_the_exact_idle_candidate_under_low_memory_and_swap(self):
        """Catches reusing the load gate or restoring/loading anything during pressure relief."""

        output = self.run_scenario("success")
        self.assertIsNone(output["firstError"])
        self.assertEqual(output["loaded"], [])
        self.assertEqual(
            [item for item in output["trace"] if item.startswith(("unload:", "FORBIDDEN-LOAD"))],
            ["unload:parked-model"],
        )
        self.assertEqual(
            [item for item in output["trace"] if item.startswith("resource:")],
            ["resource:1", "resource:2"],
        )
        self.assertGreaterEqual(
            len([item for item in output["trace"] if item.startswith("processing:parked-model:")]),
            4,
        )
        self.assertEqual(output["result"]["kind"], "park")
        self.assertEqual(len(output["result"]["resource_samples"]), 2)
        self.assertFalse(output["journalExists"])
        self.assertFalse(output["lockExists"])

    def test_park_durably_binds_the_exact_snapshot_before_its_only_unload(self):
        """Catches a broad unload or an unload issued before ownership is durably recorded."""

        output = self.run_scenario("success")
        journal = output["pendingSeenAtUnload"]
        self.assertEqual(journal["kind"], "park")
        self.assertTrue(journal["mutation_started"])
        self.assertEqual(journal["operation_pending"], {
            "kind": "unload",
            "label": "park candidate unload",
            "identifier": "parked-model",
        })
        self.assertEqual(journal["park_snapshot"]["model_key"], "meta/muse-glimmer")
        self.assertEqual(journal["park_snapshot"]["selected_variant"], "meta/muse-glimmer@q4_k_m")
        self.assertEqual(journal["park_snapshot"]["instance_reference"], "instance-parked")
        self.assertIsNotNone(journal["artifact_fingerprints_pre"])
        self.assertIsNotNone(journal["engine_binding_pre"])

    def test_park_refuses_zero_multiple_changed_or_remote_models_without_mutation(self):
        """Catches treating an empty, ambiguous, changed, or remote model set as park-owned."""

        for scenario in ("zero-loaded", "multiple-loaded", "wrong-variant", "remote-model"):
            with self.subTest(scenario=scenario):
                output = self.run_scenario(scenario)
                self.assertIsNotNone(output["firstError"])
                self.assertFalse(any(item.startswith("unload:") for item in output["trace"]))
                self.assertNotIn("FORBIDDEN-LOAD", output["trace"])
                self.assertFalse(output["journalExists"])
                self.assertFalse(output["lockExists"])

    def test_park_revalidates_two_idle_samples_immediately_before_unload(self):
        """Catches unloading work that became active while artifact/runtime bindings were checked."""

        output = self.run_scenario("busy-before-unload")
        self.assertIn("idle", output["firstError"]["message"].lower())
        self.assertFalse(any(item.startswith("unload:") for item in output["trace"]))
        self.assertEqual(output["loaded"], ["parked-model"])
        self.assertFalse(output["journalExists"])
        self.assertFalse(output["lockExists"])

    def test_park_allows_low_memory_and_swap_but_not_throttled_pages(self):
        """Catches accidentally weakening non-memory identity/safety checks in the relief gate."""

        output = self.run_scenario("pages-throttled")
        self.assertIn("throttled", output["firstError"]["message"].lower())
        self.assertFalse(any(item.startswith("unload:") for item in output["trace"]))
        self.assertEqual(output["loaded"], ["parked-model"])
        self.assertFalse(output["journalExists"])
        self.assertFalse(output["lockExists"])

    def test_park_unload_timeout_retains_journal_and_lock_and_recovery_does_not_mutate(self):
        """Catches sampling through a crash-uncertain SDK unload or loading during recovery."""

        output = self.run_scenario("unload-timeout")
        self.assertIn("unsettled", output["firstError"]["message"].lower())
        self.assertEqual(
            [item for item in output["trace"] if item.startswith("unload:")],
            ["unload:parked-model"],
        )
        self.assertNotIn("FORBIDDEN-LOAD", output["trace"])
        self.assertIn("crash-uncertain", output["recovery"]["error"].lower())
        self.assertTrue(output["journalExists"])
        self.assertTrue(output["lockExists"])
        self.assertIsNotNone(output["journal"]["operation_pending"])

    def test_park_recovery_resolves_only_a_proven_zero_or_unchanged_snapshot(self):
        """Catches park recovery restoring or unloading a model instead of using observation only."""

        zero = self.run_scenario("recover-zero")
        self.assertIsNotNone(zero["firstError"])
        self.assertNotIn("error", zero["recovery"])
        self.assertEqual(zero["loaded"], [])
        self.assertFalse(zero["journalExists"])
        self.assertFalse(zero["lockExists"])
        self.assertNotIn("FORBIDDEN-LOAD", zero["trace"])
        self.assertEqual(
            [item for item in zero["trace"] if item.startswith("unload:")],
            ["unload:parked-model"],
        )

        unchanged = self.run_scenario("recover-no-mutation")
        self.assertIn("park unload rejected", unchanged["firstError"]["message"])
        self.assertNotIn("error", unchanged["recovery"])
        self.assertEqual(unchanged["loaded"], ["parked-model"])
        self.assertFalse(unchanged["journalExists"])
        self.assertFalse(unchanged["lockExists"])
        self.assertNotIn("FORBIDDEN-LOAD", unchanged["trace"])
        self.assertEqual(
            [item for item in unchanged["trace"] if item.startswith("unload:")],
            ["unload:parked-model"],
        )

    def test_park_recovery_refuses_unknown_state_without_loading_or_unloading(self):
        """Catches a recovery operation claiming ownership from only a similar model key."""

        output = self.run_scenario("recover-unknown")
        self.assertIn("unknown", output["recovery"]["error"].lower())
        self.assertEqual(output["loaded"], ["unknown-model"])
        self.assertTrue(output["journalExists"])
        self.assertFalse(output["lockExists"])
        self.assertNotIn("FORBIDDEN-LOAD", output["trace"])
        self.assertEqual(
            [item for item in output["trace"] if item.startswith("unload:")],
            ["unload:parked-model"],
        )

    def test_park_rechecks_artifact_binding_after_verified_zero(self):
        """Catches reporting success when the reviewed artifact identity changes during unload."""

        output = self.run_scenario("artifact-change")
        self.assertIn("artifact fingerprint changed", output["firstError"]["message"].lower())
        self.assertEqual(output["loaded"], [])
        self.assertTrue(output["journalExists"])
        self.assertFalse(output["lockExists"])
        self.assertNotIn("FORBIDDEN-LOAD", output["trace"])

    def test_park_does_not_report_success_if_a_model_appears_during_final_binding_checks(self):
        """Catches removing the journal after zero samples that became stale before finalization."""

        output = self.run_scenario("model-appears-after-zero")
        self.assertIsNotNone(output["firstError"])
        self.assertEqual(output["loaded"], ["late-model"])
        self.assertTrue(output["journalExists"])
        self.assertFalse(output["lockExists"])
        self.assertEqual(
            [item for item in output["trace"] if item.startswith("unload:")],
            ["unload:parked-model"],
        )


class CommandCallbackTests(unittest.TestCase):
    def test_command_callback_itself_enforces_the_two_hour_timeout_ceiling(self):
        """Catches direct command-callback construction bypassing CLI timeout validation."""

        runner = r"""
const lifecycle = require(process.argv[1]);
const messages = [];
for (const value of [0, 7200001, Number.MAX_SAFE_INTEGER]) {
  try {
    lifecycle.offlineTestDriver.commandCallback(["/usr/bin/true"], value);
    messages.push(null);
  } catch (error) { messages.push(error.message); }
}
const valid = typeof lifecycle.offlineTestDriver.commandCallback(["/usr/bin/true"], 7200000);
console.log(JSON.stringify({messages, valid}));
"""
        completed = run_node(runner)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(all("timeout" in message.lower() for message in result["messages"]))
        self.assertEqual(result["valid"], "function")

    def test_callback_environment_is_derived_from_the_verified_snapshot(self):
        """Catches ambient or callback-supplied values overriding exact model bindings."""

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "environment.json"
            snapshot = {
                "model_key": "meta/muse-glimmer",
                "identifier": "verified-owned-model",
                "indexed_model_identifier": "meta/muse-glimmer",
                "selected_variant": "meta/muse-glimmer@q4_k_m",
                "instance_reference": "verified-instance-reference",
                "device_identifier": None,
                "context_length": 65_536,
                "ttl_ms": None,
                "last_used_time": None,
                "load_config": {
                    "contextLength": 65_536,
                    "maxParallelPredictions": 1,
                    "gpu": {"ratio": "max"},
                    "flashAttention": True,
                },
                "processing_state": {"status": "idle", "queued": 0},
            }
            runner = r"""
const lifecycle = require(process.argv[1]);
const fs = require("node:fs");
const output = process.argv[2];
const snapshot = JSON.parse(process.argv[3]);
(async () => {
  await lifecycle.offlineTestDriver.commandCallback([
    process.execPath, "-e",
    `const fs=require("node:fs"); const values=Object.fromEntries(Object.entries(process.env).filter(([key])=>key.startsWith("LMSTUDIO_BAKEOFF_"))); fs.writeFileSync(${JSON.stringify(output)}, JSON.stringify(values));`,
  ], 500, 50, 20)({
    endpoint: "ws://127.0.0.1:1234",
    identifier: snapshot.identifier,
    modelKey: snapshot.model_key,
    selectedVariant: snapshot.selected_variant,
    profile: "f16",
    effectiveSnapshot: snapshot,
    snapshotSha256: "caller-controlled",
    instanceReference: "caller-controlled",
    indexedModelIdentifier: "caller-controlled",
    contextLength: 1,
    loadConfigSha256: "caller-controlled",
    signal: new AbortController().signal,
    registerProcessGroup() {},
    clearProcessGroup() {},
  });
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
            environment = os.environ.copy()
            for name in (
                "SNAPSHOT_SHA256", "INSTANCE_REFERENCE", "INDEXED_MODEL_IDENTIFIER",
                "CONTEXT_LENGTH", "LOAD_CONFIG_SHA256", "ENDPOINT",
                "SDK_ENTRY_PATH", "SDK_ENTRY_SHA256", "SDK_CLOSURE_SHA256",
                "SDK_DEPENDENCY_CLOSURE_SHA256",
            ):
                environment[f"LMSTUDIO_BAKEOFF_{name}"] = "ambient-controlled"
            completed = subprocess.run(
                [NODE_BINARY, "-e", runner, str(LIFECYCLE), str(output), json.dumps(snapshot)],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
                env=environment,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            values = json.loads(output.read_text())
            canonical = lambda value: json.dumps(
                value, sort_keys=True, separators=(",", ":")
            ).encode()
            self.assertEqual(values["LMSTUDIO_BAKEOFF_IDENTIFIER"], snapshot["identifier"])
            self.assertEqual(values["LMSTUDIO_BAKEOFF_MODEL_KEY"], snapshot["model_key"])
            self.assertEqual(
                values["LMSTUDIO_BAKEOFF_SELECTED_VARIANT"], snapshot["selected_variant"]
            )
            self.assertEqual(
                values["LMSTUDIO_BAKEOFF_SNAPSHOT_SHA256"],
                hashlib.sha256(canonical(snapshot)).hexdigest(),
            )
            self.assertEqual(
                values["LMSTUDIO_BAKEOFF_INSTANCE_REFERENCE"],
                snapshot["instance_reference"],
            )
            self.assertEqual(
                values["LMSTUDIO_BAKEOFF_INDEXED_MODEL_IDENTIFIER"],
                snapshot["indexed_model_identifier"],
            )
            self.assertEqual(
                values["LMSTUDIO_BAKEOFF_CONTEXT_LENGTH"],
                str(snapshot["context_length"]),
            )
            self.assertEqual(
                values["LMSTUDIO_BAKEOFF_LOAD_CONFIG_SHA256"],
                hashlib.sha256(canonical(snapshot["load_config"])).hexdigest(),
            )
            self.assertEqual(
                values["LMSTUDIO_BAKEOFF_ENDPOINT"], "ws://127.0.0.1:1234"
            )
            self.assertEqual(
                values["LMSTUDIO_BAKEOFF_SDK_ENTRY_PATH"],
                "/offline-test-only/@lmstudio/sdk/dist/index.cjs",
            )
            self.assertEqual(
                values["LMSTUDIO_BAKEOFF_SDK_ENTRY_SHA256"],
                "f657b4df6408212756deb8001bb66540c1072818879dc298740f9e05de237ef3",
            )
            self.assertEqual(
                values["LMSTUDIO_BAKEOFF_SDK_CLOSURE_SHA256"],
                "a5ca5d8499398a31eee23963b77c320594092698222fd6010ae5a56b5b925dcc",
            )
            self.assertEqual(
                values["LMSTUDIO_BAKEOFF_SDK_DEPENDENCY_CLOSURE_SHA256"],
                "8eb5d5bafa79d0f7ba2f341615b3faeb07fd4919116bd63aab8fd09503fdbe20",
            )
            self.assertFalse(any("contextLength" in value for value in values.values()))

    def test_callback_rejects_an_omitted_or_non_loopback_endpoint_before_child_start(self):
        """Catches callbacks guessing an API server or trusting ambient endpoint state."""

        runner = r"""
const lifecycle = require(process.argv[1]);
const base = {
  identifier: "verified-owned-model",
  modelKey: "meta/muse-glimmer",
  selectedVariant: "meta/muse-glimmer@q4_k_m",
  profile: "f16",
  effectiveSnapshot: {
    model_key: "meta/muse-glimmer",
    identifier: "verified-owned-model",
    indexed_model_identifier: "meta/muse-glimmer",
    selected_variant: "meta/muse-glimmer@q4_k_m",
    instance_reference: "verified-instance",
    device_identifier: null,
    context_length: 65536,
    ttl_ms: null,
    last_used_time: null,
    load_config: {contextLength: 65536},
    processing_state: {status: "idle", queued: 0},
  },
  registerProcessGroup() {},
  clearProcessGroup() {},
};
(async () => {
  const messages = [];
  for (const endpoint of [undefined, "ws://192.0.2.1:1234", "ws://localhost:1234"]) {
    try {
      await lifecycle.offlineTestDriver.commandCallback([process.execPath, "-e", "process.exit(99)"], 500, 50, 20)(
        {...base, endpoint}
      );
      messages.push(null);
    } catch (error) { messages.push(error.message); }
  }
  console.log(JSON.stringify(messages));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
        completed = subprocess.run(
            [NODE_BINARY, "-e", runner, str(LIFECYCLE)],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
            env={**os.environ, "LMSTUDIO_BAKEOFF_ENDPOINT": "ws://127.0.0.1:9999"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        messages = json.loads(completed.stdout)
        self.assertEqual(len(messages), 3)
        self.assertTrue(all("endpoint" in message.lower() for message in messages))

    def test_callback_rejects_identifiers_that_disagree_with_the_verified_snapshot(self):
        """Catches a caller substituting a different loaded-model identity before child start."""

        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "started"
            runner = r"""
const lifecycle = require(process.argv[1]);
const fs = require("node:fs");
const marker = process.argv[2];
(async () => {
  let message = null;
  try {
    await lifecycle.offlineTestDriver.commandCallback([
      process.execPath, "-e", `require("node:fs").writeFileSync(${JSON.stringify(marker)}, "yes")`,
    ], 500, 50, 20)({
      endpoint: "ws://127.0.0.1:1234",
      identifier: "caller-controlled",
      modelKey: "meta/muse-glimmer",
      selectedVariant: "meta/muse-glimmer@q4_k_m",
      profile: "f16",
      effectiveSnapshot: {
        model_key: "meta/muse-glimmer",
        identifier: "verified-owned-model",
        indexed_model_identifier: "meta/muse-glimmer",
        selected_variant: "meta/muse-glimmer@q4_k_m",
        instance_reference: "verified-instance",
        device_identifier: null,
        context_length: 65536,
        ttl_ms: null,
        last_used_time: null,
        load_config: {contextLength: 65536},
        processing_state: {status: "idle", queued: 0},
      },
      registerProcessGroup() {},
      clearProcessGroup() {},
    });
  } catch (error) { message = error.message; }
  console.log(JSON.stringify({message, markerExists: fs.existsSync(marker)}));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
            completed = subprocess.run(
                [NODE_BINARY, "-e", runner, str(LIFECYCLE), str(marker)],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertIn("verified snapshot", result["message"].lower())
            self.assertFalse(result["markerExists"])

    def test_production_probe_refuses_a_live_group_after_its_bound_leader_exits(self):
        """Catches a reused or leaderless same-UID PGID being treated as callback ownership."""

        runner = r"""
const {spawn} = require("node:child_process");
const {execFileSync} = require("node:child_process");
const fs = require("node:fs");
const lifecycle = require(process.argv[1]);
const token = "e".repeat(64);
(async () => {
  const leader = spawn(process.execPath, [
    "-e",
    "require('node:child_process').spawn('/bin/sleep',['30'],{stdio:'ignore'}).unref(); setTimeout(()=>{},100);",
  ], {detached: true, stdio: "ignore"});
  const pgid = leader.pid;
  await new Promise((resolve, reject) => {
    leader.once("error", reject);
    leader.once("spawn", resolve);
  });
  const output = execFileSync("/bin/ps", [
    "-p", String(pgid), "-o", "pid=,pgid=,uid=,lstart=,comm=",
  ], {encoding: "utf8", env: {PATH: "/usr/bin:/bin", LC_ALL: "C"}});
  const match = /^\s*([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([A-Z][a-z]{2} [A-Z][a-z]{2} [ 0-9][0-9] [0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4})\s+(.+?)\s*$/u.exec(output);
  const record = {
    leader_pid: pgid, pgid, uid: process.getuid(),
    leader_start_time: match[4], leader_executable: fs.realpathSync(match[5]), token,
  };
  await new Promise((resolve, reject) => {
    leader.once("exit", resolve);
  });
  const state = await lifecycle.productionProcessGroupProbe(record);
  try { process.kill(-pgid, "SIGKILL"); } catch (error) {
    if (error.code !== "ESRCH" && error.code !== "EPERM") throw error;
  }
  console.log(JSON.stringify(state));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
        completed = subprocess.run(
            [NODE_BINARY, "-e", runner, str(LIFECYCLE)],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {"alive": True, "owned": False})

    def test_production_probe_uses_private_receipt_without_token_in_process_arguments(self):
        """Catches ownership proof that leaks its private token through global process listings."""

        runner = r"""
const lifecycle = require(process.argv[1]);
const {execFileSync} = require("node:child_process");
const controller = new AbortController();
let record = null;
(async () => {
  const promise = lifecycle.offlineTestDriver.commandCallback(["/bin/sleep", "30"], 1000, 50, 20)({
    endpoint: "ws://127.0.0.1:1234",
    identifier: "owned", modelKey: "meta/muse-glimmer",
    selectedVariant: "meta/muse-glimmer@q4_k_m", profile: "f16",
    effectiveSnapshot: {model_key: "meta/muse-glimmer", identifier: "owned", indexed_model_identifier: "meta/muse-glimmer", selected_variant: "meta/muse-glimmer@q4_k_m", instance_reference: "instance-owned", device_identifier: null, context_length: 65536, ttl_ms: null, last_used_time: null, load_config: {contextLength: 65536}, processing_state: {status: "idle", queued: 0}},
    signal: controller.signal,
    registerProcessGroup(value) { record = value; },
    clearProcessGroup() {},
  });
  while (record === null) await new Promise(resolve => setTimeout(resolve, 1));
  const state = await lifecycle.productionProcessGroupProbe(record);
  const command = execFileSync("/bin/ps", ["-p", String(record.pgid), "-o", "command="], {
    encoding: "utf8",
  });
  controller.abort();
  try { await promise; } catch (_) {}
  console.log(JSON.stringify({state, commandContainsToken: command.includes(record.token)}));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
        completed = subprocess.run(
            [NODE_BINARY, "-e", runner, str(LIFECYCLE)],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["state"], {"alive": True, "owned": True})
        self.assertFalse(result["commandContainsToken"])

    def test_production_probe_rejects_malformed_and_reused_leader_identity(self):
        """Catches same-UID PID/PGID reuse or incomplete birth identity authorizing termination."""

        runner = r"""
const lifecycle = require(process.argv[1]);
const controller = new AbortController();
let record = null;
(async () => {
  const promise = lifecycle.offlineTestDriver.commandCallback(["/bin/sleep", "30"], 1000, 50, 20)({
    endpoint: "ws://127.0.0.1:1234",
    identifier: "owned", modelKey: "meta/muse-glimmer",
    selectedVariant: "meta/muse-glimmer@q4_k_m", profile: "f16",
    effectiveSnapshot: {model_key: "meta/muse-glimmer", identifier: "owned", indexed_model_identifier: "meta/muse-glimmer", selected_variant: "meta/muse-glimmer@q4_k_m", instance_reference: "instance-owned", device_identifier: null, context_length: 65536, ttl_ms: null, last_used_time: null, load_config: {contextLength: 65536}, processing_state: {status: "idle", queued: 0}},
    signal: controller.signal,
    registerProcessGroup(value) { record = value; },
    clearProcessGroup() {},
  });
  while (record === null) await new Promise(resolve => setTimeout(resolve, 1));
  const reused = await lifecycle.productionProcessGroupProbe({
    ...record,
    leader_start_time: record.leader_start_time.replace(/[0-9]{4}$/u, "1999"),
  });
  let malformed = null;
  try {
    await lifecycle.productionProcessGroupProbe({
      pgid: record.pgid, uid: record.uid, token: record.token,
    });
  } catch (error) { malformed = error.message; }
  controller.abort();
  try { await promise; } catch (_) {}
  console.log(JSON.stringify({reused, malformed}));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
        completed = subprocess.run(
            [NODE_BINARY, "-e", runner, str(LIFECYCLE)],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["reused"], {"alive": True, "owned": False})
        self.assertIn("invalid", result["malformed"].lower())

    def test_registration_failure_keeps_the_gated_callback_from_starting(self):
        """Catches a hard-crash window between child spawn and durable group ownership."""

        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "started"
            runner = r"""
const fs = require("node:fs");
const lifecycle = require(process.argv[1]);
const marker = process.argv[2];
(async () => {
  let message = null;
  try {
    await lifecycle.offlineTestDriver.commandCallback([
      process.execPath, "-e", `require("node:fs").writeFileSync(${JSON.stringify(marker)}, "yes")`,
    ], 500, 50, 20)({
      endpoint: "ws://127.0.0.1:1234",
      identifier: "owned", modelKey: "meta/muse-glimmer",
      selectedVariant: "meta/muse-glimmer@q4_k_m", profile: "f16",
      effectiveSnapshot: {model_key: "meta/muse-glimmer", identifier: "owned", indexed_model_identifier: "meta/muse-glimmer", selected_variant: "meta/muse-glimmer@q4_k_m", instance_reference: "instance-owned", device_identifier: null, context_length: 65536, ttl_ms: null, last_used_time: null, load_config: {contextLength: 65536}, processing_state: {status: "idle", queued: 0}},
      signal: new AbortController().signal,
      registerProcessGroup() { throw new Error("journal registration failed"); },
      clearProcessGroup() {},
    });
  } catch (error) { message = error.message; }
  await new Promise(resolve => setTimeout(resolve, 75));
  console.log(JSON.stringify({message, markerExists: fs.existsSync(marker)}));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
            completed = subprocess.run(
                [NODE_BINARY, "-e", runner, str(LIFECYCLE), str(marker)],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertIn("journal registration failed", result["message"])
            self.assertFalse(result["markerExists"])

    def test_process_group_is_registered_before_callback_and_cleared_after_quiescence(self):
        """Catches callback execution without a durable recovery-owned process-group record."""

        runner = r"""
const lifecycle = require(process.argv[1]);
const events = [];
(async () => {
  await lifecycle.offlineTestDriver.commandCallback([process.execPath, "-e", "process.exit(0)"], 500, 50, 20)({
    endpoint: "ws://127.0.0.1:1234",
    identifier: "owned", modelKey: "meta/muse-glimmer",
    selectedVariant: "meta/muse-glimmer@q4_k_m", profile: "f16",
    effectiveSnapshot: {model_key: "meta/muse-glimmer", identifier: "owned", indexed_model_identifier: "meta/muse-glimmer", selected_variant: "meta/muse-glimmer@q4_k_m", instance_reference: "instance-owned", device_identifier: null, context_length: 65536, ttl_ms: null, last_used_time: null, load_config: {contextLength: 65536}, processing_state: {status: "idle", queued: 0}},
    signal: new AbortController().signal,
    registerProcessGroup(record) { events.push(["register", record]); },
    clearProcessGroup(record) { events.push(["clear", record]); },
  });
  console.log(JSON.stringify(events));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
        completed = subprocess.run(
            [NODE_BINARY, "-e", runner, str(LIFECYCLE)],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        events = json.loads(completed.stdout)
        self.assertEqual([event[0] for event in events], ["register", "clear"])
        self.assertEqual(events[0][1], events[1][1])
        self.assertGreater(events[0][1]["pgid"], 0)
        self.assertEqual(events[0][1]["leader_pid"], events[0][1]["pgid"])
        self.assertGreaterEqual(events[0][1]["uid"], 0)
        self.assertRegex(
            events[0][1]["leader_start_time"],
            r"^[A-Z][a-z]{2} [A-Z][a-z]{2} [ 0-9][0-9] "
            r"[0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4}$",
        )
        self.assertTrue(Path(events[0][1]["leader_executable"]).is_absolute())
        self.assertRegex(events[0][1]["token"], r"^[0-9a-f]{64}$")

    def test_fast_exit_does_not_reschedule_an_in_flight_resource_probe(self):
        """Catches a completed callback leaking a new monitor timer after probe resolution."""

        runner = r"""
const lifecycle = require(process.argv[1]);
let started = 0;
let completed = 0;
let record = null;
let cleared = false;
let notifyProbeStarted;
let releaseProbe;
const probeStarted = new Promise(resolve => { notifyProbeStarted = resolve; });
const probeRelease = new Promise(resolve => { releaseProbe = resolve; });
(async () => {
  const callback = lifecycle.offlineTestDriver.commandCallback(["/bin/sleep", "30"], 1000, 50, 1)({
    endpoint: "ws://127.0.0.1:1234",
    identifier: "owned", modelKey: "meta/muse-glimmer",
    selectedVariant: "meta/muse-glimmer@q4_k_m", profile: "f16",
    effectiveSnapshot: {model_key: "meta/muse-glimmer", identifier: "owned", indexed_model_identifier: "meta/muse-glimmer", selected_variant: "meta/muse-glimmer@q4_k_m", instance_reference: "instance-owned", device_identifier: null, context_length: 65536, ttl_ms: null, last_used_time: null, load_config: {contextLength: 65536}, processing_state: {status: "idle", queued: 0}},
    signal: new AbortController().signal,
    registerProcessGroup(value) { record = value; },
    clearProcessGroup() { cleared = true; },
    resourceProbe: async () => {
      started += 1;
      notifyProbeStarted();
      await probeRelease;
      completed += 1;
      return {
        free_memory_percent: 40, swap_free_bytes: 3 * 1024 * 1024 * 1024,
        pages_throttled: 0, load_1m: 2, logical_cpus: 18,
      };
    },
  });
  await probeStarted;
  process.kill(-record.pgid, "SIGTERM");
  let callbackMessage = null;
  try { await callback; } catch (error) { callbackMessage = error.message; }
  const startedAtTermination = started;
  const completedAtTermination = completed;
  releaseProbe();
  await new Promise(resolve => setTimeout(resolve, 30));
  console.log(JSON.stringify({
    callbackMessage, cleared,
    startedAtTermination, completedAtTermination,
    startedAfterRelease: started,
    completedAfterRelease: completed,
  }));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
        completed = subprocess.run(
            [NODE_BINARY, "-e", runner, str(LIFECYCLE)],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["cleared"])
        self.assertIsNotNone(result["callbackMessage"])
        self.assertGreaterEqual(result["startedAtTermination"], 1)
        self.assertEqual(result["completedAtTermination"], 0)
        self.assertEqual(
            result["startedAfterRelease"], result["startedAtTermination"]
        )
        self.assertEqual(
            result["completedAfterRelease"], result["startedAtTermination"]
        )

    def test_mid_callback_pressure_breach_terminates_owned_workload(self):
        """Catches KV/prompt growth crossing safety limits only after inference starts."""

        runner = r"""
const lifecycle = require(process.argv[1]);
let samples = 0;
(async () => {
  const started = Date.now();
  let message = null;
  try {
    await lifecycle.offlineTestDriver.commandCallback(["/bin/sleep", "30"], 500, 50, 20)({
      endpoint: "ws://127.0.0.1:1234",
      identifier: "owned", modelKey: "meta/muse-glimmer",
      selectedVariant: "meta/muse-glimmer@q4_k_m", profile: "f16",
      effectiveSnapshot: {model_key: "meta/muse-glimmer", identifier: "owned", indexed_model_identifier: "meta/muse-glimmer", selected_variant: "meta/muse-glimmer@q4_k_m", instance_reference: "instance-owned", device_identifier: null, context_length: 65536, ttl_ms: null, last_used_time: null, load_config: {contextLength: 65536}, processing_state: {status: "idle", queued: 0}},
      signal: new AbortController().signal,
      resourceProbe: async () => ({
        free_memory_percent: ++samples < 2 ? 40 : 5,
        swap_free_bytes: 3 * 1024 * 1024 * 1024,
        pages_throttled: 0, load_1m: 2, logical_cpus: 18,
      }),
    });
  } catch (error) { message = error.message; }
  console.log(JSON.stringify({message, samples, elapsed: Date.now() - started}));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
        completed = subprocess.run(
            [NODE_BINARY, "-e", runner, str(LIFECYCLE)],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertIn("free memory", result["message"].lower())
        self.assertGreaterEqual(result["samples"], 2)
        self.assertLess(result["elapsed"], 500)

    def test_timeout_kills_owned_process_group_and_waits_for_exit(self):
        """Catches lifecycle cleanup racing a benchmark child or descendant still using LM Studio."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pid_file = root / "grandchild.pid"
            child = root / "callback-child.cjs"
            child.write_text(textwrap.dedent(f"""\
                const fs = require("node:fs");
                const {{spawn}} = require("node:child_process");
                const grandchild = spawn("/bin/sleep", ["30"], {{stdio: "ignore"}});
                fs.writeFileSync({json.dumps(str(pid_file))}, String(grandchild.pid));
                process.on("SIGTERM", () => {{}});
                setInterval(() => {{}}, 1000);
            """))
            runner = r"""
const fs = require("node:fs");
const lifecycle = require(process.argv[1]);
const child = process.argv[2];
const pidFile = process.argv[3];
(async () => {
  const started = Date.now();
  let message = null;
  try {
    await lifecycle.offlineTestDriver.commandCallback([process.execPath, child], 50, 100)({
      endpoint: "ws://127.0.0.1:1234",
      identifier: "owned", modelKey: "meta/muse-glimmer",
      selectedVariant: "meta/muse-glimmer@q4_k_m", profile: "f16",
      effectiveSnapshot: {model_key: "meta/muse-glimmer", identifier: "owned", indexed_model_identifier: "meta/muse-glimmer", selected_variant: "meta/muse-glimmer@q4_k_m", instance_reference: "instance-owned", device_identifier: null, context_length: 65536, ttl_ms: null, last_used_time: null, load_config: {contextLength: 65536}, processing_state: {status: "idle", queued: 0}},
      signal: new AbortController().signal,
    });
  } catch (error) { message = error.message; }
  const pid = fs.existsSync(pidFile) ? Number(fs.readFileSync(pidFile, "utf8")) : null;
  let alive = pid !== null;
  for (let attempt = 0; attempt < 20 && alive; attempt += 1) {
    try { process.kill(pid, 0); } catch (error) { if (error.code === "ESRCH") alive = false; }
    if (alive) await new Promise(resolve => setTimeout(resolve, 25));
  }
  console.log(JSON.stringify({message, alive, elapsed: Date.now() - started}));
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
"""
            completed = subprocess.run(
                [NODE_BINARY, "-e", runner, str(LIFECYCLE), str(child), str(pid_file)],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertIn("deadline", result["message"].lower())
            self.assertFalse(result["alive"])
            self.assertGreaterEqual(result["elapsed"], 50)


if __name__ == "__main__":
    unittest.main()
