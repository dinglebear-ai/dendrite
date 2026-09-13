#!/usr/bin/env node
// Runs one explicitly authorized, locally bound LM Studio model transaction, or
// parks one exact reviewed candidate through an unload-only pressure-relief path.
// The default plan path is read-only.
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createRequire } = require("node:module");
const { spawn, execFileSync } = require("node:child_process");

const JOURNAL_SCHEMA_VERSION = 2;
const CONTEXT_LENGTH = 32_768;
const MAX_PACKET_INPUT_TOKENS = 20_480;
const MAX_PACKET_OUTPUT_TOKENS = 8_192;
const CONTEXT_RUNTIME_RESERVE_TOKENS = 4_096;
const RUNTIME_HEADROOM_BYTES = 4 * 1024 * 1024 * 1024;
const MIN_FREE_MEMORY_PERCENT = 30;
const MIN_SWAP_FREE_BYTES = 2 * 1024 * 1024 * 1024;
const DEFAULT_IDLE_SAMPLE_DELAY_MS = 1_000;
const DEFAULT_LOAD_TIMEOUT_MS = 10 * 60 * 1_000;
const DEFAULT_UNLOAD_TIMEOUT_MS = 2 * 60 * 1_000;
const DEFAULT_CALLBACK_TIMEOUT_MS = 20 * 60 * 1_000;
const MAX_CALLBACK_TIMEOUT_MS = 2 * 60 * 60 * 1_000;
const DEADLINE_SETTLE_GRACE_MS = 2_000;
const CALLBACK_SUPERVISOR_EXECUTABLE = fs.realpathSync(process.execPath);

const MODEL_SPECS = Object.freeze({
  "qwen/qwen3.6-35b-a3b": Object.freeze({
    modelKey: "qwen/qwen3.6-35b-a3b",
    selectedVariant: "qwen/qwen3.6-35b-a3b@4bit",
    format: "safetensors", quantization: "4bit", quantizationBits: 4,
    path: "qwen/qwen3.6-35b-a3b", indexedModelIdentifier: "qwen/qwen3.6-35b-a3b", backend: "MLX",
    artifactSizeBytes: 20_429_364_306,
    maxContextLength: 262_144,
  }),
  "meta/muse-glimmer": Object.freeze({
    modelKey: "meta/muse-glimmer",
    selectedVariant: "meta/muse-glimmer@q4_k_m",
    format: "gguf", quantization: "Q4_K_M", quantizationBits: 4,
    path: "meta/muse-glimmer", indexedModelIdentifier: "meta/muse-glimmer", backend: "GGUF",
    artifactSizeBytes: 18_157_122_004,
    maxContextLength: 131_072,
  }),
  "google/gemma-4-31b": Object.freeze({
    modelKey: "google/gemma-4-31b",
    selectedVariant: "google/gemma-4-31b@4bit",
    format: "safetensors", quantization: "4bit", quantizationBits: 4,
    path: "google/gemma-4-31b", indexedModelIdentifier: "google/gemma-4-31b", backend: "MLX",
    artifactSizeBytes: 18_444_515_810,
    maxContextLength: 262_144,
  }),
  "google/gemma-4-26b-a4b-qat": Object.freeze({
    modelKey: "google/gemma-4-26b-a4b-qat",
    selectedVariant: "google/gemma-4-26b-a4b-qat@4bit",
    format: "safetensors", quantization: "4bit", quantizationBits: 4,
    path: "google/gemma-4-26b-a4b-qat",
    indexedModelIdentifier: "google/gemma-4-26b-a4b-qat", backend: "MLX",
    artifactSizeBytes: 15_641_333_028,
    maxContextLength: 262_144,
  }),
  "qwen/qwen3.8-27b": Object.freeze({
    modelKey: "qwen/qwen3.8-27b",
    selectedVariant: "qwen/qwen3.8-27b@q4_k_m",
    format: "gguf", quantization: "Q4_K_M", quantizationBits: 4,
    path: "qwen/qwen3.8-27b", indexedModelIdentifier: "qwen/qwen3.8-27b", backend: "GGUF",
    artifactSizeBytes: 17_742_040_464,
    maxContextLength: 262_144,
  }),
});

if (MAX_PACKET_INPUT_TOKENS + MAX_PACKET_OUTPUT_TOKENS + CONTEXT_RUNTIME_RESERVE_TOKENS
    !== CONTEXT_LENGTH) {
  throw new Error("the fixed packet envelope must exactly fit the served context");
}

// Conservative KV-cache projections are derived from the reviewed local model
// metadata. Full-attention models reserve every layer for the served context;
// Gemma's hybrid models reserve their full-attention layers plus every sliding
// layer at its complete 1,024-token window. The independent 4 GiB runtime
// reserve covers allocator/backend working memory and preserves OS headroom.
const KV_CACHE_PROJECTIONS = Object.freeze({
  "qwen/qwen3.6-35b-a3b": Object.freeze({
    fullLayers: 40, slidingLayers: 0, slidingWindow: 0, kvHeads: 2, headDim: 256,
  }),
  "meta/muse-glimmer": Object.freeze({
    fullLayers: 52, slidingLayers: 0, slidingWindow: 0, kvHeads: 2, headDim: 128,
  }),
  "google/gemma-4-31b": Object.freeze({
    fullLayers: 10, slidingLayers: 50, slidingWindow: 1_024, kvHeads: 4, headDim: 512,
  }),
  "google/gemma-4-26b-a4b-qat": Object.freeze({
    fullLayers: 5, slidingLayers: 25, slidingWindow: 1_024, kvHeads: 2, headDim: 512,
  }),
  "qwen/qwen3.8-27b": Object.freeze({
    fullLayers: 65, slidingLayers: 0, slidingWindow: 0, kvHeads: 4, headDim: 256,
  }),
});

const REVIEWED_ENGINES = Object.freeze({
  GGUF: Object.freeze({
    name: "llama.cpp-mac-arm64-apple-metal-advsimd", version: "2.31.2",
    primaryFile: "libllama-common.0.3.0.dylib",
    primarySha256: "cb2af513d90ce7913605138089d0c85a941ca57b625e84798473672f76981549",
    manifestSha256: "55f5f12ebb829498bceb5c1d73b3831d5c9d3a102426fd64887c8e97cbba6d80",
    closureSha256: "080991a78008280a043d27b908f4d0264240dd935736d74258d4c9ab757e4629",
  }),
  MLX: Object.freeze({
    name: "mlx-llm-mac-arm64-apple-metal-nax-advsimd", version: "1.11.0",
    primaryFile: "libllm_engine.dylib",
    primarySha256: "0f5cd7c2f2253d6f1648c1809c63c556c14d0d94061af68e4ba3477a53d986cb",
    manifestSha256: "39f21df46847eb9e05f542db597027fe585d829d2d12ed7fe909bf3b0f3eace2",
    closureSha256: "b81597a447b38ba61b5cb17c7e2336a4e7cafc9e90506adc629154a5b2a75783",
  }),
});

const REVIEWED_SDK = Object.freeze({
  name: "@lmstudio/sdk",
  version: "1.5.0",
  entrySha256: "f657b4df6408212756deb8001bb66540c1072818879dc298740f9e05de237ef3",
  closureSha256: "a5ca5d8499398a31eee23963b77c320594092698222fd6010ae5a56b5b925dcc",
  dependencyClosureSha256: "8eb5d5bafa79d0f7ba2f341615b3faeb07fd4919116bd63aab8fd09503fdbe20",
});
const CLIENT_SDK_RECEIPTS = new WeakMap();
const CLIENT_ENDPOINT_RECEIPTS = new WeakMap();
const PRODUCTION_CLIENTS = new WeakSet();
const OFFLINE_TEST_RUNTIME_IDENTITIES = new WeakMap();
const CALLBACK_CONTEXT_SDK_BINDINGS = new WeakMap();

const OFFLINE_TEST_SDK_RECEIPT = Object.freeze({
  entryPath: "/offline-test-only/@lmstudio/sdk/dist/index.cjs",
  entrySha256: REVIEWED_SDK.entrySha256,
  closureSha256: REVIEWED_SDK.closureSha256,
  dependencyClosureSha256: REVIEWED_SDK.dependencyClosureSha256,
});

class LifecycleError extends Error {
  constructor(message, options = {}) {
    super(message, options);
    this.name = "LifecycleError";
    this.lifecycleAudit = null;
  }
}

class OperationDeadlineError extends LifecycleError {
  constructor(message, operationSettled) {
    super(message);
    this.operationSettled = operationSettled;
    this.name = "OperationDeadlineError";
  }
}

class OperationUncertainError extends LifecycleError {
  constructor(message, options = {}) {
    super(message, options);
    this.operationUncertain = true;
    this.name = "OperationUncertainError";
  }
}

function requirePlainObject(value, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new LifecycleError(`${label} must be an object`);
  }
  return value;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function sortValue(value) {
  if (Array.isArray(value)) return value.map(sortValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, sortValue(value[key])]));
  }
  return value;
}

function canonicalJson(value) {
  return JSON.stringify(sortValue(value));
}

function canonicalSha256(value) {
  return crypto.createHash("sha256").update(canonicalJson(value)).digest("hex");
}

function assertSha256(value, label) {
  if (typeof value !== "string" || !/^[0-9a-f]{64}$/u.test(value)) {
    throw new LifecycleError(`${label} is not a lowercase SHA-256 digest`);
  }
}

function sha256File(file) {
  return new Promise((resolve, reject) => {
    const digest = crypto.createHash("sha256");
    const stream = fs.createReadStream(file);
    stream.once("error", reject);
    stream.on("data", chunk => digest.update(chunk));
    stream.once("end", () => resolve(digest.digest("hex")));
  });
}

async function fingerprintTree(root) {
  const rootStat = fs.lstatSync(root);
  if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) {
    throw new LifecycleError("runtime dependency root must be a non-symlink directory");
  }
  const rows = [];
  const walk = async directory => {
    const entries = fs.readdirSync(directory, { withFileTypes: true })
      .sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      const file = path.join(directory, entry.name);
      const relative = path.relative(root, file);
      if (entry.isDirectory()) {
        await walk(file);
      } else if (entry.isFile()) {
        const statValue = fs.lstatSync(file);
        rows.push({
          kind: "file", path: relative, size_bytes: statValue.size,
          sha256: await sha256File(file),
        });
      } else if (entry.isSymbolicLink()) {
        const target = fs.readlinkSync(file);
        const resolved = path.resolve(path.dirname(file), target);
        if (resolved !== root && !resolved.startsWith(`${root}${path.sep}`)) {
          throw new LifecycleError("runtime dependency symlink escapes its reviewed root");
        }
        rows.push({ kind: "symlink", path: relative, target });
      } else {
        throw new LifecycleError("runtime dependency tree contains an unsupported entry");
      }
    }
  };
  await walk(root);
  return { files: rows, sha256: canonicalSha256(rows) };
}

function sha256FileSync(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function sha256DescriptorSync(descriptor) {
  const digest = crypto.createHash("sha256");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  let position = 0;
  while (true) {
    const count = fs.readSync(descriptor, buffer, 0, buffer.length, position);
    if (count === 0) break;
    digest.update(buffer.subarray(0, count));
    position += count;
  }
  return digest.digest("hex");
}

function immutableFileIdentity(statValue) {
  return {
    device: String(statValue.dev),
    inode: String(statValue.ino),
    size: String(statValue.size),
    mode: String(statValue.mode),
    mtime_ns: String(statValue.mtimeNs),
    ctime_ns: String(statValue.ctimeNs),
  };
}

function fingerprintTreeSync(root) {
  const rootStat = fs.lstatSync(root);
  if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) {
    throw new LifecycleError("SDK dependency root must be a non-symlink directory");
  }
  const rows = [];
  const walk = directory => {
    const entries = fs.readdirSync(directory, { withFileTypes: true })
      .sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      const file = path.join(directory, entry.name);
      const relative = path.relative(root, file);
      if (entry.isDirectory()) {
        walk(file);
      } else if (entry.isFile()) {
        const statValue = fs.lstatSync(file);
        rows.push({
          kind: "file", path: relative, size_bytes: statValue.size,
          sha256: sha256FileSync(file),
        });
      } else if (entry.isSymbolicLink()) {
        const target = fs.readlinkSync(file);
        const resolved = path.resolve(path.dirname(file), target);
        if (resolved !== root && !resolved.startsWith(`${root}${path.sep}`)) {
          throw new LifecycleError("SDK dependency symlink escapes its reviewed root");
        }
        rows.push({ kind: "symlink", path: relative, target });
      } else {
        throw new LifecycleError("SDK dependency tree contains an unsupported entry");
      }
    }
  };
  walk(root);
  return { files: rows, sha256: canonicalSha256(rows) };
}

function verifyReviewedSdkEntry(sdkEntry) {
  const entry = fs.realpathSync(sdkEntry);
  const flags = fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0);
  let descriptor;
  try {
    descriptor = fs.openSync(entry, flags);
    const descriptorIdentity = immutableFileIdentity(fs.fstatSync(descriptor, { bigint: true }));
    const pathIdentity = immutableFileIdentity(fs.lstatSync(entry, { bigint: true }));
    if (!equalCanonical(descriptorIdentity, pathIdentity)) {
      throw new LifecycleError("LM Studio SDK entry changed while it was opened");
    }
    const sdkRoot = path.dirname(path.dirname(entry));
    const metadata = requirePlainObject(
      JSON.parse(fs.readFileSync(path.join(sdkRoot, "package.json"), "utf8")),
      "LM Studio SDK package metadata",
    );
    const firstEntrySha256 = sha256DescriptorSync(descriptor);
    const firstClosureSha256 = fingerprintTreeSync(sdkRoot).sha256;
    const firstDependencyClosureSha256 = fingerprintSdkDependencyClosure(sdkRoot).sha256;
    const secondEntrySha256 = sha256DescriptorSync(descriptor);
    const secondClosureSha256 = fingerprintTreeSync(sdkRoot).sha256;
    const secondDependencyClosureSha256 = fingerprintSdkDependencyClosure(sdkRoot).sha256;
    const finalDescriptorIdentity = immutableFileIdentity(
      fs.fstatSync(descriptor, { bigint: true }),
    );
    const finalPathIdentity = immutableFileIdentity(fs.lstatSync(entry, { bigint: true }));
    if (!equalCanonical(descriptorIdentity, finalDescriptorIdentity)
        || !equalCanonical(descriptorIdentity, finalPathIdentity)
        || firstEntrySha256 !== secondEntrySha256
        || firstClosureSha256 !== secondClosureSha256
        || firstDependencyClosureSha256 !== secondDependencyClosureSha256
        || metadata.name !== REVIEWED_SDK.name || metadata.version !== REVIEWED_SDK.version
        || secondEntrySha256 !== REVIEWED_SDK.entrySha256
        || secondClosureSha256 !== REVIEWED_SDK.closureSha256
        || secondDependencyClosureSha256 !== REVIEWED_SDK.dependencyClosureSha256) {
      throw new LifecycleError(
        "installed LM Studio SDK entry or dependency closure differs from the reviewed SDK build",
      );
    }
    return Object.freeze({
      entryPath: entry,
      entrySha256: secondEntrySha256,
      closureSha256: secondClosureSha256,
      dependencyClosureSha256: secondDependencyClosureSha256,
      fileIdentity: Object.freeze(finalDescriptorIdentity),
    });
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
  }
}

function packageRootForResolvedEntry(entry, expectedName) {
  let directory = fs.lstatSync(entry).isDirectory() ? entry : path.dirname(entry);
  while (true) {
    const metadataPath = path.join(directory, "package.json");
    if (fs.existsSync(metadataPath)) {
      const metadata = requirePlainObject(
        JSON.parse(fs.readFileSync(metadataPath, "utf8")),
        "SDK dependency package metadata",
      );
      if (metadata.name === expectedName) return fs.realpathSync(directory);
    }
    const parent = path.dirname(directory);
    if (parent === directory) break;
    directory = parent;
  }
  throw new LifecycleError(`could not bind SDK dependency package root for ${expectedName}`);
}

function fingerprintSdkDependencyClosure(sdkRoot) {
  const queue = [fs.realpathSync(sdkRoot)];
  const packages = new Map();
  const rawEdges = [];
  while (queue.length > 0) {
    const root = fs.realpathSync(queue.shift());
    if (packages.has(root)) continue;
    const metadata = requirePlainObject(
      JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8")),
      "SDK dependency package metadata",
    );
    if (typeof metadata.name !== "string" || !metadata.name
        || typeof metadata.version !== "string" || !metadata.version) {
      throw new LifecycleError("SDK dependency package name or version is invalid");
    }
    const tree = fingerprintTreeSync(root);
    const id = `${metadata.name}@${metadata.version}:${tree.sha256}`;
    packages.set(root, {
      id, name: metadata.name, version: metadata.version, tree_sha256: tree.sha256,
    });
    const dependencyKinds = new Map();
    for (const dependency of Object.keys(metadata.dependencies || {})) {
      dependencyKinds.set(dependency, "required");
    }
    for (const dependency of Object.keys(metadata.optionalDependencies || {})) {
      dependencyKinds.set(dependency, "optional");
    }
    for (const dependency of Object.keys(metadata.peerDependencies || {})) {
      if (!dependencyKinds.has(dependency)) {
        dependencyKinds.set(
          dependency,
          metadata.peerDependenciesMeta?.[dependency]?.optional ? "optional" : "required",
        );
      }
    }
    const resolver = createRequire(path.join(root, "package.json"));
    for (const dependency of [...dependencyKinds.keys()].sort()) {
      let resolved;
      try {
        resolved = resolver.resolve(dependency);
      } catch (error) {
        if (dependencyKinds.get(dependency) === "optional") continue;
        throw new LifecycleError(`required SDK dependency is unavailable: ${dependency}`, {
          cause: error,
        });
      }
      const childRoot = packageRootForResolvedEntry(resolved, dependency);
      queue.push(childRoot);
      rawEdges.push({ from_root: root, dependency, to_root: childRoot });
    }
  }
  const nodes = [...packages.values()].sort((left, right) => left.id.localeCompare(right.id));
  const edges = rawEdges.map(edge => ({
    from: packages.get(edge.from_root).id,
    dependency: edge.dependency,
    to: packages.get(edge.to_root).id,
  })).sort((left, right) => canonicalJson(left).localeCompare(canonicalJson(right)));
  const graph = { nodes, edges };
  return { graph, sha256: canonicalSha256(graph) };
}

function equalCanonical(left, right) {
  return canonicalJson(left) === canonicalJson(right);
}

function loadProfile(modelKey, profileName) {
  const spec = MODEL_SPECS[modelKey];
  if (!spec) throw new LifecycleError("target model is outside the reviewed five-model set");
  if (spec.backend === "GGUF") {
    if (profileName !== "f16" && profileName !== "q8_0") {
      throw new LifecycleError("GGUF profile must be f16 or q8_0");
    }
    const cache = profileName === "q8_0" ? "q8_0" : false;
    return {
      contextLength: CONTEXT_LENGTH,
      maxParallelPredictions: 1,
      gpu: { ratio: "max" },
      flashAttention: true,
      speculativeDraftMtp: false,
      speculativeDraftSimple: false,
      useFp16ForKVCache: true,
      llamaKCacheQuantizationType: cache,
      llamaVCacheQuantizationType: cache,
    };
  }
  if (profileName !== "mlx-native") {
    throw new LifecycleError("MLX profile must be mlx-native");
  }
  return {
    contextLength: CONTEXT_LENGTH,
    maxParallelPredictions: 1,
    mlxDiskCache: false,
    mlxKvCacheQuantization: false,
  };
}

function loadProfileAtContext(modelKey, profileName, contextLength) {
  if (!Number.isSafeInteger(contextLength) || contextLength <= 0) {
    throw new LifecycleError("load profile context length is invalid");
  }
  const config = loadProfile(modelKey, profileName);
  config.contextLength = contextLength;
  return config;
}

function cacheBytesFor(modelKey, profileName, contextLength) {
  const projection = KV_CACHE_PROJECTIONS[modelKey];
  if (!projection || !Number.isSafeInteger(contextLength) || contextLength <= 0) {
    throw new LifecycleError("KV-cache projection input is invalid");
  }
  const cachedPositions = projection.fullLayers * contextLength
    + projection.slidingLayers * Math.min(contextLength, projection.slidingWindow);
  const fp16Bytes = cachedPositions * projection.kvHeads * projection.headDim * 2 * 2;
  const quantized = profileName === "q8_0";
  if (!new Set(["f16", "q8_0", "mlx-native"]).has(profileName)) {
    throw new LifecycleError("KV-cache projection profile is invalid");
  }
  return quantized ? Math.ceil(fp16Bytes / 2) : fp16Bytes;
}

function profileForSnapshot(snapshot) {
  const spec = MODEL_SPECS[snapshot.model_key];
  if (!spec) throw new LifecycleError("snapshot model is outside the reviewed set");
  const config = requirePlainObject(snapshot.load_config, "snapshot load config");
  if (spec.backend === "MLX") return "mlx-native";
  const key = config.llamaKCacheQuantizationType;
  const value = config.llamaVCacheQuantizationType;
  if (key === false && value === false) return "f16";
  if (key === "q8_0" && value === "q8_0") return "q8_0";
  throw new LifecycleError("snapshot GGUF cache profile is outside the reviewed profiles");
}

function validateInitialSnapshot(value) {
  const snapshot = requirePlainObject(value, "initial recovery snapshot");
  const spec = MODEL_SPECS[snapshot.model_key];
  if (!spec || snapshot.selected_variant !== spec.selectedVariant
      || snapshot.indexed_model_identifier !== spec.indexedModelIdentifier) {
    throw new LifecycleError(
      "initial recovery snapshot model, variant, or indexed identifier is invalid",
    );
  }
  for (const field of ["identifier", "instance_reference"]) {
    if (typeof snapshot[field] !== "string" || !snapshot[field]) {
      throw new LifecycleError(`initial recovery snapshot omitted ${field}`);
    }
  }
  if (snapshot.device_identifier !== null
      || !Number.isSafeInteger(snapshot.context_length) || snapshot.context_length <= 0
      || snapshot.context_length > spec.maxContextLength
      || snapshot.ttl_ms !== null
        && (!Number.isSafeInteger(snapshot.ttl_ms) || snapshot.ttl_ms < 0)
      || snapshot.last_used_time !== null
        && (!Number.isSafeInteger(snapshot.last_used_time) || snapshot.last_used_time < 0)) {
    throw new LifecycleError(
      "initial recovery snapshot device, context, TTL, or last-used relationship is invalid",
    );
  }
  const config = requirePlainObject(snapshot.load_config, "initial recovery load config");
  if (config.contextLength !== snapshot.context_length) {
    throw new LifecycleError(
      "initial recovery snapshot context differs from its effective load config",
    );
  }
  const profileName = profileForSnapshot(snapshot);
  assertExactLoadConfig(
    config,
    loadProfileAtContext(snapshot.model_key, profileName, snapshot.context_length),
  );
  normalizeProcessingState(snapshot.processing_state);
  return snapshot;
}

function validateProjectedLoadHeadroom(sample, modelKey, profileName, contextLength) {
  const resources = requirePlainObject(sample, "projected load resource sample");
  if (typeof resources.total_memory_bytes !== "number"
      || !Number.isSafeInteger(resources.total_memory_bytes)
      || resources.total_memory_bytes <= 0) {
    throw new LifecycleError("projected load resource sample lacks finite total memory");
  }
  const spec = MODEL_SPECS[modelKey];
  if (!spec) throw new LifecycleError("projected load target is outside the reviewed set");
  const availablePhysicalBytes = Math.floor(
    resources.total_memory_bytes * resources.free_memory_percent / 100,
  );
  const projectedCacheBytes = cacheBytesFor(modelKey, profileName, contextLength);
  const requiredCapacityBytes = spec.artifactSizeBytes
    + projectedCacheBytes + RUNTIME_HEADROOM_BYTES;
  const projection = {
    model_key: modelKey,
    profile: profileName,
    context_length: contextLength,
    exact_artifact_size_bytes: spec.artifactSizeBytes,
    projected_cache_bytes: projectedCacheBytes,
    runtime_headroom_bytes: RUNTIME_HEADROOM_BYTES,
    available_physical_bytes: availablePhysicalBytes,
    available_swap_bytes: resources.swap_free_bytes,
    projected_available_capacity_bytes: availablePhysicalBytes,
    projected_required_capacity_bytes: requiredCapacityBytes,
    projected_post_load_headroom_bytes: availablePhysicalBytes
      - spec.artifactSizeBytes - projectedCacheBytes,
    swap_policy: "Swap is a separate safety floor and is never counted as physical/Metal capacity.",
  };
  if (availablePhysicalBytes < requiredCapacityBytes) {
    throw new LifecycleError(
      `projected post-load headroom is below the ${RUNTIME_HEADROOM_BYTES}-byte runtime reserve`,
    );
  }
  return projection;
}

function validateDownloadedRow(row, spec) {
  requirePlainObject(row, "downloaded model row");
  const quantization = requirePlainObject(row.quantization, "downloaded model quantization");
  if (row.type !== "llm" || row.modelKey !== spec.modelKey
      || row.selectedVariant !== spec.selectedVariant
      || row.format !== spec.format || quantization.name !== spec.quantization
      || quantization.bits !== spec.quantizationBits
      || row.path !== spec.path || row.indexedModelIdentifier !== spec.indexedModelIdentifier
      || row.deviceIdentifier !== null) {
    throw new LifecycleError(`downloaded artifact identity changed for ${spec.modelKey}`);
  }
  if (!Array.isArray(row.variants) || row.variants.filter(value => value === spec.selectedVariant).length !== 1) {
    throw new LifecycleError(`downloaded selected variant is missing or ambiguous for ${spec.modelKey}`);
  }
  for (const field of ["path", "indexedModelIdentifier"]) {
    if (typeof row[field] !== "string" || !row[field]) {
      throw new LifecycleError(`downloaded artifact omitted ${field}`);
    }
  }
  for (const field of ["sizeBytes", "maxContextLength"]) {
    if (!Number.isSafeInteger(row[field]) || row[field] <= 0) {
      throw new LifecycleError(`downloaded artifact has invalid ${field}`);
    }
  }
  if (row.sizeBytes !== spec.artifactSizeBytes
      || row.maxContextLength !== spec.maxContextLength) {
    throw new LifecycleError(
      `downloaded artifact size or native context changed for ${spec.modelKey}`,
    );
  }
  if (row.maxContextLength < CONTEXT_LENGTH) {
    throw new LifecycleError(`downloaded artifact cannot support ${CONTEXT_LENGTH} tokens`);
  }
  return {
    type: row.type,
    model_key: row.modelKey,
    selected_variant: row.selectedVariant,
    format: row.format,
    quantization: { name: quantization.name, bits: quantization.bits },
    path: row.path,
    indexed_model_identifier: row.indexedModelIdentifier,
    device_identifier: null,
    size_bytes: row.sizeBytes,
    max_context_length: row.maxContextLength,
  };
}

async function downloadedArtifactFingerprints(client, modelKeys) {
  const rows = await client.system.listDownloadedModels("llm");
  if (!Array.isArray(rows)) throw new LifecycleError("downloaded model inventory is invalid");
  const result = {};
  for (const modelKey of [...new Set(modelKeys)].sort()) {
    const spec = MODEL_SPECS[modelKey];
    if (!spec) throw new LifecycleError("loaded model is outside the reviewed five-model set");
    const matches = rows.filter(row => row && row.modelKey === modelKey);
    if (matches.length !== 1) {
      throw new LifecycleError(`downloaded artifact is missing or ambiguous for ${modelKey}`);
    }
    const identity = validateDownloadedRow(matches[0], spec);
    result[modelKey] = { identity, sha256: canonicalSha256(identity) };
  }
  return result;
}

function normalizeEngineSelections(value) {
  if (!(value instanceof Map)) throw new LifecycleError("runtime engine selections must be a Map");
  const rows = [];
  for (const [format, selection] of value.entries()) {
    requirePlainObject(selection, "runtime engine selection");
    if (typeof format !== "string" || !format || typeof selection.name !== "string"
        || !selection.name || typeof selection.version !== "string" || !selection.version) {
      throw new LifecycleError("runtime engine selection is invalid");
    }
    rows.push({ format, name: selection.name, version: selection.version });
  }
  rows.sort((left, right) => left.format.localeCompare(right.format));
  return rows;
}

async function productionRuntimeIdentity(client, backends) {
  const sdkReceipt = CLIENT_SDK_RECEIPTS.get(client);
  if (!PRODUCTION_CLIENTS.has(client) || !sdkReceipt) {
    throw new LifecycleError("runtime identity requires a privately constructed production client");
  }
  const sdkEntry = sdkReceipt.entryPath;
  const sdkRoot = path.dirname(path.dirname(sdkEntry));
  const sdkPackage = requirePlainObject(
    JSON.parse(fs.readFileSync(path.join(sdkRoot, "package.json"), "utf8")),
    "LM Studio SDK package metadata",
  );
  const sdkTree = await fingerprintTree(sdkRoot);
  const sdkDependencyClosure = fingerprintSdkDependencyClosure(sdkRoot);
  const sdk = {
    name: sdkPackage.name,
    version: sdkPackage.version,
    entry_sha256: await sha256File(sdkEntry),
    closure_sha256: sdkTree.sha256,
    dependency_closure_sha256: sdkDependencyClosure.sha256,
  };
  const backendRows = {};
  const backendRoot = path.join(os.homedir(), ".lmstudio", "extensions", "backends");
  for (const backend of backends) {
    const reviewed = REVIEWED_ENGINES[backend];
    const directory = path.join(backendRoot, `${reviewed.name}-${reviewed.version}`);
    const tree = await fingerprintTree(directory);
    backendRows[backend] = {
      name: reviewed.name,
      version: reviewed.version,
      primary_file: reviewed.primaryFile,
      primary_sha256: await sha256File(path.join(directory, reviewed.primaryFile)),
      manifest_sha256: await sha256File(path.join(directory, "backend-manifest.json")),
      closure_sha256: tree.sha256,
    };
  }
  return {
    sdk,
    helper: { sha256: await sha256File(fs.realpathSync(__filename)) },
    backends: backendRows,
  };
}

function validateRuntimeIdentity(value, backends) {
  const identity = requirePlainObject(value, "runtime identity");
  const sdk = requirePlainObject(identity.sdk, "runtime identity SDK");
  const expectedSdk = {
    name: REVIEWED_SDK.name,
    version: REVIEWED_SDK.version,
    entry_sha256: REVIEWED_SDK.entrySha256,
    closure_sha256: REVIEWED_SDK.closureSha256,
    dependency_closure_sha256: REVIEWED_SDK.dependencyClosureSha256,
  };
  if (!equalCanonical(sdk, expectedSdk)) {
    throw new LifecycleError("runtime identity differs from the reviewed LM Studio SDK build");
  }
  const helper = requirePlainObject(identity.helper, "runtime identity helper");
  assertSha256(helper.sha256, "runtime helper identity");
  const foundBackends = requirePlainObject(identity.backends, "runtime identity backends");
  const normalizedBackends = {};
  for (const backend of backends) {
    const reviewed = REVIEWED_ENGINES[backend];
    const actual = requirePlainObject(foundBackends[backend], `runtime identity ${backend} backend`);
    const expected = {
      name: reviewed.name,
      version: reviewed.version,
      primary_file: reviewed.primaryFile,
      primary_sha256: reviewed.primarySha256,
      manifest_sha256: reviewed.manifestSha256,
      closure_sha256: reviewed.closureSha256,
    };
    if (!equalCanonical(actual, expected)) {
      throw new LifecycleError(`runtime identity differs from the reviewed ${backend} backend build`);
    }
    normalizedBackends[backend] = clone(actual);
  }
  return { sdk: clone(sdk), helper: { sha256: helper.sha256 }, backends: normalizedBackends };
}

async function captureEngineBinding(client, modelKeys) {
  const allSelections = normalizeEngineSelections(await client.runtime.engine.getSelections());
  const backends = [...new Set(modelKeys.map(modelKey => {
    const spec = MODEL_SPECS[modelKey];
    if (!spec) throw new LifecycleError("engine binding model is outside the reviewed set");
    return spec.backend;
  }))].sort();
  for (const modelKey of modelKeys) {
    const spec = MODEL_SPECS[modelKey];
    const expected = REVIEWED_ENGINES[spec.backend];
    const match = allSelections.find(row => row.format === spec.backend);
    if (!match || match.name !== expected.name || match.version !== expected.version) {
      throw new LifecycleError(`runtime engine selection changed for ${spec.backend}`);
    }
  }
  const offlineProvider = OFFLINE_TEST_RUNTIME_IDENTITIES.get(client);
  const rawIdentity = offlineProvider
    ? await offlineProvider(backends)
    : await productionRuntimeIdentity(client, backends);
  const runtimeIdentity = validateRuntimeIdentity(rawIdentity, backends);
  const selections = allSelections.filter(row => backends.includes(row.format));
  const binding = { selections, runtime_identity: runtimeIdentity };
  return { ...binding, sha256: canonicalSha256(binding) };
}

function projectEngineBinding(binding, modelKeys) {
  const source = requirePlainObject(binding, "captured engine binding");
  const sourceIdentity = requirePlainObject(
    source.runtime_identity,
    "captured runtime identity",
  );
  const requestedBackends = [...new Set(modelKeys.map(modelKey => {
    const spec = MODEL_SPECS[modelKey];
    if (!spec) throw new LifecycleError("engine projection model is outside the reviewed set");
    return spec.backend;
  }))].sort();
  const selections = source.selections.filter(row => requestedBackends.includes(row.format));
  const backends = Object.fromEntries(requestedBackends.map(backend => [
    backend,
    clone(requirePlainObject(
      sourceIdentity.backends[backend],
      `captured ${backend} runtime identity`,
    )),
  ]));
  const projected = {
    selections: clone(selections),
    runtime_identity: {
      sdk: clone(sourceIdentity.sdk),
      helper: clone(sourceIdentity.helper),
      backends,
    },
  };
  return { ...projected, sha256: canonicalSha256(projected) };
}

async function assertModelBindingUnchanged(client, journal, modelKey, label) {
  const expectedArtifacts = requirePlainObject(
    journal.artifact_fingerprints_pre,
    "captured artifact fingerprints",
  );
  const expectedArtifact = expectedArtifacts[modelKey];
  if (!expectedArtifact) throw new LifecycleError(`${label} lacks its captured artifact binding`);
  let actualArtifacts;
  try {
    actualArtifacts = await downloadedArtifactFingerprints(client, [modelKey]);
  } catch (error) {
    throw new LifecycleError(
      `${label} artifact fingerprint changed immediately before load: ${error.message}`,
      { cause: error },
    );
  }
  if (!equalCanonical(actualArtifacts[modelKey], expectedArtifact)) {
    throw new LifecycleError(`${label} artifact fingerprint changed immediately before load`);
  }
  const actualEngine = await captureEngineBinding(client, [modelKey]);
  const expectedEngine = projectEngineBinding(journal.engine_binding_pre, [modelKey]);
  if (!equalCanonical(actualEngine, expectedEngine)) {
    throw new LifecycleError(`${label} engine binding changed immediately before load`);
  }
  return { artifacts: actualArtifacts, engine: actualEngine };
}

async function assertAllBindingsUnchanged(client, journal, modelKeys, label) {
  const uniqueKeys = [...new Set(modelKeys)].sort();
  let artifacts;
  try {
    artifacts = await downloadedArtifactFingerprints(client, uniqueKeys);
  } catch (error) {
    throw new LifecycleError(`${label} artifact fingerprint changed: ${error.message}`, {
      cause: error,
    });
  }
  if (!equalCanonical(artifacts, journal.artifact_fingerprints_pre)) {
    throw new LifecycleError(`${label} artifact fingerprint changed`);
  }
  const engine = await captureEngineBinding(client, uniqueKeys);
  if (!equalCanonical(engine, journal.engine_binding_pre)) {
    throw new LifecycleError(`${label} engine binding changed`);
  }
  return { artifacts, engine };
}

function normalizeProcessingState(value) {
  requirePlainObject(value, "model processing state");
  if (value.status !== "idle" || value.queued !== 0) {
    throw new LifecycleError("all loaded models must be idle with an empty queue");
  }
  return { status: "idle", queued: 0 };
}

async function snapshotHandle(handle) {
  const info = requirePlainObject(await handle.getModelInfo(), "loaded model info");
  const loadConfig = requirePlainObject(await handle.getLoadConfig(), "loaded model config");
  const state = normalizeProcessingState(await handle.getInstanceProcessingState());
  for (const field of [
    "modelKey", "identifier", "indexedModelIdentifier", "selectedVariant", "instanceReference",
  ]) {
    if (typeof info[field] !== "string" || !info[field]) {
      throw new LifecycleError(`loaded model info omitted ${field}`);
    }
  }
  if (!MODEL_SPECS[info.modelKey] || info.selectedVariant !== MODEL_SPECS[info.modelKey].selectedVariant) {
    throw new LifecycleError("loaded model is not one of the exact reviewed variants");
  }
  if (info.deviceIdentifier !== null) throw new LifecycleError("loaded model is not local-only");
  if (!Number.isSafeInteger(info.contextLength) || info.contextLength <= 0) {
    throw new LifecycleError("loaded model context length is invalid");
  }
  for (const field of ["ttlMs", "lastUsedTime"]) {
    if (info[field] !== null && (!Number.isSafeInteger(info[field]) || info[field] < 0)) {
      throw new LifecycleError(`loaded model ${field} is invalid or unavailable`);
    }
  }
  return {
    model_key: info.modelKey,
    identifier: info.identifier,
    indexed_model_identifier: info.indexedModelIdentifier,
    selected_variant: info.selectedVariant,
    instance_reference: info.instanceReference,
    device_identifier: null,
    context_length: info.contextLength,
    ttl_ms: info.ttlMs,
    last_used_time: info.lastUsedTime,
    load_config: clone(loadConfig),
    processing_state: state,
  };
}

async function loadedSnapshot(client) {
  const handles = await client.llm.listLoaded();
  if (!Array.isArray(handles)) throw new LifecycleError("loaded model list is invalid");
  if (handles.length > 1) {
    throw new LifecycleError("lifecycle requires zero or one pre-existing loaded LLM");
  }
  if (handles.length === 0) return { handles, snapshots: [] };
  return { handles, snapshots: [await snapshotHandle(handles[0])] };
}

function restorableSnapshot(snapshot) {
  if (snapshot === null) return null;
  const value = clone(snapshot);
  delete value.instance_reference;
  delete value.last_used_time;
  return value;
}

function assertSnapshotPair(left, right, label, ignoreInstanceReference = false) {
  const lhs = ignoreInstanceReference ? restorableSnapshot(left) : left;
  const rhs = ignoreInstanceReference ? restorableSnapshot(right) : right;
  if (!equalCanonical(lhs, rhs)) throw new LifecycleError(`${label} changed between samples`);
}

function sleep(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}

async function twoIdleSamples(client, delayMs) {
  const first = await loadedSnapshot(client);
  await sleep(delayMs);
  const second = await loadedSnapshot(client);
  if (first.snapshots.length !== second.snapshots.length) {
    throw new LifecycleError("loaded model set changed between idle samples");
  }
  if (first.snapshots.length === 1) {
    assertSnapshotPair(first.snapshots[0], second.snapshots[0], "loaded model");
  }
  return second;
}

async function assertZeroLoaded(client, label) {
  const value = await loadedSnapshot(client);
  if (value.snapshots.length !== 0) throw new LifecycleError(`${label} did not reach exact zero`);
}

function validateResources(value) {
  const sample = requirePlainObject(value, "host resource sample");
  const numeric = [
    "free_memory_percent", "swap_free_bytes", "pages_throttled", "load_1m", "logical_cpus",
  ];
  for (const field of numeric) {
    if (typeof sample[field] !== "number" || !Number.isFinite(sample[field]) || sample[field] < 0) {
      throw new LifecycleError(`host resource sample has invalid ${field}`);
    }
  }
  if (sample.free_memory_percent > 100) {
    throw new LifecycleError("free memory percentage exceeds the physical-memory ceiling");
  }
  if (sample.free_memory_percent < MIN_FREE_MEMORY_PERCENT) {
    throw new LifecycleError(`free memory is below ${MIN_FREE_MEMORY_PERCENT}%`);
  }
  if (sample.swap_free_bytes < MIN_SWAP_FREE_BYTES) {
    throw new LifecycleError("swap free space is below the 2 GiB safety floor");
  }
  if (sample.pages_throttled !== 0) throw new LifecycleError("memory pages are throttled");
  if (sample.logical_cpus < 1 || sample.load_1m > sample.logical_cpus * 0.75) {
    throw new LifecycleError("one-minute host load exceeds the safety ceiling");
  }
  return clone(sample);
}

function validatePressureReliefResources(value) {
  const sample = requirePlainObject(value, "pressure-relief host resource sample");
  const numeric = [
    "free_memory_percent", "swap_free_bytes", "pages_throttled", "load_1m", "logical_cpus",
  ];
  for (const field of numeric) {
    if (typeof sample[field] !== "number" || !Number.isFinite(sample[field]) || sample[field] < 0) {
      throw new LifecycleError(`pressure-relief host resource sample has invalid ${field}`);
    }
  }
  if (sample.free_memory_percent > 100) {
    throw new LifecycleError("pressure-relief free memory percentage exceeds 100%");
  }
  if (sample.pages_throttled !== 0) throw new LifecycleError("memory pages are throttled");
  if (sample.logical_cpus < 1 || sample.load_1m > sample.logical_cpus * 0.75) {
    throw new LifecycleError("one-minute host load exceeds the safety ceiling");
  }
  return clone(sample);
}

function validateProcessGroupRecord(value) {
  const record = requirePlainObject(value, "callback process-group record");
  if (!Number.isSafeInteger(record.leader_pid) || record.leader_pid <= 0
      || !Number.isSafeInteger(record.pgid) || record.pgid <= 0
      || record.leader_pid !== record.pgid
      || !Number.isSafeInteger(record.uid) || record.uid < 0
      || typeof record.leader_start_time !== "string"
      || !/^[A-Z][a-z]{2} [A-Z][a-z]{2} [ 0-9][0-9] [0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4}$/u
        .test(record.leader_start_time)
      || record.leader_executable !== CALLBACK_SUPERVISOR_EXECUTABLE
      || typeof record.token !== "string" || !/^[0-9a-f]{64}$/u.test(record.token)) {
    throw new LifecycleError("callback process-group ownership record is invalid");
  }
  return {
    leader_pid: record.leader_pid,
    pgid: record.pgid,
    uid: record.uid,
    leader_start_time: record.leader_start_time,
    leader_executable: record.leader_executable,
    token: record.token,
  };
}

function processLeaderIdentity(pid) {
  let output;
  try {
    output = execFileSync("/bin/ps", [
      "-p", String(pid), "-o", "pid=,pgid=,uid=,lstart=,comm=",
    ], {
      encoding: "utf8", timeout: 5_000, maxBuffer: 64 * 1024,
      env: { PATH: "/usr/bin:/bin", LC_ALL: "C" },
    });
  } catch (error) {
    return null;
  }
  const match = /^\s*([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([A-Z][a-z]{2} [A-Z][a-z]{2} [ 0-9][0-9] [0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4})\s+(.+?)\s*$/u
    .exec(output);
  if (!match) return null;
  let executable;
  try {
    if (!path.isAbsolute(match[5])) return null;
    executable = fs.realpathSync(match[5]);
  } catch (error) {
    return null;
  }
  return {
    leader_pid: Number(match[1]),
    pgid: Number(match[2]),
    uid: Number(match[3]),
    leader_start_time: match[4],
    leader_executable: executable,
  };
}

function processGroupAlive(pgid) {
  try {
    process.kill(-pgid, 0);
    return true;
  } catch (error) {
    if (error.code === "ESRCH") return false;
    if (error.code === "EPERM") return true;
    throw error;
  }
}

async function productionProcessGroupProbe(value) {
  const record = validateProcessGroupRecord(value);
  if (!processGroupAlive(record.pgid)) return { alive: false, owned: true };
  const leader = processLeaderIdentity(record.leader_pid);
  if (!leader || !equalCanonical(leader, {
    leader_pid: record.leader_pid,
    pgid: record.pgid,
    uid: record.uid,
    leader_start_time: record.leader_start_time,
    leader_executable: record.leader_executable,
  })) {
    return { alive: true, owned: false };
  }
  let output;
  try {
    output = execFileSync("/bin/ps", [
      "-axo", "pid=,pgid=,uid=",
    ], { encoding: "utf8", timeout: 5_000, maxBuffer: 1024 * 1024 });
  } catch (error) {
    if (!processGroupAlive(record.pgid)) return { alive: false, owned: true };
    return { alive: true, owned: false };
  }
  const members = output.split("\n").map(line => {
    const match = /^\s*([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*$/u.exec(line);
    return match ? {
      pid: Number(match[1]), pgid: Number(match[2]), uid: Number(match[3]),
    } : null;
  }).filter(row => row !== null && row.pgid === record.pgid);
  if (members.length === 0) {
    return processGroupAlive(record.pgid)
      ? { alive: true, owned: false } : { alive: false, owned: true };
  }
  // The dedicated supervisor remains the group leader until every descendant
  // quiesces. Recovery never treats a leaderless/reused PGID as owned. The
  // random receipt is durable in the mode-0600 journal and is never placed in
  // globally visible process arguments.
  const groupBound = members.some(row => row.pid === record.leader_pid)
    && members.every(row => row.uid === record.uid && row.pgid === record.pgid);
  return {
    alive: true,
    owned: Boolean(groupBound),
  };
}

async function productionProcessGroupTerminate(value, graceMs = 5_000) {
  const record = validateProcessGroupRecord(value);
  if (!Number.isSafeInteger(graceMs) || graceMs <= 0) {
    throw new LifecycleError("callback process-group termination deadline is invalid");
  }
  const send = signal => {
    try {
      process.kill(-record.pgid, signal);
    } catch (error) {
      if (error.code !== "ESRCH" && error.code !== "EPERM") throw error;
    }
  };
  const waitUntil = async deadline => {
    while (Date.now() < deadline) {
      if (!processGroupAlive(record.pgid)) return true;
      await sleep(50);
    }
    return !processGroupAlive(record.pgid);
  };
  let state = await productionProcessGroupProbe(record);
  if (!state.alive) return;
  if (!state.owned) throw new LifecycleError("callback process group is alive but ownership is ambiguous");
  send("SIGTERM");
  if (await waitUntil(Date.now() + graceMs)) return;
  state = await productionProcessGroupProbe(record);
  if (!state.alive) return;
  if (!state.owned) {
    throw new LifecycleError("callback process-group ownership became ambiguous before SIGKILL");
  }
  send("SIGKILL");
  if (!await waitUntil(Date.now() + Math.min(graceMs, 1_000))) {
    throw new LifecycleError("callback process group did not quiesce after SIGKILL");
  }
}

function normalizeProcessGroupState(value) {
  const state = requirePlainObject(value, "callback process-group state");
  if (typeof state.alive !== "boolean" || typeof state.owned !== "boolean") {
    throw new LifecycleError("callback process-group state is invalid");
  }
  return { alive: state.alive, owned: state.owned };
}

function parseFirstNumber(pattern, text, label) {
  const match = pattern.exec(text);
  if (!match) throw new LifecycleError(`could not parse ${label}`);
  const value = Number(match[1]);
  if (!Number.isFinite(value)) throw new LifecycleError(`could not parse ${label}`);
  return value;
}

async function productionResourceProbe() {
  const run = (file, args) => execFileSync(file, args, {
    encoding: "utf8", timeout: 10_000, maxBuffer: 1024 * 1024,
    env: Object.fromEntries(["HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR"]
      .filter(key => process.env[key] !== undefined).map(key => [key, process.env[key]])),
  });
  let pressure;
  let swap;
  let vm;
  try {
    pressure = run("/usr/bin/memory_pressure", ["-Q"]);
    swap = run("/usr/sbin/sysctl", ["-n", "vm.swapusage"]);
    vm = run("/usr/bin/vm_stat", []);
  } catch (error) {
    throw new LifecycleError("host resource probe failed", { cause: error });
  }
  const swapFreeMib = parseFirstNumber(/free\s*=\s*([0-9.]+)M/u, swap, "free swap");
  return {
    free_memory_percent: parseFirstNumber(/free percentage:\s*([0-9.]+)%/u, pressure, "free memory"),
    swap_free_bytes: Math.floor(swapFreeMib * 1024 * 1024),
    pages_throttled: parseFirstNumber(/Pages throttled:\s*([0-9.]+)/u, vm, "throttled pages"),
    load_1m: os.loadavg()[0],
    logical_cpus: os.cpus().length,
    total_memory_bytes: os.totalmem(),
  };
}

function assertSafePath(file, label) {
  if (typeof file !== "string" || !path.isAbsolute(file) || path.basename(file) === "."
      || path.basename(file) === "..") {
    throw new LifecycleError(`${label} must be an absolute file path`);
  }
  const parent = path.dirname(file);
  const parentStat = fs.lstatSync(parent);
  if (!parentStat.isDirectory() || parentStat.isSymbolicLink()) {
    throw new LifecycleError(`${label} parent must be an existing non-symlink directory`);
  }
}

function fsyncDirectory(directory) {
  let descriptor;
  try {
    descriptor = fs.openSync(directory, fs.constants.O_RDONLY);
    fs.fsyncSync(descriptor);
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
  }
}

function processIsAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error.code === "ESRCH") return false;
    if (error.code === "EPERM") return true;
    throw error;
  }
}

function removeProvenStaleLock(lockPath) {
  const before = fs.lstatSync(lockPath, { bigint: true });
  if (!before.isFile() || before.isSymbolicLink() || (before.mode & 0o777n) !== 0o600n
      || before.uid !== BigInt(process.getuid()) || before.size > 4096n) {
    throw new LifecycleError("existing lifecycle lock identity, mode, owner, or size is unsafe");
  }
  let record;
  try {
    record = JSON.parse(fs.readFileSync(lockPath, "utf8"));
  } catch (error) {
    throw new LifecycleError("existing lifecycle lock is not a valid recovery record", { cause: error });
  }
  if (!record || record.schema_version !== 1 || record.kind !== "lmstudio-model-lifecycle-lock-v1"
      || !Number.isSafeInteger(record.pid) || record.pid <= 0) {
    throw new LifecycleError("existing lifecycle lock recovery record is invalid");
  }
  if (processIsAlive(record.pid)) {
    throw new LifecycleError("existing lifecycle lock owner process is still alive");
  }
  const after = fs.lstatSync(lockPath, { bigint: true });
  if (after.dev !== before.dev || after.ino !== before.ino || after.size !== before.size
      || after.mtimeNs !== before.mtimeNs || after.ctimeNs !== before.ctimeNs) {
    throw new LifecycleError("existing lifecycle lock changed during stale-lock verification");
  }
  fs.unlinkSync(lockPath);
  fsyncDirectory(path.dirname(lockPath));
  return { stale_pid: record.pid };
}

function acquireLock(lockPath, allowStaleRecovery = false) {
  assertSafePath(lockPath, "lock path");
  let descriptor;
  let stale = null;
  try {
    descriptor = fs.openSync(lockPath, fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_RDWR, 0o600);
  } catch (error) {
    if (error.code !== "EEXIST" || !allowStaleRecovery) {
      throw new LifecycleError("exclusive lifecycle lock is already held or unavailable", { cause: error });
    }
    stale = removeProvenStaleLock(lockPath);
    try {
      descriptor = fs.openSync(lockPath, fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_RDWR, 0o600);
    } catch (retryError) {
      throw new LifecycleError("exclusive lifecycle lock changed during stale recovery", { cause: retryError });
    }
  }
  try {
    fs.fchmodSync(descriptor, 0o600);
    const identity = fs.fstatSync(descriptor, { bigint: true });
    fs.writeFileSync(descriptor, `${canonicalJson({
      schema_version: 1,
      kind: "lmstudio-model-lifecycle-lock-v1",
      pid: process.pid,
    })}\n`, { encoding: "utf8" });
    fs.fsyncSync(descriptor);
    fsyncDirectory(path.dirname(lockPath));
    return { descriptor, identity, stale };
  } catch (error) {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    throw new LifecycleError("exclusive lifecycle lock could not be initialized", { cause: error });
  }
}

function releaseLock(lockPath, lock) {
  try {
    const current = fs.lstatSync(lockPath, { bigint: true });
    if (!current.isFile() || current.isSymbolicLink()
        || current.dev !== lock.identity.dev || current.ino !== lock.identity.ino) {
      throw new LifecycleError("exclusive lifecycle lock identity changed");
    }
    fs.unlinkSync(lockPath);
    fsyncDirectory(path.dirname(lockPath));
  } finally {
    fs.closeSync(lock.descriptor);
  }
}

function retainLock(lock) {
  fs.closeSync(lock.descriptor);
}

function writeNewJournal(journalPath, value) {
  assertSafePath(journalPath, "journal path");
  let descriptor;
  try {
    descriptor = fs.openSync(journalPath, fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_WRONLY, 0o600);
    fs.fchmodSync(descriptor, 0o600);
    fs.writeFileSync(descriptor, `${canonicalJson(value)}\n`, { encoding: "utf8" });
    fs.fsyncSync(descriptor);
  } catch (error) {
    throw new LifecycleError("recovery journal already exists or cannot be created", { cause: error });
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
  }
  fsyncDirectory(path.dirname(journalPath));
}

function updateJournal(journalPath, value) {
  const temporary = `${journalPath}.tmp-${process.pid}-${crypto.randomBytes(6).toString("hex")}`;
  let descriptor;
  try {
    descriptor = fs.openSync(temporary, fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_WRONLY, 0o600);
    fs.fchmodSync(descriptor, 0o600);
    fs.writeFileSync(descriptor, `${canonicalJson(value)}\n`, { encoding: "utf8" });
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    fs.renameSync(temporary, journalPath);
    fsyncDirectory(path.dirname(journalPath));
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    try { fs.unlinkSync(temporary); } catch (error) { if (error.code !== "ENOENT") throw error; }
  }
}

function readJournal(journalPath) {
  assertSafePath(journalPath, "journal path");
  const statValue = fs.lstatSync(journalPath);
  if (!statValue.isFile() || statValue.isSymbolicLink() || (statValue.mode & 0o777) !== 0o600
      || statValue.uid !== process.getuid() || statValue.size > 1024 * 1024) {
    throw new LifecycleError("recovery journal identity, mode, owner, or size is unsafe");
  }
  const value = JSON.parse(fs.readFileSync(journalPath, "utf8"));
  requirePlainObject(value, "recovery journal");
  if (value.schema_version !== JOURNAL_SCHEMA_VERSION) {
    throw new LifecycleError("recovery journal schema is unsupported");
  }
  return value;
}

function removeJournal(journalPath) {
  const statValue = fs.lstatSync(journalPath);
  if (!statValue.isFile() || statValue.isSymbolicLink() || (statValue.mode & 0o777) !== 0o600) {
    throw new LifecycleError("refusing to remove an unsafe recovery journal");
  }
  fs.unlinkSync(journalPath);
  fsyncDirectory(path.dirname(journalPath));
}

function addPhase(state, phase) {
  state.audit.phases.push(phase);
  state.journal.phase = phase;
  if (state.journalCreated) updateJournal(state.journalPath, state.journal);
}

function attachAudit(error, audit) {
  const wrapped = error instanceof LifecycleError
    ? error : new LifecycleError(error && error.message ? error.message : "lifecycle operation failed", { cause: error });
  wrapped.lifecycleAudit = clone(audit);
  return wrapped;
}

async function operationWithDeadline(operation, milliseconds, label, abortController = null) {
  if (!Number.isSafeInteger(milliseconds) || milliseconds <= 0) {
    throw new LifecycleError(`${label} deadline is invalid`);
  }
  let settled = false;
  const promise = Promise.resolve().then(operation).finally(() => { settled = true; });
  let timer;
  const deadline = new Promise((resolve, reject) => {
    timer = setTimeout(() => {
      if (abortController) abortController.abort();
      reject(new OperationDeadlineError(`${label} exceeded its deadline`, false));
    }, milliseconds);
  });
  try {
    return await Promise.race([promise, deadline]);
  } catch (error) {
    if (!(error instanceof OperationDeadlineError)) throw error;
    let graceTimer;
    try {
      await Promise.race([
        promise.catch(() => undefined),
        new Promise(resolve => { graceTimer = setTimeout(resolve, DEADLINE_SETTLE_GRACE_MS); }),
      ]);
    } finally {
      if (graceTimer !== undefined) clearTimeout(graceTimer);
    }
    error.operationSettled = settled;
    error.operationPromise = promise;
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function validatePendingOperation(value) {
  const pending = requirePlainObject(value, "pending lifecycle operation");
  if (!new Set(["load", "unload"]).has(pending.kind)
      || typeof pending.label !== "string" || !pending.label
      || typeof pending.identifier !== "string" || !pending.identifier) {
    throw new LifecycleError("pending lifecycle operation record is invalid");
  }
  return { kind: pending.kind, label: pending.label, identifier: pending.identifier };
}

async function journaledOperation(
  state,
  record,
  operation,
  milliseconds,
  label,
  abortController = null,
) {
  const pending = validatePendingOperation(record);
  if (state.journal.operation_pending !== null) {
    throw new OperationUncertainError("another lifecycle operation is already pending");
  }
  state.journal.operation_pending = pending;
  updateJournal(state.journalPath, state.journal);
  let result;
  let operationError = null;
  try {
    result = await operationWithDeadline(operation, milliseconds, label, abortController);
  } catch (error) {
    operationError = error;
  }
  if (operationError instanceof OperationDeadlineError && !operationError.operationSettled) {
    throw operationError;
  }
  try {
    state.journal.operation_pending = null;
    updateJournal(state.journalPath, state.journal);
  } catch (error) {
    state.journal.operation_pending = pending;
    throw new OperationUncertainError(
      `${label} settled but its durable pending marker could not be cleared`,
      { cause: error },
    );
  }
  if (operationError) throw operationError;
  return result;
}

async function stableLoadedState(client, delayMs) {
  const first = await loadedSnapshot(client);
  await sleep(delayMs);
  const second = await loadedSnapshot(client);
  if (first.snapshots.length !== second.snapshots.length) {
    throw new LifecycleError("loaded state is unstable after a lifecycle failure");
  }
  if (first.snapshots.length === 1) {
    assertSnapshotPair(first.snapshots[0], second.snapshots[0], "loaded state");
  }
  return second;
}

function assertExactLoadConfig(actual, expected) {
  requirePlainObject(actual, "effective load config");
  requirePlainObject(expected, "reviewed load config");
  const actualKeys = Object.keys(actual).sort();
  const expectedKeys = Object.keys(expected).sort();
  if (!equalCanonical(actualKeys, expectedKeys) || !equalCanonical(actual, expected)) {
    throw new LifecycleError(
      "effective load config differs from the strict reviewed key/value allowlist",
    );
  }
}

function assertOwnedTargetIdentity(snapshot, target, identifier) {
  if (snapshot.identifier !== identifier || snapshot.model_key !== target.modelKey
      || snapshot.indexed_model_identifier !== target.indexedModelIdentifier
      || snapshot.selected_variant !== target.selectedVariant
      || typeof snapshot.instance_reference !== "string" || !snapshot.instance_reference
      || snapshot.device_identifier !== null
      || snapshot.context_length !== CONTEXT_LENGTH || snapshot.ttl_ms !== null) {
    throw new LifecycleError("owned target identity or local binding differs");
  }
}

function assertOwnedTargetSnapshot(snapshot, target, identifier, config) {
  assertOwnedTargetIdentity(snapshot, target, identifier);
  assertExactLoadConfig(snapshot.load_config, config);
}

async function verifyOwnedTarget(client, target, identifier, config) {
  const state = await loadedSnapshot(client);
  if (state.snapshots.length !== 1) throw new LifecycleError("owned target is not the only loaded LLM");
  const snapshot = state.snapshots[0];
  assertOwnedTargetSnapshot(snapshot, target, identifier, config);
  return { handle: state.handles[0], snapshot };
}

function targetOwnershipProjection(snapshot) {
  const value = requirePlainObject(snapshot, "owned target snapshot");
  return {
    model_key: value.model_key,
    identifier: value.identifier,
    indexed_model_identifier: value.indexed_model_identifier,
    selected_variant: value.selected_variant,
    instance_reference: value.instance_reference,
    device_identifier: value.device_identifier,
    context_length: value.context_length,
    ttl_ms: value.ttl_ms,
    load_config: clone(requirePlainObject(value.load_config, "owned target load config")),
  };
}

function validateTargetOwnershipProjection(value, target, identifier, profileName) {
  const projection = targetOwnershipProjection(
    requirePlainObject(value, "owned target ownership projection"),
  );
  assertOwnedTargetSnapshot(projection, target, identifier, loadProfile(target.modelKey, profileName));
  return projection;
}

function assertTargetOwnership(snapshot, projection, label) {
  if (!equalCanonical(targetOwnershipProjection(snapshot), projection)) {
    throw new LifecycleError(`${label} differs from the durable exact ownership projection`);
  }
}

function journalTargetOwnership(journal, target, identifier, profileName) {
  if (journal.owned_target_ownership === null) return null;
  const projection = validateTargetOwnershipProjection(
    journal.owned_target_ownership,
    target,
    identifier,
    profileName,
  );
  if (typeof journal.owned_target_ownership_sha256 !== "string"
      || journal.owned_target_ownership_sha256 !== canonicalSha256(projection)) {
    throw new LifecycleError("owned target ownership projection digest is invalid");
  }
  return projection;
}

function validateParkCandidateSnapshot(snapshot) {
  const value = requirePlainObject(snapshot, "park candidate snapshot");
  const target = MODEL_SPECS[value.model_key];
  if (!target || value.selected_variant !== target.selectedVariant
      || value.indexed_model_identifier !== target.indexedModelIdentifier
      || value.device_identifier !== null) {
    throw new LifecycleError("loaded model is not one exact local reviewed candidate variant");
  }
  return target;
}

async function verifyRestoration(client, initial) {
  const state = await loadedSnapshot(client);
  if (initial === null) {
    if (state.snapshots.length !== 0) throw new LifecycleError("zero-model initial state was not restored");
    return;
  }
  if (state.snapshots.length !== 1) throw new LifecycleError("initial loaded model was not restored");
  assertSnapshotPair(initial, state.snapshots[0], "restored model", true);
}

function ownedIdentifier(transactionId, targetModelKey) {
  if (typeof transactionId !== "string" || !/^[a-z0-9]{6,32}$/u.test(transactionId)) {
    throw new LifecycleError("transaction id must be 6-32 lowercase ASCII letters or digits");
  }
  const slug = targetModelKey.replace(/[^a-z0-9]+/gu, "-").replace(/^-|-$/gu, "");
  return `codex-bakeoff-${transactionId}-${slug}`;
}

function canonicalStatePaths() {
  return {
    journalPath: path.join(os.homedir(), ".lmstudio-model-lifecycle-recovery.json"),
    lockPath: path.join(os.homedir(), ".lmstudio-model-lifecycle.lock"),
  };
}

function validateCanonicalStatePaths(journalPath, lockPath) {
  const expected = canonicalStatePaths();
  if (journalPath !== expected.journalPath || lockPath !== expected.lockPath) {
    throw new LifecycleError(
      "journal and lock must use the single canonical per-user lifecycle state paths",
    );
  }
  return expected;
}

function normalizedOptions(options) {
  requirePlainObject(options, "lifecycle options");
  const target = MODEL_SPECS[options.targetModelKey];
  if (!target) throw new LifecycleError("target model is outside the reviewed five-model set");
  if (!options.client || typeof options.client !== "object") throw new LifecycleError("SDK client is required");
  if (typeof options.callback !== "function") throw new LifecycleError("transaction callback is required");
  if (options.signal !== undefined
      && (!options.signal || typeof options.signal.aborted !== "boolean"
        || typeof options.signal.addEventListener !== "function")) {
    throw new LifecycleError("transaction abort signal is invalid");
  }
  validateCanonicalStatePaths(options.journalPath, options.lockPath);
  const endpointReceipt = CLIENT_ENDPOINT_RECEIPTS.get(options.client);
  if (!endpointReceipt) {
    throw new LifecycleError("SDK client lacks a private endpoint creation receipt");
  }
  const claimedEndpoint = validateEndpoint(options.endpoint);
  if (claimedEndpoint !== endpointReceipt.endpoint) {
    throw new LifecycleError("transaction endpoint differs from the client creation receipt");
  }
  const sdkReceipt = CLIENT_SDK_RECEIPTS.get(options.client);
  if (!sdkReceipt) {
    throw new LifecycleError("SDK client lacks a private reviewed SDK creation receipt");
  }
  return {
    ...options,
    endpoint: endpointReceipt.endpoint,
    sdkBinding: sdkCallbackBinding(sdkReceipt),
    target,
    config: loadProfile(options.targetModelKey, options.profileName),
    identifier: ownedIdentifier(options.transactionId, options.targetModelKey),
    idleSampleDelayMs: options.idleSampleDelayMs ?? DEFAULT_IDLE_SAMPLE_DELAY_MS,
    callbackTimeoutMs: validateCallbackTimeoutMs(
      options.callbackTimeoutMs ?? DEFAULT_CALLBACK_TIMEOUT_MS,
    ),
    resourceProbe: options.resourceProbe || productionResourceProbe,
    timeouts: {
      loadMs: options.timeouts?.loadMs ?? DEFAULT_LOAD_TIMEOUT_MS,
      unloadMs: options.timeouts?.unloadMs ?? DEFAULT_UNLOAD_TIMEOUT_MS,
    },
  };
}

function normalizedParkOptions(options) {
  requirePlainObject(options, "park options");
  if (!options.client || typeof options.client !== "object") {
    throw new LifecycleError("SDK client is required");
  }
  if (options.signal !== undefined
      && (!options.signal || typeof options.signal.aborted !== "boolean"
        || typeof options.signal.addEventListener !== "function")) {
    throw new LifecycleError("park abort signal is invalid");
  }
  validateCanonicalStatePaths(options.journalPath, options.lockPath);
  return {
    ...options,
    idleSampleDelayMs: options.idleSampleDelayMs ?? DEFAULT_IDLE_SAMPLE_DELAY_MS,
    resourceProbe: options.resourceProbe || productionResourceProbe,
    timeouts: {
      unloadMs: options.timeouts?.unloadMs ?? DEFAULT_UNLOAD_TIMEOUT_MS,
    },
  };
}

async function runLifecycleTransaction(rawOptions) {
  const options = normalizedOptions(rawOptions);
  const state = {
    audit: {
      schema_version: 1,
      transaction_id: options.transactionId,
      target_model_key: options.targetModelKey,
      selected_variant: options.target.selectedVariant,
      profile: options.profileName,
      callback_timeout_ms: options.callbackTimeoutMs,
      owned_identifier: options.identifier,
      phases: [],
      resource_samples: [],
      artifact_fingerprint_scope: (
        "Normalized SDK downloaded-model identity metadata; not model-file content bytes."
      ),
      limitation: "SDK unload has no AbortSignal; a timeout retains the recovery journal and forbids racing a new load.",
    },
    journal: {
      schema_version: JOURNAL_SCHEMA_VERSION,
      kind: "transaction",
      transaction_id: options.transactionId,
      target_model_key: options.targetModelKey,
      selected_variant: options.target.selectedVariant,
      profile: options.profileName,
      callback_timeout_ms: options.callbackTimeoutMs,
      owned_identifier: options.identifier,
      owned_target_ownership: null,
      owned_target_ownership_sha256: null,
      initial_snapshot: null,
      initial_state_had_model: null,
      initial_snapshot_sha256: null,
      artifact_fingerprints_pre: null,
      engine_binding_pre: null,
      callback_process_group: null,
      operation_pending: null,
      phase: "created",
      mutation_started: false,
    },
    journalPath: options.journalPath,
    journalCreated: false,
  };
  let lock;
  let primaryError = null;
  let initial = null;
  let initialVerifiedUnloaded = false;
  let ownedHandle = null;
  let ownedMayExist = false;
  let ownedCleanupFailed = false;
  let unsafeUnsettledOperation = false;
  let artifactError = null;
  let callbackResult;
  let restored = false;

  const gate = async (observeSignal = true) => {
    if (observeSignal && options.signal?.aborted) {
      throw new LifecycleError("lifecycle transaction was interrupted");
    }
    const sample = validateResources(await options.resourceProbe());
    state.audit.resource_samples.push(sample);
    return sample;
  };

  try {
    lock = acquireLock(options.lockPath);
    state.audit.phases.push("lock_acquired");
    writeNewJournal(options.journalPath, state.journal);
    state.journalCreated = true;
    addPhase(state, "journal_created");
    await gate();
    addPhase(state, "host_gate_pre");

    const first = await loadedSnapshot(options.client);
    addPhase(state, "snapshot_idle_1");
    await sleep(options.idleSampleDelayMs);
    const second = await loadedSnapshot(options.client);
    addPhase(state, "snapshot_idle_2");
    if (first.snapshots.length !== second.snapshots.length) {
      throw new LifecycleError("loaded model set changed between idle samples");
    }
    if (first.snapshots.length === 1) {
      assertSnapshotPair(first.snapshots[0], second.snapshots[0], "loaded model");
      initial = second.snapshots[0];
      validateInitialSnapshot(initial);
    }
    state.journal.initial_snapshot = initial;
    state.journal.initial_state_had_model = initial !== null;
    state.journal.initial_snapshot_sha256 = canonicalSha256(initial);
    addPhase(state, "snapshot_captured");

    const keys = [options.targetModelKey];
    if (initial) keys.push(initial.model_key);
    const artifactPre = await downloadedArtifactFingerprints(options.client, keys);
    state.audit.artifact_fingerprints_pre = artifactPre;
    state.journal.artifact_fingerprints_pre = artifactPre;
    addPhase(state, "artifact_fingerprint_pre");
    const enginePre = await captureEngineBinding(options.client, keys);
    state.audit.engine_binding_pre = enginePre;
    state.journal.engine_binding_pre = enginePre;
    addPhase(state, "engine_bound_pre");

    if (initial) {
      const readyToUnload = await twoIdleSamples(options.client, options.idleSampleDelayMs);
      if (readyToUnload.snapshots.length !== 1) {
        throw new LifecycleError("initial model disappeared before unload");
      }
      assertSnapshotPair(initial, readyToUnload.snapshots[0], "initial model before unload");
      addPhase(state, "initial_idle_revalidated");
      state.journal.mutation_started = true;
      addPhase(state, "initial_unload_started");
      try {
        await journaledOperation(
          state,
          { kind: "unload", label: "initial model unload", identifier: initial.identifier },
          () => readyToUnload.handles[0].unload(), options.timeouts.unloadMs,
          "initial model unload",
        );
      } catch (error) {
        if ((error instanceof OperationDeadlineError && !error.operationSettled)
            || error.operationUncertain) {
          unsafeUnsettledOperation = true;
        }
        throw error;
      }
      addPhase(state, "initial_unloaded");
      await assertZeroLoaded(options.client, "initial unload");
      initialVerifiedUnloaded = true;
      addPhase(state, "zero_verified");
    } else {
      state.journal.mutation_started = true;
      addPhase(state, "initial_unload_started");
      addPhase(state, "initial_unloaded");
      await assertZeroLoaded(options.client, "empty initial state");
      initialVerifiedUnloaded = true;
      addPhase(state, "zero_verified");
    }

    const targetResources = await gate();
    state.audit.target_load_projection = validateProjectedLoadHeadroom(
      targetResources,
      options.targetModelKey,
      options.profileName,
      CONTEXT_LENGTH,
    );
    addPhase(state, "host_gate_target");
    await assertModelBindingUnchanged(
      options.client,
      state.journal,
      options.targetModelKey,
      "target model",
    );
    addPhase(state, "target_binding_revalidated");
    addPhase(state, "target_load_started");
    const controller = new AbortController();
    const abortTargetLoad = () => controller.abort();
    if (options.signal) {
      if (options.signal.aborted) abortTargetLoad();
      else options.signal.addEventListener("abort", abortTargetLoad, { once: true });
    }
    try {
      ownedHandle = await journaledOperation(
        state,
        { kind: "load", label: "target model load", identifier: options.identifier },
        () => options.client.llm.load(options.target.selectedVariant, {
          identifier: options.identifier,
          config: clone(options.config),
          deviceIdentifier: null,
          signal: controller.signal,
        }),
        options.timeouts.loadMs,
        "target model load",
        controller,
      );
      ownedMayExist = true;
    } catch (error) {
      if ((error instanceof OperationDeadlineError && !error.operationSettled)
          || error.operationUncertain) {
        unsafeUnsettledOperation = true;
      }
      throw error;
    } finally {
      if (options.signal) options.signal.removeEventListener("abort", abortTargetLoad);
    }
    addPhase(state, "target_loaded");
    const returnedSnapshot = await snapshotHandle(ownedHandle);
    assertOwnedTargetSnapshot(
      returnedSnapshot,
      options.target,
      options.identifier,
      options.config,
    );
    const verified = await verifyOwnedTarget(
      options.client, options.target, options.identifier, options.config,
    );
    assertSnapshotPair(
      returnedSnapshot,
      verified.snapshot,
      "load-returned target and sole loaded target",
    );
    ownedHandle = verified.handle;
    ownedMayExist = true;
    state.audit.effective_target_snapshot = verified.snapshot;
    const ownership = validateTargetOwnershipProjection(
      targetOwnershipProjection(verified.snapshot),
      options.target,
      options.identifier,
      options.profileName,
    );
    state.journal.owned_target_ownership = ownership;
    state.journal.owned_target_ownership_sha256 = canonicalSha256(ownership);
    state.audit.owned_target_ownership = clone(ownership);
    addPhase(state, "target_verified");
    await gate();
    addPhase(state, "host_gate_post_load");
    addPhase(state, "callback_started");
    const callbackController = new AbortController();
    const abortCallback = () => callbackController.abort();
    if (options.signal) {
      if (options.signal.aborted) abortCallback();
      else options.signal.addEventListener("abort", abortCallback, { once: true });
    }
    try {
      callbackResult = await operationWithDeadline(
        () => {
          const callbackContext = {
            endpoint: options.endpoint,
            identifier: options.identifier,
            modelKey: options.targetModelKey,
            selectedVariant: options.target.selectedVariant,
            profile: options.profileName,
            effectiveSnapshot: clone(verified.snapshot),
            signal: callbackController.signal,
            resourceProbe: options.resourceProbe,
            registerProcessGroup: record => {
              const normalized = validateProcessGroupRecord(record);
              if (state.journal.callback_process_group !== null) {
                throw new LifecycleError("a callback process group is already registered");
              }
              state.journal.callback_process_group = normalized;
              updateJournal(state.journalPath, state.journal);
              state.audit.phases.push("callback_process_group_registered");
            },
            clearProcessGroup: record => {
              const normalized = validateProcessGroupRecord(record);
              if (!equalCanonical(normalized, state.journal.callback_process_group)) {
                throw new LifecycleError("callback process-group ownership changed before cleanup");
              }
              state.journal.callback_process_group = null;
              updateJournal(state.journalPath, state.journal);
              state.audit.phases.push("callback_process_group_cleared");
            },
          };
          CALLBACK_CONTEXT_SDK_BINDINGS.set(callbackContext, options.sdkBinding);
          let result;
          try {
            result = options.callback(callbackContext);
          } catch (error) {
            CALLBACK_CONTEXT_SDK_BINDINGS.delete(callbackContext);
            throw error;
          }
          return Promise.resolve(result).finally(() => {
            CALLBACK_CONTEXT_SDK_BINDINGS.delete(callbackContext);
          });
        },
        options.callbackTimeoutMs,
        "transaction callback",
        callbackController,
      );
      addPhase(state, "callback_completed");
    } catch (error) {
      if (error instanceof OperationDeadlineError && !error.operationSettled) {
        unsafeUnsettledOperation = true;
      }
      addPhase(state, "callback_failed");
      primaryError = error;
    } finally {
      if (options.signal) options.signal.removeEventListener("abort", abortCallback);
    }
  } catch (error) {
    primaryError = primaryError || error;
  }

  if (state.journal.callback_process_group !== null) {
    unsafeUnsettledOperation = true;
    const callbackGroupError = new LifecycleError(
      "callback process group remains registered; model cleanup is forbidden",
    );
    primaryError = primaryError
      ? new LifecycleError(
        `transaction failure: ${primaryError.message}; ${callbackGroupError.message}`,
        { cause: new AggregateError([primaryError, callbackGroupError]) },
      )
      : callbackGroupError;
  }

  if (state.journalCreated && state.journal.mutation_started) {
    try {
      if (unsafeUnsettledOperation) {
        throw new LifecycleError(
          "a lifecycle operation or callback group remains unsettled; recovery journal retained",
        );
      }

      if (ownedMayExist) {
        const ownership = journalTargetOwnership(
          state.journal, options.target, options.identifier, options.profileName,
        );
        if (ownership === null) {
          throw new LifecycleError(
            "owned target lacks a durable exact ownership projection; cleanup unload is forbidden",
          );
        }
        const readyToUnload = await twoIdleSamples(options.client, options.idleSampleDelayMs);
        if (readyToUnload.snapshots.length !== 1) {
          throw new LifecycleError("owned target disappeared before cleanup");
        }
        assertTargetOwnership(
          readyToUnload.snapshots[0], ownership, "owned target before cleanup",
        );
        ownedHandle = readyToUnload.handles[0];
        addPhase(state, "owned_idle_revalidated");
        addPhase(state, "owned_unload_started");
        try {
          await journaledOperation(
            state,
            { kind: "unload", label: "owned model unload", identifier: options.identifier },
            () => ownedHandle.unload(), options.timeouts.unloadMs, "owned model unload",
          );
        } catch (error) {
          if ((error instanceof OperationDeadlineError && !error.operationSettled)
              || error.operationUncertain) {
            unsafeUnsettledOperation = true;
          }
          ownedCleanupFailed = true;
          throw error;
        }
        ownedMayExist = false;
        addPhase(state, "owned_unloaded");
      } else if (initialVerifiedUnloaded) {
        const current = await stableLoadedState(options.client, options.idleSampleDelayMs);
        if (current.snapshots.length === 1) {
          const candidate = current.snapshots[0];
          const ownership = journalTargetOwnership(
            state.journal, options.target, options.identifier, options.profileName,
          );
          if (ownership === null) {
            throw new LifecycleError(
              "loaded target lacks a durable exact ownership projection; cleanup unload is forbidden",
            );
          }
          assertTargetOwnership(candidate, ownership, "recovered owned target before cleanup");
          addPhase(state, "owned_unload_started");
          try {
            await journaledOperation(
              state,
              {
                kind: "unload", label: "recovered owned model unload",
                identifier: options.identifier,
              },
              () => current.handles[0].unload(), options.timeouts.unloadMs,
              "recovered owned model unload",
            );
          } catch (error) {
            if ((error instanceof OperationDeadlineError && !error.operationSettled)
                || error.operationUncertain) {
              unsafeUnsettledOperation = true;
            }
            throw error;
          }
          addPhase(state, "owned_unloaded");
        }
      }

      if (initialVerifiedUnloaded) {
        await assertZeroLoaded(options.client, "owned cleanup");
        addPhase(state, "zero_verified_after_owned_cleanup");
        let artifactPost = null;
        try {
          artifactPost = await downloadedArtifactFingerprints(
            options.client,
            [options.targetModelKey, ...(initial ? [initial.model_key] : [])],
          );
          state.audit.artifact_fingerprints_post = artifactPost;
          if (!equalCanonical(artifactPost, state.journal.artifact_fingerprints_pre)) {
            artifactError = new LifecycleError(
              "artifact fingerprint changed during lifecycle transaction",
            );
          }
        } catch (error) {
          artifactError = new LifecycleError(
            `artifact fingerprint changed during lifecycle transaction: ${error.message}`,
            { cause: error },
          );
        }
        addPhase(state, "artifact_fingerprint_post");

        const restoreResources = await gate(false);
        if (initial) {
          state.audit.initial_restore_projection = validateProjectedLoadHeadroom(
            restoreResources,
            initial.model_key,
            profileForSnapshot(initial),
            initial.context_length,
          );
        }
        addPhase(state, "host_gate_restore");
        if (initial) {
          await assertModelBindingUnchanged(
            options.client,
            state.journal,
            initial.model_key,
            "initial restore model",
          );
          addPhase(state, "initial_restore_binding_revalidated");
        }
        addPhase(state, "initial_restore_started");
        if (initial) {
          const restoreController = new AbortController();
          try {
            await journaledOperation(
              state,
              { kind: "load", label: "initial model restore", identifier: initial.identifier },
              () => options.client.llm.load(initial.selected_variant, {
                identifier: initial.identifier,
                config: clone(initial.load_config),
                deviceIdentifier: null,
                signal: restoreController.signal,
                ...(initial.ttl_ms === null ? {} : { ttl: initial.ttl_ms / 1000 }),
              }),
              options.timeouts.loadMs,
              "initial model restore",
              restoreController,
            );
          } catch (error) {
            if ((error instanceof OperationDeadlineError && !error.operationSettled)
                || error.operationUncertain) {
              unsafeUnsettledOperation = true;
            }
            throw error;
          }
        }
        addPhase(state, "initial_restored");
        await verifyRestoration(options.client, initial);
        addPhase(state, "restore_verified");
        const finalBinding = await assertAllBindingsUnchanged(
          options.client,
          state.journal,
          [options.targetModelKey, ...(initial ? [initial.model_key] : [])],
          "post-restoration binding",
        );
        state.audit.engine_binding_post = finalBinding.engine;
        addPhase(state, "engine_bound_post");
        state.audit.artifact_fingerprints_final = finalBinding.artifacts;
        addPhase(state, "artifact_fingerprint_final");
        restored = true;
      } else if (initial) {
        const stable = await stableLoadedState(options.client, options.idleSampleDelayMs);
        if (stable.snapshots.length !== 1) {
          throw new LifecycleError("initial unload outcome is not safely recoverable inline");
        }
        assertSnapshotPair(initial, stable.snapshots[0], "initial model after failed unload");
        restored = true;
      }
    } catch (error) {
      if (unsafeUnsettledOperation) {
        const earlier = primaryError;
        primaryError = new LifecycleError(
          `a lifecycle operation remains unsettled; no subsequent load was issued and the recovery journal is retained${
            earlier ? `; transaction failure: ${earlier.message}; recovery failure: ${error.message}` : ""
          }`,
          { cause: new AggregateError([...(earlier ? [earlier] : []), error]) },
        );
      } else if (primaryError && primaryError !== error) {
        primaryError = new LifecycleError(
          `transaction failure: ${primaryError.message}; recovery failure: ${error.message}; initial state was not restored`,
          { cause: new AggregateError([primaryError, error]) },
        );
      } else {
        primaryError = primaryError || error;
      }
      if (ownedCleanupFailed) {
        primaryError = primaryError || new LifecycleError("owned cleanup failed");
      }
    }
  }

  if (artifactError) primaryError = primaryError || artifactError;
  const canRemoveJournal = state.journalCreated
    && (!state.journal.mutation_started || restored)
    && !unsafeUnsettledOperation && !ownedCleanupFailed;
  if (canRemoveJournal) {
    if (primaryError && state.journal.mutation_started) {
      state.audit.phases.push("transaction_failed_recovered");
    }
    try {
      removeJournal(options.journalPath);
      state.journalCreated = false;
      state.audit.phases.push("journal_removed");
    } catch (error) {
      primaryError = primaryError
        ? new LifecycleError(
          `transaction failure: ${primaryError.message}; journal finalization failure: ${error.message}`,
          { cause: new AggregateError([primaryError, error]) },
        )
        : error;
    }
  }

  if (lock) {
    try {
      if (unsafeUnsettledOperation) {
        retainLock(lock);
        state.audit.phases.push("lock_retained_for_unsettled_operation");
      } else {
        releaseLock(options.lockPath, lock);
        state.audit.phases.push("lock_released");
      }
    } catch (error) {
      primaryError = primaryError || error;
    }
  }

  if (primaryError) throw attachAudit(primaryError, state.audit);
  return { ...clone(state.audit), callback_result: callbackResult };
}

async function parkLoadedCandidate(rawOptions) {
  const options = normalizedParkOptions(rawOptions);
  const state = {
    audit: {
      schema_version: 1,
      kind: "park",
      phases: [],
      resource_samples: [],
      pressure_relief_policy: (
        "Low free-memory and free-swap values are permitted only for this unload-only operation; "
        + "finite metrics, zero throttled pages, CPU-load safety, artifact identity, and runtime "
        + "binding remain mandatory."
      ),
      artifact_fingerprint_scope: (
        "Normalized SDK downloaded-model identity metadata; not model-file content bytes."
      ),
      limitation: (
        "SDK unload has no AbortSignal; an unsettled deadline retains the canonical journal and lock."
      ),
    },
    journal: {
      schema_version: JOURNAL_SCHEMA_VERSION,
      kind: "park",
      park_snapshot: null,
      artifact_fingerprints_pre: null,
      engine_binding_pre: null,
      operation_pending: null,
      phase: "created",
      mutation_started: false,
    },
    journalPath: options.journalPath,
    journalCreated: false,
  };
  let lock;
  let primaryError = null;
  let unsafeUnsettledOperation = false;

  const gate = async (observeSignal = true) => {
    if (observeSignal && options.signal?.aborted) {
      throw new LifecycleError("park operation was interrupted");
    }
    const sample = validatePressureReliefResources(await options.resourceProbe());
    state.audit.resource_samples.push(sample);
  };

  try {
    lock = acquireLock(options.lockPath);
    state.audit.phases.push("lock_acquired");
    writeNewJournal(options.journalPath, state.journal);
    state.journalCreated = true;
    addPhase(state, "journal_created");

    await gate();
    addPhase(state, "pressure_relief_resource_pre");

    const first = await loadedSnapshot(options.client);
    addPhase(state, "park_snapshot_idle_1");
    await sleep(options.idleSampleDelayMs);
    const second = await loadedSnapshot(options.client);
    addPhase(state, "park_snapshot_idle_2");
    if (first.snapshots.length !== 1 || second.snapshots.length !== 1) {
      throw new LifecycleError("park requires exactly one loaded reviewed candidate model");
    }
    assertSnapshotPair(first.snapshots[0], second.snapshots[0], "park candidate");
    const parkedSnapshot = second.snapshots[0];
    validateParkCandidateSnapshot(parkedSnapshot);
    state.audit.parked_snapshot = clone(parkedSnapshot);
    state.journal.park_snapshot = clone(parkedSnapshot);
    addPhase(state, "park_snapshot_captured");

    const modelKeys = [parkedSnapshot.model_key];
    const artifactPre = await downloadedArtifactFingerprints(options.client, modelKeys);
    state.audit.artifact_fingerprints_pre = artifactPre;
    state.journal.artifact_fingerprints_pre = artifactPre;
    addPhase(state, "artifact_fingerprint_pre");
    const enginePre = await captureEngineBinding(options.client, modelKeys);
    state.audit.engine_binding_pre = enginePre;
    state.journal.engine_binding_pre = enginePre;
    addPhase(state, "engine_bound_pre");

    const readyToUnload = await twoIdleSamples(options.client, options.idleSampleDelayMs);
    if (readyToUnload.snapshots.length !== 1) {
      throw new LifecycleError("park candidate disappeared before unload");
    }
    assertSnapshotPair(parkedSnapshot, readyToUnload.snapshots[0], "park candidate before unload");
    validateParkCandidateSnapshot(readyToUnload.snapshots[0]);
    addPhase(state, "park_idle_revalidated");
    if (options.signal?.aborted) throw new LifecycleError("park operation was interrupted");

    state.journal.mutation_started = true;
    addPhase(state, "park_unload_started");
    try {
      await journaledOperation(
        state,
        { kind: "unload", label: "park candidate unload", identifier: parkedSnapshot.identifier },
        () => readyToUnload.handles[0].unload(), options.timeouts.unloadMs,
        "park candidate unload",
      );
    } catch (error) {
      if ((error instanceof OperationDeadlineError && !error.operationSettled)
          || error.operationUncertain) {
        unsafeUnsettledOperation = true;
      }
      throw error;
    }
    addPhase(state, "park_unloaded");

    await assertZeroLoaded(options.client, "park unload first sample");
    addPhase(state, "park_zero_verified_1");
    await sleep(options.idleSampleDelayMs);
    await assertZeroLoaded(options.client, "park unload second sample");
    addPhase(state, "park_zero_verified_2");

    let artifactPost;
    try {
      artifactPost = await downloadedArtifactFingerprints(options.client, modelKeys);
    } catch (error) {
      throw new LifecycleError(
        `artifact fingerprint changed during park operation: ${error.message}`,
        { cause: error },
      );
    }
    state.audit.artifact_fingerprints_post = artifactPost;
    addPhase(state, "artifact_fingerprint_post");
    if (!equalCanonical(artifactPost, state.journal.artifact_fingerprints_pre)) {
      throw new LifecycleError("artifact fingerprint changed during park operation");
    }
    const enginePost = await captureEngineBinding(options.client, modelKeys);
    state.audit.engine_binding_post = enginePost;
    addPhase(state, "engine_bound_post");
    if (!equalCanonical(enginePost, state.journal.engine_binding_pre)) {
      throw new LifecycleError("runtime engine selection changed during park operation");
    }

    await gate(false);
    addPhase(state, "pressure_relief_resource_post");
    await assertZeroLoaded(options.client, "park final first sample");
    addPhase(state, "park_final_zero_verified_1");
    await sleep(options.idleSampleDelayMs);
    await assertZeroLoaded(options.client, "park final second sample");
    addPhase(state, "park_final_zero_verified_2");
    removeJournal(options.journalPath);
    state.journalCreated = false;
    state.audit.phases.push("journal_removed");
  } catch (error) {
    primaryError = error;
  }

  if (state.journalCreated && !state.journal.mutation_started) {
    try {
      removeJournal(options.journalPath);
      state.journalCreated = false;
      state.audit.phases.push("journal_removed_pre_mutation");
    } catch (error) {
      primaryError = primaryError
        ? new LifecycleError(
          `park failure: ${primaryError.message}; journal finalization failure: ${error.message}`,
          { cause: new AggregateError([primaryError, error]) },
        )
        : error;
    }
  }

  if (lock) {
    try {
      if (unsafeUnsettledOperation) {
        retainLock(lock);
        state.audit.phases.push("lock_retained_for_unsettled_operation");
      } else {
        releaseLock(options.lockPath, lock);
        state.audit.phases.push("lock_released");
      }
    } catch (error) {
      primaryError = primaryError || error;
    }
  }

  if (unsafeUnsettledOperation) {
    primaryError = new LifecycleError(
      `park unload remains unsettled; canonical journal and lock retained; ${primaryError.message}`,
      { cause: primaryError },
    );
  }
  if (primaryError) throw attachAudit(primaryError, state.audit);
  return clone(state.audit);
}

function validateParkRecoveryJournal(journal) {
  if (journal.kind !== "park" || typeof journal.mutation_started !== "boolean") {
    throw new LifecycleError("park recovery journal kind or mutation boundary is invalid");
  }
  if (!Object.hasOwn(journal, "operation_pending")) {
    throw new LifecycleError("park recovery journal lacks durable operation state");
  }
  if (journal.operation_pending !== null) validatePendingOperation(journal.operation_pending);
  if (journal.callback_process_group !== undefined && journal.callback_process_group !== null) {
    throw new LifecycleError("park recovery journal must not own a callback process group");
  }
  if (!journal.mutation_started) return null;
  const snapshot = requirePlainObject(journal.park_snapshot, "park recovery snapshot");
  validateParkCandidateSnapshot(snapshot);
  if (!journal.artifact_fingerprints_pre || !journal.engine_binding_pre) {
    throw new LifecycleError("mutated park recovery journal binding is incomplete");
  }
  if (journal.operation_pending !== null
      && (journal.operation_pending.kind !== "unload"
        || journal.operation_pending.identifier !== snapshot.identifier)) {
    throw new LifecycleError("park pending operation does not match its exact snapshot");
  }
  return snapshot;
}

async function recoverParkJournal(options, journal, audit) {
  audit.resource_samples = [];
  if (!journal.mutation_started) {
    audit.phases.push("park_pre_mutation_crash_proven");
    removeJournal(options.journalPath);
    audit.phases.push("journal_removed");
    return;
  }

  const resourceProbe = options.resourceProbe || productionResourceProbe;
  audit.resource_samples.push(validatePressureReliefResources(await resourceProbe()));
  audit.phases.push("pressure_relief_resource_pre");
  const delayMs = options.idleSampleDelayMs ?? DEFAULT_IDLE_SAMPLE_DELAY_MS;
  const firstState = await twoIdleSamples(options.client, delayMs);
  audit.phases.push("park_recovery_state_sampled_pre_binding");
  const snapshot = journal.park_snapshot;
  if (firstState.snapshots.length === 1) {
    if (!equalCanonical(snapshot, firstState.snapshots[0])) {
      throw new LifecycleError("park recovery found an unknown loaded model");
    }
    validateParkCandidateSnapshot(firstState.snapshots[0]);
  }

  const modelKeys = [snapshot.model_key];
  const artifacts = await downloadedArtifactFingerprints(options.client, modelKeys);
  if (!equalCanonical(artifacts, journal.artifact_fingerprints_pre)) {
    throw new LifecycleError("artifact fingerprint changed since the interrupted park operation");
  }
  const engines = await captureEngineBinding(options.client, modelKeys);
  if (!equalCanonical(engines, journal.engine_binding_pre)) {
    throw new LifecycleError("runtime engine selection changed since the interrupted park operation");
  }
  audit.phases.push("park_bindings_verified");

  audit.resource_samples.push(validatePressureReliefResources(await resourceProbe()));
  audit.phases.push("pressure_relief_resource_post");
  const finalState = await twoIdleSamples(options.client, delayMs);
  audit.phases.push("park_recovery_state_sampled_post_binding");
  if (firstState.snapshots.length !== finalState.snapshots.length) {
    throw new LifecycleError("park recovery state changed while bindings were verified");
  }
  if (finalState.snapshots.length === 0) {
    audit.phases.push("park_zero_proven");
  } else if (finalState.snapshots.length === 1) {
    assertSnapshotPair(snapshot, finalState.snapshots[0], "park recovery unchanged candidate");
    audit.phases.push("park_no_mutation_proven");
  } else {
    throw new LifecycleError("park recovery found an unknown loaded state");
  }

  removeJournal(options.journalPath);
  audit.phases.push("journal_removed");
}

function validateRecoveryJournal(journal) {
  if (journal.kind !== undefined && journal.kind !== "transaction") {
    throw new LifecycleError("recovery journal kind is unsupported");
  }
  const target = MODEL_SPECS[journal.target_model_key];
  if (!target || journal.selected_variant !== target.selectedVariant) {
    throw new LifecycleError("recovery journal target is outside the reviewed exact variants");
  }
  const expectedIdentifier = ownedIdentifier(journal.transaction_id, journal.target_model_key);
  if (journal.owned_identifier !== expectedIdentifier
      || typeof journal.mutation_started !== "boolean") {
    throw new LifecycleError("recovery journal ownership or mutation boundary is incomplete");
  }
  loadProfile(journal.target_model_key, journal.profile);
  let ownership = null;
  if (journal.mutation_started) {
    if (!Object.hasOwn(journal, "owned_target_ownership")
        || !Object.hasOwn(journal, "owned_target_ownership_sha256")) {
      throw new LifecycleError("recovery journal lacks durable target ownership fields");
    }
    ownership = journalTargetOwnership(
      journal, target, expectedIdentifier, journal.profile,
    );
    if (ownership === null && journal.owned_target_ownership_sha256 !== null) {
      throw new LifecycleError("empty target ownership has a non-empty digest");
    }
  }
  if (journal.mutation_started
      && (!journal.artifact_fingerprints_pre || !journal.engine_binding_pre)) {
    throw new LifecycleError("mutated recovery journal binding is incomplete");
  }
  if (journal.mutation_started) {
    if (typeof journal.initial_state_had_model !== "boolean"
        || typeof journal.initial_snapshot_sha256 !== "string"
        || journal.initial_snapshot_sha256 !== canonicalSha256(journal.initial_snapshot)) {
      throw new LifecycleError("initial recovery snapshot identity or digest is incomplete");
    }
    if ((journal.initial_snapshot !== null) !== journal.initial_state_had_model) {
      throw new LifecycleError("initial recovery snapshot presence contradicts its captured state");
    }
    if (journal.initial_snapshot !== null) validateInitialSnapshot(journal.initial_snapshot);
  }
  if (journal.callback_process_group !== undefined && journal.callback_process_group !== null) {
    validateProcessGroupRecord(journal.callback_process_group);
  }
  if (!("operation_pending" in journal)) {
    throw new LifecycleError("recovery journal lacks durable operation state");
  }
  if (journal.operation_pending !== null) validatePendingOperation(journal.operation_pending);
  return { target, ownership };
}

async function recoverLifecycleTransaction(options) {
  requirePlainObject(options, "recovery options");
  validateCanonicalStatePaths(options.journalPath, options.lockPath);
  const audit = { schema_version: 1, kind: "recovery", phases: [] };
  let lock;
  let error = null;
  let unsafeUnsettledOperation = false;
  try {
    lock = acquireLock(options.lockPath, true);
    audit.phases.push("lock_acquired");
    if (lock.stale) audit.phases.push("dead_pid_lock_replaced");
    const journal = readJournal(options.journalPath);
    const parkJournal = journal.kind === "park";
    const validated = parkJournal
      ? validateParkRecoveryJournal(journal) : validateRecoveryJournal(journal);
    const target = parkJournal ? validated : validated.target;
    const ownership = parkJournal ? null : validated.ownership;
    audit.journal_kind = parkJournal ? "park" : "transaction";
    if (!parkJournal) {
      audit.transaction_id = journal.transaction_id;
      audit.owned_identifier = journal.owned_identifier;
    }
    audit.phases.push("journal_read");
    if (journal.operation_pending !== null) {
      unsafeUnsettledOperation = true;
      throw new LifecycleError(
        "automatic recovery is blocked by a crash-uncertain SDK operation; "
        + "restart LM Studio and perform explicit manual recovery",
      );
    }
    if (journal.callback_process_group !== undefined && journal.callback_process_group !== null) {
      const record = validateProcessGroupRecord(journal.callback_process_group);
      const probe = options.processGroupProbe || productionProcessGroupProbe;
      const terminate = options.processGroupTerminate
        || (owned => productionProcessGroupTerminate(
          owned, options.timeouts?.processGroupMs ?? 5_000,
        ));
      try {
        const before = normalizeProcessGroupState(await probe(record));
        audit.phases.push("callback_process_group_probed");
        if (before.alive) {
          if (!before.owned) {
            unsafeUnsettledOperation = true;
            throw new LifecycleError("callback process group is alive but ownership is ambiguous");
          }
          await terminate(record);
          audit.phases.push("callback_process_group_terminated");
        }
        const after = normalizeProcessGroupState(await probe(record));
        if (after.alive) {
          unsafeUnsettledOperation = true;
          throw new LifecycleError("callback process group remains alive; recovery cannot mutate models");
        }
        journal.callback_process_group = null;
        updateJournal(options.journalPath, journal);
        audit.phases.push("callback_process_group_quiescent");
      } catch (caught) {
        unsafeUnsettledOperation = true;
        throw caught;
      }
    }
    if (parkJournal) {
      await recoverParkJournal(options, journal, audit);
    } else if (!journal.mutation_started) {
      audit.phases.push("pre_mutation_crash_proven");
      removeJournal(options.journalPath);
      audit.phases.push("journal_removed");
    } else {
      const resourceProbe = options.resourceProbe || productionResourceProbe;
      validateResources(await resourceProbe());
      audit.phases.push("host_gate_pre");
      const delayMs = options.idleSampleDelayMs ?? DEFAULT_IDLE_SAMPLE_DELAY_MS;
      const current = await twoIdleSamples(options.client, delayMs);
      audit.phases.push("stable_state_sampled");
      const keys = [journal.target_model_key];
      if (journal.initial_snapshot) keys.push(journal.initial_snapshot.model_key);
      const artifacts = await downloadedArtifactFingerprints(options.client, keys);
      if (!equalCanonical(artifacts, journal.artifact_fingerprints_pre)) {
        throw new LifecycleError("artifact fingerprint changed since the interrupted transaction");
      }
      const engines = await captureEngineBinding(options.client, keys);
      if (!equalCanonical(engines, journal.engine_binding_pre)) {
        throw new LifecycleError("runtime engine selection changed since the interrupted transaction");
      }
      audit.phases.push("bindings_verified");
      const timeouts = {
        loadMs: options.timeouts?.loadMs ?? DEFAULT_LOAD_TIMEOUT_MS,
        unloadMs: options.timeouts?.unloadMs ?? DEFAULT_UNLOAD_TIMEOUT_MS,
      };

      if (current.snapshots.length === 1) {
        const loaded = current.snapshots[0];
        if (journal.initial_snapshot
            && equalCanonical(
              restorableSnapshot(loaded),
              restorableSnapshot(journal.initial_snapshot),
            )) {
          audit.phases.push("initial_already_restored");
        } else if (ownership !== null) {
          assertTargetOwnership(loaded, ownership, "recovery loaded target");
          const readyToUnload = await twoIdleSamples(options.client, delayMs);
          if (readyToUnload.snapshots.length !== 1) {
            throw new LifecycleError("recovery owned model disappeared before unload");
          }
          assertSnapshotPair(
            loaded,
            readyToUnload.snapshots[0],
            "recovery owned model before unload",
          );
          assertTargetOwnership(
            readyToUnload.snapshots[0], ownership, "recovery owned target before unload",
          );
          audit.phases.push("owned_idle_revalidated");
          audit.phases.push("owned_unload_started");
          try {
            await journaledOperation(
              { journalPath: options.journalPath, journal },
              { kind: "unload", label: "recovery owned unload", identifier: loaded.identifier },
              () => readyToUnload.handles[0].unload(), timeouts.unloadMs,
              "recovery owned unload",
            );
          } catch (caught) {
            if ((caught instanceof OperationDeadlineError && !caught.operationSettled)
                || caught.operationUncertain) {
              unsafeUnsettledOperation = true;
            }
            throw caught;
          }
          audit.phases.push("owned_unloaded");
          await assertZeroLoaded(options.client, "recovery owned unload");
          audit.phases.push("zero_verified");
        } else {
          throw new LifecycleError("recovery found an unknown or unowned loaded model");
        }
      }

      const afterOwned = await loadedSnapshot(options.client);
      if (afterOwned.snapshots.length === 0 && journal.initial_snapshot) {
        const restoreResources = validateResources(await resourceProbe());
        audit.initial_restore_projection = validateProjectedLoadHeadroom(
          restoreResources,
          journal.initial_snapshot.model_key,
          profileForSnapshot(journal.initial_snapshot),
          journal.initial_snapshot.context_length,
        );
        audit.phases.push("host_gate_restore");
        const initial = journal.initial_snapshot;
        await assertModelBindingUnchanged(
          options.client,
          journal,
          initial.model_key,
          "recovery initial restore model",
        );
        audit.phases.push("initial_restore_binding_revalidated");
        audit.phases.push("initial_restore_started");
        const restoreController = new AbortController();
        try {
          await journaledOperation(
            { journalPath: options.journalPath, journal },
            { kind: "load", label: "recovery initial restore", identifier: initial.identifier },
            () => options.client.llm.load(initial.selected_variant, {
              identifier: initial.identifier,
              config: clone(initial.load_config),
              deviceIdentifier: null,
              signal: restoreController.signal,
              ...(initial.ttl_ms === null ? {} : { ttl: initial.ttl_ms / 1000 }),
            }),
            timeouts.loadMs,
            "recovery initial restore",
            restoreController,
          );
        } catch (caught) {
          if ((caught instanceof OperationDeadlineError && !caught.operationSettled)
              || caught.operationUncertain) {
            unsafeUnsettledOperation = true;
          }
          throw caught;
        }
        audit.phases.push("initial_restored");
      }
      await verifyRestoration(options.client, journal.initial_snapshot);
      audit.phases.push("restore_verified");
      const finalBindings = await assertAllBindingsUnchanged(
        options.client,
        journal,
        keys,
        "post-recovery restoration binding",
      );
      audit.artifact_fingerprints_final = finalBindings.artifacts;
      audit.engine_binding_final = finalBindings.engine;
      audit.phases.push("restoration_bindings_verified");
      removeJournal(options.journalPath);
      audit.phases.push("journal_removed");
    }
  } catch (caught) {
    error = unsafeUnsettledOperation
      ? new LifecycleError(
        `a recovery lifecycle operation remains unsettled; lock and journal retained; ${caught.message}`,
        { cause: caught },
      )
      : caught;
  }
  if (lock) {
    try {
      if (unsafeUnsettledOperation) {
        retainLock(lock);
        audit.phases.push("lock_retained_for_unsettled_operation");
      } else {
        releaseLock(options.lockPath, lock);
        audit.phases.push("lock_released");
      }
    } catch (caught) {
      error = error || caught;
    }
  }
  if (error) throw attachAudit(error, audit);
  return audit;
}

async function readOnlyPlan(client, resourceProbe = productionResourceProbe) {
  const sample = validateResources(await resourceProbe());
  const current = await loadedSnapshot(client);
  const rows = await client.system.listDownloadedModels("llm");
  const candidates = [];
  for (const spec of Object.values(MODEL_SPECS)) {
    const matches = rows.filter(row => row && row.modelKey === spec.modelKey);
    if (matches.length !== 1) throw new LifecycleError(`candidate is missing or ambiguous: ${spec.modelKey}`);
    candidates.push({
      ...validateDownloadedRow(matches[0], spec),
      profiles: spec.backend === "GGUF" ? ["f16", "q8_0"] : ["mlx-native"],
    });
  }
  const engines = await captureEngineBinding(client, Object.keys(MODEL_SPECS));
  return {
    schema_version: 1,
    mode: "read-only-plan",
    mutation_performed: false,
    resources: sample,
    loaded: current.snapshots,
    candidates,
    engine_binding: engines,
    artifact_fingerprint_scope: (
      "Normalized SDK downloaded-model identity metadata; not model-file content bytes."
    ),
    unload_timeout_boundary: (
      "SDK 1.5.0 exposes AbortSignal for load but not unload. An unload deadline "
      + "retains the recovery journal and forbids a new load until stable exact state is re-established."
    ),
  };
}

function validateEndpoint(value) {
  if (typeof value !== "string" || !value) {
    throw new LifecycleError("SDK endpoint must be a bare loopback WebSocket URL");
  }
  let endpoint;
  try {
    endpoint = new URL(value);
  } catch (error) {
    throw new LifecycleError("SDK endpoint must be a bare loopback WebSocket URL", { cause: error });
  }
  const loopback = new Set(["127.0.0.1", "::1", "[::1]"]);
  if (!new Set(["ws:", "wss:"]).has(endpoint.protocol) || !loopback.has(endpoint.hostname)
      || endpoint.username || endpoint.password || endpoint.search || endpoint.hash
      || (endpoint.pathname !== "/" && endpoint.pathname !== "")) {
    throw new LifecycleError("SDK endpoint must be a bare loopback WebSocket URL");
  }
  return endpoint.toString().replace(/\/$/u, "");
}

function discoverSdkEntry() {
  const plugins = path.join(os.homedir(), ".lmstudio", "extensions", "plugins");
  const entries = [];
  const walk = directory => {
    for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
      const child = path.join(directory, item.name);
      if (item.isDirectory()) walk(child);
      else if (item.isFile() && child.endsWith(`${path.sep}@lmstudio${path.sep}sdk${path.sep}dist${path.sep}index.cjs`)) {
        entries.push(fs.realpathSync(child));
      }
    }
  };
  if (!fs.existsSync(plugins)) throw new LifecycleError("official LM Studio SDK installation is unavailable");
  walk(plugins);
  const unique = [...new Set(entries)].sort();
  if (unique.length === 0) throw new LifecycleError("official LM Studio SDK CommonJS entry is unavailable");
  const digests = new Set(unique.map(file => crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex")));
  if (digests.size !== 1) throw new LifecycleError("installed official LM Studio SDK copies disagree");
  return unique[0];
}

function createClient(endpoint) {
  const validatedEndpoint = validateEndpoint(endpoint);
  const sdkReceipt = verifyReviewedSdkEntry(discoverSdkEntry());
  const pluginsRoot = fs.realpathSync(
    path.join(os.homedir(), ".lmstudio", "extensions", "plugins"),
  );
  const preloadedPluginModule = Object.keys(require.cache).find(candidate => {
    const resolved = fs.realpathSync(candidate);
    return resolved === pluginsRoot || resolved.startsWith(`${pluginsRoot}${path.sep}`);
  });
  if (preloadedPluginModule) {
    throw new LifecycleError(
      "refusing to construct an SDK client from a previously executed plugin module cache",
    );
  }
  const currentIdentity = immutableFileIdentity(
    fs.lstatSync(sdkReceipt.entryPath, { bigint: true }),
  );
  if (!equalCanonical(currentIdentity, sdkReceipt.fileIdentity)
      || sha256FileSync(sdkReceipt.entryPath) !== sdkReceipt.entrySha256) {
    throw new LifecycleError("reviewed LM Studio SDK entry changed immediately before require");
  }
  const sdk = require(sdkReceipt.entryPath);
  if (!sdk || typeof sdk.LMStudioClient !== "function") {
    throw new LifecycleError("official LM Studio SDK entry is invalid");
  }
  const postRequireReceipt = verifyReviewedSdkEntry(sdkReceipt.entryPath);
  if (postRequireReceipt.entryPath !== sdkReceipt.entryPath
      || postRequireReceipt.entrySha256 !== sdkReceipt.entrySha256
      || postRequireReceipt.closureSha256 !== sdkReceipt.closureSha256
      || postRequireReceipt.dependencyClosureSha256 !== sdkReceipt.dependencyClosureSha256
      || !equalCanonical(postRequireReceipt.fileIdentity, sdkReceipt.fileIdentity)) {
    throw new LifecycleError("reviewed LM Studio SDK binding changed during require");
  }
  const client = new sdk.LMStudioClient({
    baseUrl: validatedEndpoint,
    verboseErrorMessages: false,
    logger: { debug() {}, info() {}, warn() {}, error() {} },
  });
  CLIENT_SDK_RECEIPTS.set(client, sdkReceipt);
  CLIENT_ENDPOINT_RECEIPTS.set(client, Object.freeze({
    endpoint: validatedEndpoint,
    source: "reviewed-production-construction",
  }));
  PRODUCTION_CLIENTS.add(client);
  return client;
}

async function disposeClient(client) {
  if (client && typeof client[Symbol.asyncDispose] === "function") {
    await client[Symbol.asyncDispose]();
  }
}

function parseCli(argv) {
  const args = [...argv];
  const command = args.shift();
  if (!new Set(["plan", "run", "park", "recover"]).has(command)) {
    throw new LifecycleError("usage: lifecycle plan|run|park|recover [options]");
  }
  const values = {
    command,
    endpoint: "ws://127.0.0.1:1234",
    ...canonicalStatePaths(),
  };
  const callbackIndex = args.indexOf("--");
  values.callbackArgv = callbackIndex === -1 ? [] : args.splice(callbackIndex + 1);
  if (callbackIndex !== -1) args.splice(callbackIndex, 1);
  for (let index = 0; index < args.length; index += 1) {
    const key = args[index];
    if (key === "--allow-model-mutation") {
      values.allowMutation = true;
      continue;
    }
    const field = {
      "--endpoint": "endpoint", "--target": "targetModelKey", "--profile": "profileName",
      "--transaction-id": "transactionId", "--journal": "journalPath", "--lock": "lockPath",
      "--callback-timeout-ms": "callbackTimeoutRaw",
    }[key];
    if (!field || index + 1 >= args.length) throw new LifecycleError(`unknown or incomplete option: ${key}`);
    values[field] = args[++index];
  }
  if (values.callbackTimeoutRaw !== undefined) {
    if (!/^[0-9]+$/u.test(values.callbackTimeoutRaw)) {
      throw new LifecycleError("callback timeout must be a whole number of milliseconds");
    }
    values.callbackTimeoutMs = validateCallbackTimeoutMs(Number(values.callbackTimeoutRaw));
    delete values.callbackTimeoutRaw;
  }
  if (command !== "run" && values.callbackTimeoutMs !== undefined) {
    throw new LifecycleError("callback timeout is only valid for run");
  }
  return values;
}

function validateCallbackTimeoutMs(value) {
  if (!Number.isSafeInteger(value) || value <= 0 || value > MAX_CALLBACK_TIMEOUT_MS) {
    throw new LifecycleError(
      `callback timeout must be between 1 and ${MAX_CALLBACK_TIMEOUT_MS} milliseconds`,
    );
  }
  return value;
}

function sdkCallbackBinding(value) {
  const receipt = requirePlainObject(value, "private SDK creation receipt");
  if (typeof receipt.entryPath !== "string" || !path.isAbsolute(receipt.entryPath)
      || receipt.entrySha256 !== REVIEWED_SDK.entrySha256
      || receipt.closureSha256 !== REVIEWED_SDK.closureSha256
      || receipt.dependencyClosureSha256 !== REVIEWED_SDK.dependencyClosureSha256) {
    throw new LifecycleError("private SDK creation receipt differs from the reviewed SDK build");
  }
  return Object.freeze({
    entryPath: receipt.entryPath,
    entrySha256: receipt.entrySha256,
    closureSha256: receipt.closureSha256,
    dependencyClosureSha256: receipt.dependencyClosureSha256,
  });
}

function callbackBindingEnvironment(context) {
  const value = requirePlainObject(context, "callback context");
  const sdkBinding = sdkCallbackBinding(CALLBACK_CONTEXT_SDK_BINDINGS.get(value));
  const endpoint = validateEndpoint(value.endpoint);
  const snapshot = requirePlainObject(value.effectiveSnapshot, "verified callback snapshot");
  const loadConfig = requirePlainObject(snapshot.load_config, "verified callback load config");
  normalizeProcessingState(snapshot.processing_state);
  for (const field of [
    "identifier", "model_key", "selected_variant", "instance_reference",
    "indexed_model_identifier",
  ]) {
    if (typeof snapshot[field] !== "string" || !snapshot[field]) {
      throw new LifecycleError(`verified callback snapshot omitted ${field}`);
    }
  }
  if (!Number.isSafeInteger(snapshot.context_length) || snapshot.context_length <= 0
      || snapshot.device_identifier !== null
      || snapshot.identifier !== value.identifier
      || snapshot.model_key !== value.modelKey
      || snapshot.selected_variant !== value.selectedVariant) {
    throw new LifecycleError("callback identity differs from the verified snapshot");
  }
  validateParkCandidateSnapshot(snapshot);
  if (typeof value.profile !== "string" || !value.profile) {
    throw new LifecycleError("callback profile is invalid");
  }
  return {
    LMSTUDIO_BAKEOFF_ENDPOINT: endpoint,
    LMSTUDIO_BAKEOFF_IDENTIFIER: snapshot.identifier,
    LMSTUDIO_BAKEOFF_MODEL_KEY: snapshot.model_key,
    LMSTUDIO_BAKEOFF_SELECTED_VARIANT: snapshot.selected_variant,
    LMSTUDIO_BAKEOFF_PROFILE: value.profile,
    LMSTUDIO_BAKEOFF_SNAPSHOT_SHA256: canonicalSha256(snapshot),
    LMSTUDIO_BAKEOFF_INSTANCE_REFERENCE: snapshot.instance_reference,
    LMSTUDIO_BAKEOFF_INDEXED_MODEL_IDENTIFIER: snapshot.indexed_model_identifier,
    LMSTUDIO_BAKEOFF_CONTEXT_LENGTH: String(snapshot.context_length),
    LMSTUDIO_BAKEOFF_LOAD_CONFIG_SHA256: canonicalSha256(loadConfig),
    LMSTUDIO_BAKEOFF_SDK_ENTRY_PATH: sdkBinding.entryPath,
    LMSTUDIO_BAKEOFF_SDK_ENTRY_SHA256: sdkBinding.entrySha256,
    LMSTUDIO_BAKEOFF_SDK_CLOSURE_SHA256: sdkBinding.closureSha256,
    LMSTUDIO_BAKEOFF_SDK_DEPENDENCY_CLOSURE_SHA256:
      sdkBinding.dependencyClosureSha256,
  };
}

const CALLBACK_SUPERVISOR_SOURCE = String.raw`
"use strict";
const fs = require("node:fs");
const {spawn} = require("node:child_process");
const gate = Buffer.alloc(16);
try {
  if (fs.readSync(3, gate, 0, gate.length, null) <= 0) process.exit(125);
} catch (_) { process.exit(125); }
const argv = process.argv.slice(1);
if (argv.length === 0) process.exit(126);
const child = spawn(argv[0], argv.slice(1), {shell: false, stdio: "inherit"});
let directResult = {code: 127, signal: null};
for (const signal of ["SIGHUP", "SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    try { child.kill(signal); } catch (_) {}
  });
}
const directDone = new Promise(resolve => {
  child.once("error", () => resolve());
  child.once("exit", (code, signal) => {
    directResult = {code, signal};
    resolve();
  });
});
function groupDescendantsRemain() {
  return new Promise(resolve => {
    const probe = spawn("/bin/ps", ["-axo", "pid=,pgid="], {
      shell: false, stdio: ["ignore", "pipe", "ignore"],
      env: {PATH: "/usr/bin:/bin", LC_ALL: "C"},
    });
    let output = "";
    probe.stdout.setEncoding("utf8");
    probe.stdout.on("data", chunk => { output += chunk; });
    probe.once("error", () => resolve(true));
    probe.once("close", () => {
      const remains = output.split("\n").some(line => {
        const match = /^\s*([0-9]+)\s+([0-9]+)\s*$/u.exec(line);
        if (!match) return false;
        const pid = Number(match[1]);
        const pgid = Number(match[2]);
        return pgid === process.pid && pid !== process.pid && pid !== probe.pid;
      });
      resolve(remains);
    });
  });
}
(async () => {
  await directDone;
  while (await groupDescendantsRemain()) {
    await new Promise(resolve => setTimeout(resolve, 25));
  }
  process.exitCode = directResult.signal === null && Number.isInteger(directResult.code)
    ? directResult.code : 128;
})().catch(() => { process.exitCode = 127; });
`;

function commandCallback(
  argv,
  timeoutMs = DEFAULT_CALLBACK_TIMEOUT_MS,
  terminationGraceMs = 5_000,
  resourceMonitorIntervalMs = 5_000,
) {
  if (!Array.isArray(argv) || argv.length === 0 || argv.some(value => typeof value !== "string" || !value)) {
    throw new LifecycleError("run requires a callback argv after --");
  }
  validateCallbackTimeoutMs(timeoutMs);
  if (!Number.isSafeInteger(terminationGraceMs) || terminationGraceMs <= 0
      || !Number.isSafeInteger(resourceMonitorIntervalMs) || resourceMonitorIntervalMs <= 0) {
    throw new LifecycleError("callback deadline or termination grace is invalid");
  }
  return context => new Promise((resolve, reject) => {
    const bindingEnvironment = callbackBindingEnvironment(context);
    const ownershipToken = crypto.randomBytes(32).toString("hex");
    const environment = {
      ...Object.fromEntries(["HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TMP", "TEMP", "PATH"]
        .filter(key => process.env[key] !== undefined).map(key => [key, process.env[key]])),
      ...bindingEnvironment,
      LMSTUDIO_BAKEOFF_PROCESS_TOKEN: ownershipToken,
    };
    const child = spawn(CALLBACK_SUPERVISOR_EXECUTABLE, [
      "-e", CALLBACK_SUPERVISOR_SOURCE, "--", ...argv,
    ], {
      shell: false, stdio: ["inherit", "inherit", "inherit", "pipe"],
      env: environment, detached: true,
    });
    let processGroupRecord = null;
    const hasRegistrationHooks = typeof context.registerProcessGroup === "function"
      || typeof context.clearProcessGroup === "function";
    let processGroupRegistered = false;
    let termination = null;
    let killTimer = null;
    let resourceTimer = null;
    let finished = false;
    const signalGroup = signal => {
      if (!Number.isSafeInteger(child.pid) || child.pid <= 0) return;
      try {
        process.kill(-child.pid, signal);
      } catch (error) {
        if (error.code !== "ESRCH" && error.code !== "EPERM") throw error;
      }
    };
    const groupAlive = () => {
      try {
        process.kill(-child.pid, 0);
        return true;
      } catch (error) {
        if (error.code === "ESRCH") return false;
        if (error.code === "EPERM") return true;
        throw error;
      }
    };
    const beginTermination = error => {
      if (termination) return;
      termination = error;
      signalGroup("SIGTERM");
      killTimer = setTimeout(() => signalGroup("SIGKILL"), terminationGraceMs);
    };
    const deadlineTimer = setTimeout(() => beginTermination(
      new LifecycleError("benchmark callback exceeded its deadline"),
    ), timeoutMs);
    const scheduleResourceSample = () => {
      if (finished || termination || typeof context.resourceProbe !== "function") return;
      resourceTimer = setTimeout(async () => {
        try {
          validateResources(await context.resourceProbe());
          if (finished) return;
          scheduleResourceSample();
        } catch (error) {
          if (finished) return;
          beginTermination(error instanceof LifecycleError
            ? error
            : new LifecycleError(`callback resource monitor failed: ${error.message}`, { cause: error }));
        }
      }, resourceMonitorIntervalMs);
    };
    scheduleResourceSample();
    const abortListener = () => beginTermination(
      new LifecycleError("benchmark callback was interrupted"),
    );
    if (context.signal) {
      if (context.signal.aborted) abortListener();
      else context.signal.addEventListener("abort", abortListener, { once: true });
    }
    const cleanListeners = () => {
      clearTimeout(deadlineTimer);
      if (killTimer !== null) clearTimeout(killTimer);
      if (resourceTimer !== null) clearTimeout(resourceTimer);
      if (context.signal) context.signal.removeEventListener("abort", abortListener);
    };
    child.once("error", error => {
      if (finished) return;
      finished = true;
      cleanListeners();
      try {
        if (processGroupRegistered) context.clearProcessGroup(processGroupRecord);
        reject(error);
      } catch (cleanupError) {
        reject(new LifecycleError(
          `callback spawn failure: ${error.message}; process-group journal cleanup failed: ${cleanupError.message}`,
          { cause: new AggregateError([error, cleanupError]) },
        ));
      }
    });
    child.once("exit", async (code, signal) => {
      if (finished) return;
      finished = true;
      cleanListeners();
      try {
        if (groupAlive()) {
          signalGroup("SIGTERM");
          await sleep(terminationGraceMs);
        }
        if (groupAlive()) {
          signalGroup("SIGKILL");
          await sleep(Math.min(1_000, terminationGraceMs));
        }
        if (groupAlive()) {
          throw new LifecycleError("benchmark callback process group did not quiesce");
        }
        if (processGroupRegistered) {
          context.clearProcessGroup(processGroupRecord);
          processGroupRegistered = false;
        }
        if (termination) reject(termination);
        else if (code === 0 && signal === null) resolve({ exit_code: 0 });
        else reject(new LifecycleError(`benchmark callback failed with code ${code} signal ${signal}`));
      } catch (error) {
        reject(error);
      }
    });
    child.stdio[3].once("error", error => {
      if (!finished) beginTermination(new LifecycleError(
        `callback start gate failed: ${error.message}`, { cause: error },
      ));
    });
    child.once("spawn", () => {
      try {
        const identity = processLeaderIdentity(child.pid);
        if (!identity || identity.leader_pid !== child.pid || identity.pgid !== child.pid
            || identity.uid !== process.getuid()
            || identity.leader_executable !== CALLBACK_SUPERVISOR_EXECUTABLE) {
          throw new LifecycleError("callback supervisor identity could not be bound safely");
        }
        processGroupRecord = validateProcessGroupRecord({
          ...identity,
          token: ownershipToken,
        });
        if (hasRegistrationHooks) {
          if (typeof context.registerProcessGroup !== "function"
              || typeof context.clearProcessGroup !== "function") {
            throw new LifecycleError("callback process-group journal hooks are incomplete");
          }
          context.registerProcessGroup(processGroupRecord);
          processGroupRegistered = true;
        }
        child.stdio[3].end("start\n");
      } catch (error) {
        child.stdio[3].destroy();
        beginTermination(error);
      }
    });
  });
}

async function withOfflineTestClient(options, operation, requireEndpoint = false) {
  requirePlainObject(options, "offline test-driver options");
  const client = options.client;
  if (!client || typeof client !== "object"
      || typeof options.testRuntimeIdentity !== "function") {
    throw new LifecycleError(
      "offline test driver requires an object client and explicit runtime-identity provider",
    );
  }
  if (PRODUCTION_CLIENTS.has(client) || CLIENT_SDK_RECEIPTS.has(client)
      || CLIENT_ENDPOINT_RECEIPTS.has(client)
      || OFFLINE_TEST_RUNTIME_IDENTITIES.has(client)) {
    throw new LifecycleError("offline test driver cannot accept a production or active client");
  }
  const endpoint = requireEndpoint
    ? validateEndpoint(options.testClientEndpoint ?? options.endpoint)
    : null;
  OFFLINE_TEST_RUNTIME_IDENTITIES.set(client, options.testRuntimeIdentity);
  CLIENT_SDK_RECEIPTS.set(client, OFFLINE_TEST_SDK_RECEIPT);
  if (endpoint !== null) {
    CLIENT_ENDPOINT_RECEIPTS.set(client, Object.freeze({
      endpoint,
      source: "structurally-separate-offline-test-driver",
    }));
  }
  try {
    return await operation();
  } finally {
    OFFLINE_TEST_RUNTIME_IDENTITIES.delete(client);
    CLIENT_SDK_RECEIPTS.delete(client);
    CLIENT_ENDPOINT_RECEIPTS.delete(client);
  }
}

function stripOfflineTestOptions(options) {
  const value = { ...options };
  delete value.testRuntimeIdentity;
  delete value.testClientEndpoint;
  return value;
}

const offlineTestDriver = Object.freeze({
  runTransaction(options) {
    return withOfflineTestClient(
      options,
      () => runLifecycleTransaction(stripOfflineTestOptions(options)),
      true,
    );
  },
  park(options) {
    return withOfflineTestClient(
      options,
      () => parkLoadedCandidate(stripOfflineTestOptions(options)),
    );
  },
  recover(options) {
    return withOfflineTestClient(
      options,
      () => recoverLifecycleTransaction(stripOfflineTestOptions(options)),
    );
  },
  plan(options) {
    return withOfflineTestClient(
      options,
      () => readOnlyPlan(options.client, options.resourceProbe),
    );
  },
  commandCallback(argv, timeoutMs, terminationGraceMs, resourceMonitorIntervalMs) {
    const callback = commandCallback(
      argv,
      timeoutMs,
      terminationGraceMs,
      resourceMonitorIntervalMs,
    );
    return context => {
      const testContext = { ...context };
      CALLBACK_CONTEXT_SDK_BINDINGS.set(testContext, OFFLINE_TEST_SDK_RECEIPT);
      let result;
      try {
        result = callback(testContext);
      } catch (error) {
        CALLBACK_CONTEXT_SDK_BINDINGS.delete(testContext);
        throw error;
      }
      return Promise.resolve(result).finally(() => {
        CALLBACK_CONTEXT_SDK_BINDINGS.delete(testContext);
      });
    };
  },
  parseCli,
});

async function main(argv = process.argv.slice(2)) {
  let client;
  let receivedSignal = null;
  let signalController = null;
  const signalHandlers = new Map();
  const resultCode = fallback => receivedSignal === "SIGINT"
    ? 130 : receivedSignal === "SIGTERM" ? 143 : fallback;
  try {
    const args = parseCli(argv);
    if (args.command === "plan") {
      if (args.allowMutation || args.callbackArgv.length) {
        throw new LifecycleError("plan does not accept mutation flags or callbacks");
      }
      client = createClient(args.endpoint);
      process.stdout.write(`${canonicalJson(await readOnlyPlan(client))}\n`);
      return 0;
    }
    if (!args.allowMutation) {
      throw new LifecycleError("mutation command requires --allow-model-mutation");
    }
    signalController = new AbortController();
    for (const name of ["SIGINT", "SIGTERM"]) {
      const handler = () => {
        if (receivedSignal === null) receivedSignal = name;
        signalController.abort();
      };
      signalHandlers.set(name, handler);
      process.on(name, handler);
    }
    client = createClient(args.endpoint);
    if (args.command === "run") {
      const result = await runLifecycleTransaction({
        client,
        endpoint: validateEndpoint(args.endpoint),
        targetModelKey: args.targetModelKey,
        profileName: args.profileName,
        transactionId: args.transactionId,
        callbackTimeoutMs: args.callbackTimeoutMs,
        journalPath: args.journalPath,
        lockPath: args.lockPath,
        callback: commandCallback(
          args.callbackArgv,
          args.callbackTimeoutMs ?? DEFAULT_CALLBACK_TIMEOUT_MS,
        ),
        signal: signalController.signal,
      });
      process.stdout.write(`${canonicalJson(result)}\n`);
      return resultCode(0);
    }
    if (args.command === "park") {
      if (args.callbackArgv.length || args.targetModelKey !== undefined
          || args.profileName !== undefined || args.transactionId !== undefined) {
        throw new LifecycleError("park accepts no callback, target, profile, or transaction id");
      }
      const result = await parkLoadedCandidate({
        client,
        journalPath: args.journalPath,
        lockPath: args.lockPath,
        signal: signalController.signal,
      });
      process.stdout.write(`${canonicalJson(result)}\n`);
      return resultCode(0);
    }
    if (args.callbackArgv.length) throw new LifecycleError("recover does not accept a callback");
    const result = await recoverLifecycleTransaction({
      client, journalPath: args.journalPath, lockPath: args.lockPath,
    });
    process.stdout.write(`${canonicalJson(result)}\n`);
    return resultCode(0);
  } catch (error) {
    process.stderr.write(`error: ${error.message}\n`);
    if (error.lifecycleAudit) process.stderr.write(`${canonicalJson(error.lifecycleAudit)}\n`);
    return resultCode(2);
  } finally {
    for (const [name, handler] of signalHandlers) process.removeListener(name, handler);
    await disposeClient(client);
  }
}

module.exports = {
  LifecycleError,
  MODEL_SPECS,
  REVIEWED_ENGINES,
  loadProfile,
  productionResourceProbe,
  productionProcessGroupProbe,
  offlineTestDriver,
};

if (require.main === module) {
  main().then(code => { process.exitCode = code; }).catch(error => {
    process.stderr.write(`error: ${error.message}\n`);
    process.exitCode = 2;
  });
}
