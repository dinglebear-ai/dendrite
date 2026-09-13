#!/usr/bin/env node
// Asserts the effective configuration and identity of already-loaded LM Studio
// models through the official SDK without loading, unloading, or predicting.
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

const WATCHER_VERSION = "lmstudio-sdk-watcher-v2";
const WATCHER_SCHEMA_VERSION = 2;
const MAX_WATCHER_LINE_BYTES = 65_536;
const RUNTIME_DEPENDENCIES = [
  "@lmstudio/lms-isomorphic", "chalk", "zod", "zod-to-json-schema",
];
const MAX_WATCHER_INTERVAL_MILLISECONDS = 2_147_483_647;
let cachedNodeRuntimeIdentity;

const LOAD_CONFIG_FIELDS = new Map([
  ["gpu", "gpu"],
  ["gpuStrictVramCap", "gpu_strict_vram_cap"],
  ["maxParallelPredictions", "max_parallel_predictions"],
  ["useUnifiedKvCache", "use_unified_kv_cache"],
  ["offloadKVCacheToGpu", "offload_kv_cache_to_gpu"],
  ["contextLength", "context_length"],
  ["promptTemplate", "prompt_template"],
  ["ropeFrequencyBase", "rope_frequency_base"],
  ["ropeFrequencyScale", "rope_frequency_scale"],
  ["evalBatchSize", "eval_batch_size"],
  ["physicalBatchSize", "physical_batch_size"],
  ["flashAttention", "flash_attention"],
  ["contextCheckpoints", "context_checkpoints"],
  ["reasoningBudgetMessage", "reasoning_budget_message"],
  ["speculativeDraftMtp", "speculative_draft_mtp"],
  ["speculativeDraftSimple", "speculative_draft_simple"],
  ["speculativeDraftModel", "speculative_draft_model"],
  ["speculativeDraftMaxTokens", "speculative_draft_max_tokens"],
  ["speculativeDraftMinTokens", "speculative_draft_min_tokens"],
  ["speculativeDraftMinContinueProbability", "speculative_draft_min_continue_probability"],
  ["keepModelInMemory", "keep_model_in_memory"],
  ["seed", "seed"],
  ["useFp16ForKVCache", "use_fp16_for_kv_cache"],
  ["tryMmap", "try_mmap"],
  ["tryDirectIO", "try_direct_io"],
  ["numExperts", "num_experts"],
  ["llamaKCacheQuantizationType", "llama_k_cache_quantization_type"],
  ["llamaVCacheQuantizationType", "llama_v_cache_quantization_type"],
  ["mlxDiskCache", "mlx_disk_cache"],
  ["mlxKvCacheQuantization", "mlx_kv_cache_quantization"],
]);

const BOOLEAN_FIELDS = new Set([
  "gpuStrictVramCap", "useUnifiedKvCache", "offloadKVCacheToGpu",
  "flashAttention", "speculativeDraftMtp", "speculativeDraftSimple",
  "keepModelInMemory", "useFp16ForKVCache", "tryMmap", "tryDirectIO",
  "mlxDiskCache",
]);
const INTEGER_FIELDS = new Set([
  "maxParallelPredictions", "contextLength", "evalBatchSize", "physicalBatchSize",
  "contextCheckpoints", "speculativeDraftMaxTokens", "speculativeDraftMinTokens",
  "numExperts",
]);
const CACHE_TYPES = new Set([
  "f32", "f16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1",
]);

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function canonicalSha256(value) {
  return sha256(JSON.stringify(sortValue(value)));
}

function compareText(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function hashRegularFile(file) {
  const descriptor = fs.openSync(file, "r");
  const digest = crypto.createHash("sha256");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  let before;
  let after;
  let bytes = 0;
  try {
    before = fs.fstatSync(descriptor, { bigint: true });
    if (!before.isFile()) throw new Error("attested source is not a regular file");
    while (true) {
      const count = fs.readSync(descriptor, buffer, 0, buffer.length, null);
      if (count === 0) break;
      digest.update(buffer.subarray(0, count));
      bytes += count;
    }
    after = fs.fstatSync(descriptor, { bigint: true });
  } finally {
    fs.closeSync(descriptor);
  }
  for (const field of ["dev", "ino", "size", "mtimeNs", "ctimeNs"]) {
    if (before[field] !== after[field]) {
      throw new Error("attested source changed during hashing");
    }
  }
  if (BigInt(bytes) !== before.size) {
    throw new Error("attested source size changed during hashing");
  }
  return { sha256: digest.digest("hex"), bytes, stat: before };
}

function hashedText(value, label) {
  if (typeof value !== "string") {
    throw new Error(`${label} must be a string`);
  }
  return {
    sha256: sha256(value),
    utf8_bytes: Buffer.byteLength(value, "utf8"),
  };
}

function requirePlainObject(value, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value;
}

function normalizeGpu(value) {
  const gpu = requirePlainObject(value, "gpu config");
  const allowed = new Set([
    "splitStrategy", "disabledGpus", "mainGpu", "ratio", "numCpuExpertLayersRatio",
  ]);
  for (const key of Object.keys(gpu)) {
    if (!allowed.has(key)) {
      throw new Error(`unsupported gpu config field: ${key}`);
    }
  }
  const result = {};
  if ("splitStrategy" in gpu) {
    if (!new Set(["evenly", "favorMainGpu"]).has(gpu.splitStrategy)) {
      throw new Error("gpu splitStrategy is invalid");
    }
    result.split_strategy = gpu.splitStrategy;
  }
  if ("disabledGpus" in gpu) {
    if (!Array.isArray(gpu.disabledGpus)
        || gpu.disabledGpus.some(value => !Number.isInteger(value) || value < 0)) {
      throw new Error("gpu disabledGpus must be an array of non-negative integers");
    }
    result.disabled_gpus = [...gpu.disabledGpus].sort((left, right) => left - right);
  }
  if (gpu.mainGpu !== undefined) {
    if (!Number.isInteger(gpu.mainGpu) || gpu.mainGpu < 0) {
      throw new Error("gpu mainGpu must be a non-negative integer");
    }
    result.main_gpu = gpu.mainGpu;
  }
  for (const [source, target] of [
    ["ratio", "ratio"], ["numCpuExpertLayersRatio", "num_cpu_expert_layers_ratio"],
  ]) {
    if (source in gpu) {
      const value = gpu[source];
      if (!(typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1)
          && value !== "max" && value !== "off") {
        throw new Error(`gpu ${source} is invalid`);
      }
      result[target] = value;
    }
  }
  return result;
}

function normalizePromptTemplate(value) {
  const prompt = requirePlainObject(value, "prompt template");
  if (Object.keys(prompt).some(key => !new Set(["type", "jinjaPromptTemplate"]).has(key))) {
    throw new Error("prompt template has unsupported fields");
  }
  if (prompt.type !== "jinja") {
    throw new Error("prompt template type must be jinja");
  }
  const jinja = requirePlainObject(prompt.jinjaPromptTemplate, "jinja prompt template");
  if (Object.keys(jinja).length !== 1 || typeof jinja.template !== "string") {
    throw new Error("jinja prompt template has unsupported fields");
  }
  return {
    type: "jinja",
    template_sha256: sha256(jinja.template),
    template_utf8_bytes: Buffer.byteLength(jinja.template, "utf8"),
  };
}

function normalizeMlxKvCache(value) {
  if (value === false) {
    return false;
  }
  const mlx = requirePlainObject(value, "MLX KV cache config");
  const allowed = new Set(["enabled", "bits", "groupSize", "quantizedStart"]);
  if (Object.keys(mlx).some(key => !allowed.has(key))) {
    throw new Error("MLX KV cache config has unsupported fields");
  }
  if (typeof mlx.enabled !== "boolean" || ![2, 3, 4, 6, 8].includes(mlx.bits)
      || ![32, 64, 128].includes(mlx.groupSize)
      || !Number.isInteger(mlx.quantizedStart) || mlx.quantizedStart < 0) {
    throw new Error("MLX KV cache config is invalid");
  }
  return {
    enabled: mlx.enabled, bits: mlx.bits, group_size: mlx.groupSize,
    quantized_start: mlx.quantizedStart,
  };
}

function normalizeCacheType(value, useFp16, label) {
  if (value !== false && !CACHE_TYPES.has(value)) {
    throw new Error(`${label} is invalid or unavailable`);
  }
  return value === false ? (useFp16 ? "f16" : "f32") : value;
}

function normalizeLoadConfig(value) {
  const config = requirePlainObject(value, "load config");
  for (const key of Object.keys(config)) {
    if (!LOAD_CONFIG_FIELDS.has(key)) {
      throw new Error(`unsupported load config field: ${key}`);
    }
  }
  const mlxBackend = "mlxDiskCache" in config || "mlxKvCacheQuantization" in config;
  const requiredFields = mlxBackend
    ? ["contextLength", "maxParallelPredictions", "mlxDiskCache", "mlxKvCacheQuantization"]
    : [
        "contextLength", "maxParallelPredictions", "flashAttention", "useFp16ForKVCache",
        "llamaKCacheQuantizationType", "llamaVCacheQuantizationType",
      ];
  for (const required of requiredFields) {
    if (!(required in config)) {
      throw new Error(`effective load config omitted required field: ${required}`);
    }
  }
  const result = { runtime_backend: mlxBackend ? "mlx" : "llama" };
  for (const [source, target] of LOAD_CONFIG_FIELDS) {
    if (!(source in config)) continue;
    const item = config[source];
    if (source === "gpu") {
      result[target] = normalizeGpu(item);
    } else if (source === "promptTemplate") {
      result[target] = normalizePromptTemplate(item);
    } else if (source === "reasoningBudgetMessage" || source === "speculativeDraftModel") {
      result[target] = hashedText(item, source);
    } else if (source === "mlxKvCacheQuantization") {
      result[target] = normalizeMlxKvCache(item);
    } else if (BOOLEAN_FIELDS.has(source)) {
      if (typeof item !== "boolean") throw new Error(`${source} must be boolean`);
      result[target] = item;
    } else if (INTEGER_FIELDS.has(source)) {
      if (!Number.isInteger(item) || item < 0) throw new Error(`${source} must be a non-negative integer`);
      result[target] = item;
    } else if (source === "ropeFrequencyBase" || source === "ropeFrequencyScale") {
      if (item !== false && !(typeof item === "number" && Number.isFinite(item))) {
        throw new Error(`${source} is invalid`);
      }
      result[target] = item;
    } else if (source === "speculativeDraftMinContinueProbability") {
      if (!(typeof item === "number" && Number.isFinite(item) && item >= 0 && item <= 1)) {
        throw new Error(`${source} is invalid`);
      }
      result[target] = item;
    } else if (source === "seed") {
      if (item !== false && !Number.isInteger(item)) throw new Error("seed is invalid");
      result[target] = item;
    } else if (source === "llamaKCacheQuantizationType" || source === "llamaVCacheQuantizationType") {
      if (item !== false && !CACHE_TYPES.has(item)) throw new Error(`${source} is invalid`);
      result[target] = item;
    } else {
      throw new Error(`load config field lacks a normalizer: ${source}`);
    }
  }
  if (!mlxBackend) {
    result.effective_llama_k_cache_type = normalizeCacheType(
      config.llamaKCacheQuantizationType, config.useFp16ForKVCache,
      "llama K cache quantization type",
    );
    result.effective_llama_v_cache_type = normalizeCacheType(
      config.llamaVCacheQuantizationType, config.useFp16ForKVCache,
      "llama V cache quantization type",
    );
  }
  return result;
}

function normalizeProcessingState(value) {
  const state = requirePlainObject(value, "model processing state");
  if (Object.keys(state).some(key => !new Set(["status", "queued"]).has(key))
      || !new Set(["idle", "processingPrompt", "generating", "computingEmbedding"]).has(state.status)
      || !Number.isInteger(state.queued) || state.queued < 0) {
    throw new Error("model processing state is invalid");
  }
  return { status: state.status, queued: state.queued };
}

function normalizeModelState(info, processingState) {
  requirePlainObject(info, "model info");
  for (const field of [
    "modelKey", "identifier", "indexedModelIdentifier", "selectedVariant",
    "instanceReference",
  ]) {
    if (typeof info[field] !== "string" || !info[field]) {
      throw new Error(`model info omitted ${field}`);
    }
  }
  if (!Number.isInteger(info.contextLength) || info.contextLength <= 0) {
    throw new Error("model info contextLength is invalid");
  }
  if (info.deviceIdentifier !== null && typeof info.deviceIdentifier !== "string") {
    throw new Error("model info deviceIdentifier is invalid or unavailable");
  }
  return {
    model_key: info.modelKey,
    identifier: info.identifier,
    indexed_model_identifier: info.indexedModelIdentifier,
    selected_variant: info.selectedVariant,
    instance_reference_sha256: sha256(info.instanceReference),
    device_identifier: info.deviceIdentifier === null
      ? null : hashedText(info.deviceIdentifier, "device identifier"),
    context_length: info.contextLength,
    processing_state: normalizeProcessingState(processingState),
  };
}

function normalizeModel(info, loadConfig, processingState) {
  const state = normalizeModelState(info, processingState);
  const normalizedConfig = normalizeLoadConfig(loadConfig);
  return {
    ...state,
    load_config: normalizedConfig,
    load_config_sha256: sha256(JSON.stringify(sortValue(normalizedConfig))),
  };
}

function sortValue(value) {
  if (Array.isArray(value)) return value.map(sortValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, sortValue(value[key])]));
  }
  return value;
}

function validateWsEndpoint(value) {
  const url = new URL(value);
  const loopback = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);
  if (!new Set(["ws:", "wss:"]).has(url.protocol) || !loopback.has(url.hostname)
      || url.username || url.password || url.search || url.hash
      || (url.pathname !== "/" && url.pathname !== "")) {
    throw new Error("SDK endpoint must be a bare loopback WebSocket URL");
  }
  return url.toString().replace(/\/$/, "");
}

function createClient(sdkEntry, endpoint) {
  const sdk = require(sdkEntry);
  if (!sdk || typeof sdk.LMStudioClient !== "function") {
    throw new Error("official SDK entry does not export LMStudioClient");
  }
  return new sdk.LMStudioClient({
    baseUrl: validateWsEndpoint(endpoint),
    verboseErrorMessages: false,
    logger: { debug() {}, info() {}, warn() {}, error() {} },
  });
}

function normalizeAppIdentity(value) {
  if (!value || typeof value.version !== "string" || !value.version
      || !Number.isInteger(value.build) || value.build < 0) {
    throw new Error("LM Studio app identity is invalid");
  }
  return { version: value.version, build: value.build };
}

function nodeRuntimeIdentity() {
  if (cachedNodeRuntimeIdentity !== undefined) {
    return JSON.parse(JSON.stringify(cachedNodeRuntimeIdentity));
  }
  const executableRealpath = fs.realpathSync(process.execPath);
  const executable = hashRegularFile(executableRealpath);
  cachedNodeRuntimeIdentity = {
    version: process.version,
    executable_realpath: executableRealpath,
    executable_sha256: executable.sha256,
    executable_bytes: executable.bytes,
    executable_stat: {
      device: executable.stat.dev.toString(),
      inode: executable.stat.ino.toString(),
      bytes: executable.stat.size.toString(),
      modified_nanoseconds: executable.stat.mtimeNs.toString(),
      changed_nanoseconds: executable.stat.ctimeNs.toString(),
    },
  };
  return JSON.parse(JSON.stringify(cachedNodeRuntimeIdentity));
}

async function disposeClient(client) {
  if (typeof client[Symbol.asyncDispose] === "function") {
    await client[Symbol.asyncDispose]();
  }
}

function modelInfoMatchesTarget(info, targetModel) {
  return [info.modelKey, info.identifier, info.indexedModelIdentifier]
    .some(value => value === targetModel);
}

async function findTargetModel(client, targetModel) {
  const loaded = await client.llm.listLoaded();
  if (!Array.isArray(loaded)) throw new Error("loaded model list is invalid");
  const matches = [];
  for (const model of loaded) {
    const info = await model.getModelInfo();
    if (modelInfoMatchesTarget(info, targetModel)) {
      matches.push({ model, info });
    }
  }
  if (matches.length !== 1) {
    throw new Error("target model is missing or ambiguous");
  }
  return matches[0];
}

async function sampleBoundTargetModel(model, initialInfo) {
  const info = initialInfo === undefined ? await model.getModelInfo() : initialInfo;
  const loadConfig = await model.getLoadConfig();
  const processingState = await model.getInstanceProcessingState();
  return normalizeModel(info, loadConfig, processingState);
}

async function sampleBoundTargetModelState(model) {
  const info = await model.getModelInfo();
  const processingState = await model.getInstanceProcessingState();
  return normalizeModelState(info, processingState);
}

function createLineWriter(stream) {
  let streamError = null;
  const pending = new Set();
  const onError = error => {
    streamError = error || new Error("output stream failed");
    for (const reject of pending) reject(streamError);
    pending.clear();
  };
  stream.on("error", onError);

  return {
    write(value) {
      if (streamError) return Promise.reject(streamError);
      let serialized;
      try {
        serialized = `${JSON.stringify(value)}\n`;
      } catch (error) {
        return Promise.reject(error);
      }
      if (Buffer.byteLength(serialized, "utf8") > MAX_WATCHER_LINE_BYTES) {
        return Promise.reject(new Error("watcher output line is too large"));
      }
      return new Promise((resolve, reject) => {
        let settled = false;
        const fail = error => {
          if (settled) return;
          settled = true;
          pending.delete(fail);
          reject(error);
        };
        pending.add(fail);
        try {
          stream.write(serialized, error => {
            if (settled) return;
            settled = true;
            pending.delete(fail);
            if (error || streamError) reject(error || streamError);
            else resolve();
          });
        } catch (error) {
          fail(error);
        }
      });
    },
    close() {
      stream.removeListener("error", onError);
    },
  };
}

function createStopController(stream) {
  const expected = Buffer.from("stop\n", "utf8");
  let received = Buffer.alloc(0);
  let active = true;
  let resolveRequest;
  const promise = new Promise(resolve => { resolveRequest = resolve; });

  const cleanup = () => {
    stream.removeListener("data", onData);
    stream.removeListener("end", onEnd);
    stream.removeListener("error", onError);
    stream.pause();
  };
  const finish = result => {
    if (!active) return;
    active = false;
    cleanup();
    resolveRequest(result);
  };
  const onData = chunk => {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    received = Buffer.concat([received, bytes]);
    if (received.length > expected.length
        || !expected.subarray(0, received.length).equals(received)) {
      finish({ kind: "error", error: new Error("invalid watcher stop command") });
    } else if (received.length === expected.length) {
      finish({ kind: "stop" });
    }
  };
  const onEnd = () => finish({
    kind: "error", error: new Error("watcher stdin ended before stop command"),
  });
  const onError = error => finish({ kind: "error", error });

  stream.on("data", onData);
  stream.once("end", onEnd);
  stream.once("error", onError);
  stream.resume();
  return {
    promise,
    cancel() {
      finish({ kind: "cancelled" });
    },
  };
}

async function waitForIntervalOrStop(intervalMilliseconds, stopPromise) {
  let timer;
  try {
    return await Promise.race([
      new Promise(resolve => {
        timer = setTimeout(() => resolve({ kind: "interval" }), intervalMilliseconds);
      }),
      stopPromise,
    ]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

async function runProbe(sdkEntry, endpoint) {
  const executionIdentity = captureRuntimeExecutionIdentity(sdkEntry);
  const client = createClient(sdkEntry, endpoint);
  try {
    const app = normalizeAppIdentity(await client.system.getLMStudioVersion());
    const loaded = await client.llm.listLoaded();
    if (!Array.isArray(loaded)) throw new Error("loaded model list is invalid");
    const models = [];
    for (const model of loaded) {
      const info = await model.getModelInfo();
      const loadConfig = await model.getLoadConfig();
      const processingState = await model.getInstanceProcessingState();
      models.push(normalizeModel(info, loadConfig, processingState));
    }
    models.sort((left, right) => left.identifier.localeCompare(right.identifier));
    return {
      schema_version: 5,
      node_runtime: nodeRuntimeIdentity(),
      execution_identity: executionIdentity,
      app,
      models,
    };
  } finally {
    await disposeClient(client);
  }
}

async function runWatch(sdkEntry, endpoint, targetModel, intervalMilliseconds) {
  if (typeof targetModel !== "string" || !targetModel
      || Buffer.byteLength(targetModel, "utf8") > 1024
      || /[\u0000-\u001f\u007f]/u.test(targetModel)
      || !Number.isSafeInteger(intervalMilliseconds) || intervalMilliseconds <= 0
      || intervalMilliseconds > MAX_WATCHER_INTERVAL_MILLISECONDS) {
    throw new Error("watcher arguments are invalid");
  }
  const executionIdentity = captureRuntimeExecutionIdentity(sdkEntry);
  const client = createClient(sdkEntry, endpoint);
  const writer = createLineWriter(process.stdout);
  const stop = createStopController(process.stdin);
  let samples = 0;
  try {
    const app = normalizeAppIdentity(await client.system.getLMStudioVersion());
    const boundTarget = await findTargetModel(client, targetModel);
    const model = await sampleBoundTargetModel(boundTarget.model, boundTarget.info);
    await writer.write({
      schema_version: WATCHER_SCHEMA_VERSION,
      kind: "ready",
      watcher_version: WATCHER_VERSION,
      interval_milliseconds: intervalMilliseconds,
      target_model: targetModel,
      node_runtime: nodeRuntimeIdentity(),
      execution_identity: executionIdentity,
      app,
      model,
    });
    while (true) {
      const event = await waitForIntervalOrStop(intervalMilliseconds, stop.promise);
      if (event.kind === "stop") break;
      if (event.kind === "error") throw event.error;
      if (event.kind !== "interval") throw new Error("watcher stopped unexpectedly");
      const sampledModel = await sampleBoundTargetModelState(boundTarget.model);
      samples += 1;
      await writer.write({
        schema_version: WATCHER_SCHEMA_VERSION,
        kind: "sample",
        watcher_version: WATCHER_VERSION,
        sequence: samples,
        model: sampledModel,
      });
    }
    await writer.write({
      schema_version: WATCHER_SCHEMA_VERSION,
      kind: "stopped",
      watcher_version: WATCHER_VERSION,
      samples,
    });
  } finally {
    stop.cancel();
    writer.close();
    await disposeClient(client);
  }
}

function findResolvedPackageRoot(resolvedEntry, packageName) {
  let cursor = path.dirname(fs.realpathSync(resolvedEntry));
  while (true) {
    const metadataPath = path.join(cursor, "package.json");
    if (fs.existsSync(metadataPath)) {
      const metadata = JSON.parse(fs.readFileSync(metadataPath, "utf8"));
      if (metadata && metadata.name === packageName) return fs.realpathSync(cursor);
    }
    const parent = path.dirname(cursor);
    if (parent === cursor) throw new Error("resolved dependency package root is missing");
    cursor = parent;
  }
}

function resolveRuntimeDependencies(sdkEntry) {
  const absoluteEntry = fs.realpathSync(sdkEntry);
  const sdkRoot = findResolvedPackageRoot(absoluteEntry, "@lmstudio/sdk");
  const packages = new Map();
  const edges = [];
  const missingEdges = [];

  const resolveEdge = (parentRoot, parentEntry, name, relationship, required) => {
    const requireFromParent = createRequire(parentEntry);
    let entry;
    try {
      entry = fs.realpathSync(requireFromParent.resolve(name));
    } catch (error) {
      if (!required) {
        missingEdges.push({
          parent_package_root: parentRoot,
          dependency_name: name,
          relationship,
        });
        return;
      }
      throw error;
    }
    const packageRoot = findResolvedPackageRoot(entry, name);
    edges.push({
      parent_package_root: parentRoot,
      dependency_name: name,
      child_package_root: packageRoot,
      relationship,
    });
    if (!packages.has(packageRoot)) {
      packages.set(packageRoot, { name, entry, package_root: packageRoot, expanded: false });
    }
  };

  const declaredRuntimeEdges = metadata => {
    const map = (value, label) => {
      if (value === undefined) return {};
      if (value === null || typeof value !== "object" || Array.isArray(value)) {
        throw new Error(`${label} must be an object`);
      }
      return value;
    };
    const dependencies = map(metadata.dependencies, "dependencies");
    const optionalDependencies = map(
      metadata.optionalDependencies, "optionalDependencies",
    );
    const peerDependencies = map(metadata.peerDependencies, "peerDependencies");
    const peerDependenciesMeta = map(
      metadata.peerDependenciesMeta, "peerDependenciesMeta",
    );
    const declarations = new Map();
    for (const name of Object.keys(dependencies)) {
      declarations.set(name, {
        name, relationship: "dependency", required: true,
      });
    }
    // npm treats optionalDependencies as overriding dependencies with the same
    // name, so preserve that precedence in the attested graph.
    for (const name of Object.keys(optionalDependencies)) {
      declarations.set(name, {
        name, relationship: "optional_dependency", required: false,
      });
    }
    for (const name of Object.keys(peerDependencies)) {
      if (declarations.has(name)) continue;
      const peerMeta = peerDependenciesMeta[name];
      if (peerMeta !== undefined && (
        peerMeta === null || typeof peerMeta !== "object" || Array.isArray(peerMeta)
        || Object.keys(peerMeta).some(key => key !== "optional")
        || (peerMeta.optional !== undefined && typeof peerMeta.optional !== "boolean")
      )) {
        throw new Error("peerDependenciesMeta entry is invalid");
      }
      declarations.set(name, {
        name,
        relationship: peerMeta && peerMeta.optional === true
          ? "optional_peer_dependency" : "peer_dependency",
        // A host may legitimately omit peers. Their declared absence is still
        // bound below instead of silently disappearing from the graph.
        required: false,
      });
    }
    return [...declarations.values()].sort((left, right) =>
      left.name.localeCompare(right.name)
      || left.relationship.localeCompare(right.relationship));
  };

  const sdkMetadata = JSON.parse(
    fs.readFileSync(path.join(sdkRoot, "package.json"), "utf8"),
  );
  const sdkDependencies = sdkMetadata.dependencies || {};
  if (!RUNTIME_DEPENDENCIES.every(name => name in sdkDependencies)) {
    throw new Error("known SDK runtime dependencies are missing from metadata");
  }
  for (const declaration of declaredRuntimeEdges(sdkMetadata)) {
    resolveEdge(
      sdkRoot, absoluteEntry, declaration.name,
      declaration.relationship, declaration.required,
    );
  }

  while ([...packages.values()].some(value => !value.expanded)) {
    const item = [...packages.values()].find(value => !value.expanded);
    item.expanded = true;
    const metadata = JSON.parse(
      fs.readFileSync(path.join(item.package_root, "package.json"), "utf8"),
    );
    if (!metadata || metadata.name !== item.name) {
      throw new Error("resolved dependency metadata is invalid");
    }
    for (const declaration of declaredRuntimeEdges(metadata)) {
      resolveEdge(
        item.package_root, item.entry, declaration.name,
        declaration.relationship, declaration.required,
      );
    }
  }

  const dependencies = [...packages.values()]
    .map(({ name, entry, package_root: packageRoot }) => ({
      name, entry, package_root: packageRoot,
    }))
    .sort((left, right) => left.name.localeCompare(right.name)
      || left.package_root.localeCompare(right.package_root));
  edges.sort((left, right) => left.parent_package_root.localeCompare(right.parent_package_root)
    || left.dependency_name.localeCompare(right.dependency_name)
    || left.child_package_root.localeCompare(right.child_package_root)
    || left.relationship.localeCompare(right.relationship));
  missingEdges.sort((left, right) =>
    left.parent_package_root.localeCompare(right.parent_package_root)
    || left.dependency_name.localeCompare(right.dependency_name)
    || left.relationship.localeCompare(right.relationship));
  return {
    schema_version: 5, node_runtime: nodeRuntimeIdentity(),
    sdk_package_root: sdkRoot, dependencies, edges,
    missing_edges: missingEdges,
  };
}

function packageContentSha256(packageRoot) {
  const entries = [];
  const visit = (directory, relativeDirectory) => {
    for (const name of fs.readdirSync(directory).sort()) {
      const relative = relativeDirectory ? `${relativeDirectory}/${name}` : name;
      if (relative.split("/").includes("node_modules")) continue;
      const child = path.join(directory, name);
      const itemStat = fs.lstatSync(child, { bigint: true });
      if (itemStat.isSymbolicLink()) {
        throw new Error("SDK package contains a symlink");
      }
      if (itemStat.isDirectory()) {
        visit(child, relative);
      } else if (itemStat.isFile()) {
        const identity = hashRegularFile(child);
        entries.push({
          path: relative, bytes: identity.bytes, sha256: identity.sha256,
        });
      } else {
        throw new Error("SDK package contains a non-regular entry");
      }
    }
  };
  visit(packageRoot, "");
  if (entries.length === 0) throw new Error("SDK package contains no files");
  entries.sort((left, right) => compareText(left.path, right.path));
  return canonicalSha256(entries);
}

function runtimeExecutionIdentity(sdkEntry, resolvedGraph) {
  const graph = resolvedGraph || resolveRuntimeDependencies(sdkEntry);
  const sdkRoot = graph.sdk_package_root;
  const sdkMetadata = JSON.parse(
    fs.readFileSync(path.join(sdkRoot, "package.json"), "utf8"),
  );
  if (!sdkMetadata || sdkMetadata.name !== "@lmstudio/sdk"
      || typeof sdkMetadata.version !== "string" || !sdkMetadata.version) {
    throw new Error("SDK execution metadata is invalid");
  }
  const sdkPackage = {
    name: "@lmstudio/sdk",
    version: sdkMetadata.version,
    content_sha256: packageContentSha256(sdkRoot),
  };
  const sdkIdentitySha256 = canonicalSha256(sdkPackage);
  const packagesByRoot = new Map();
  const packages = graph.dependencies.map(dependency => {
    const metadata = JSON.parse(
      fs.readFileSync(path.join(dependency.package_root, "package.json"), "utf8"),
    );
    if (!metadata || metadata.name !== dependency.name
        || typeof metadata.version !== "string" || !metadata.version) {
      throw new Error("runtime dependency execution metadata is invalid");
    }
    const entry = hashRegularFile(dependency.entry);
    const relativeEntry = path.relative(
      dependency.package_root, dependency.entry,
    ).split(path.sep).join("/");
    if (!relativeEntry || relativeEntry.startsWith("../")) {
      throw new Error("runtime dependency execution entry escaped package");
    }
    const row = {
      name: dependency.name,
      version: metadata.version,
      content_sha256: packageContentSha256(dependency.package_root),
      entry_relative_path: relativeEntry,
      entry_sha256: entry.sha256,
    };
    row.identity_sha256 = canonicalSha256(row);
    packagesByRoot.set(dependency.package_root, row);
    return row;
  }).sort((left, right) => compareText(left.name, right.name)
    || compareText(left.version, right.version)
    || compareText(left.identity_sha256, right.identity_sha256));
  const edgesByCanonical = new Map();
  for (const edge of graph.edges) {
    const child = packagesByRoot.get(edge.child_package_root);
    const parentIdentity = edge.parent_package_root === sdkRoot
      ? sdkIdentitySha256
      : packagesByRoot.get(edge.parent_package_root)?.identity_sha256;
    if (!child || !parentIdentity || edge.dependency_name !== child.name) {
      throw new Error("runtime dependency execution edge is invalid");
    }
    const row = {
      parent_identity_sha256: parentIdentity,
      dependency_name: edge.dependency_name,
      child_identity_sha256: child.identity_sha256,
      relationship: edge.relationship,
    };
    edgesByCanonical.set(JSON.stringify(sortValue(row)), row);
  }
  const edges = [...edgesByCanonical.values()].sort((left, right) =>
    compareText(left.parent_identity_sha256, right.parent_identity_sha256)
    || compareText(left.dependency_name, right.dependency_name)
    || compareText(left.child_identity_sha256, right.child_identity_sha256)
    || compareText(left.relationship, right.relationship));
  const missingDependencies = graph.missing_edges.map(missing => {
    const parentIdentity = missing.parent_package_root === sdkRoot
      ? sdkIdentitySha256
      : packagesByRoot.get(missing.parent_package_root)?.identity_sha256;
    if (!parentIdentity) {
      throw new Error("missing runtime dependency execution edge is invalid");
    }
    return {
      parent_identity_sha256: parentIdentity,
      dependency_name: missing.dependency_name,
      relationship: missing.relationship,
    };
  }).sort((left, right) =>
    compareText(left.parent_identity_sha256, right.parent_identity_sha256)
    || compareText(left.dependency_name, right.dependency_name)
    || compareText(left.relationship, right.relationship));
  const closure = {
    sdk: { ...sdkPackage, identity_sha256: sdkIdentitySha256 },
    packages,
    edges,
    missing_dependencies: missingDependencies,
  };
  return {
    schema_version: 1,
    probe_helper_sha256: hashRegularFile(__filename).sha256,
    sdk_package: sdkPackage,
    runtime_dependency_closure_sha256: canonicalSha256(closure),
  };
}

function captureRuntimeExecutionIdentity(sdkEntry, resolvedGraph) {
  try {
    return runtimeExecutionIdentity(sdkEntry, resolvedGraph);
  } catch (_error) {
    // Standalone helper consumers can inspect this explicit unavailable value;
    // the Python production boundary rejects it rather than trusting a partial
    // identity. This keeps normalization-only fixture use independent of npm.
    return {
      schema_version: 1,
      probe_helper_sha256: hashRegularFile(__filename).sha256,
      sdk_package: null,
      runtime_dependency_closure_sha256: null,
    };
  }
}

module.exports = {
  normalizeLoadConfig, resolveRuntimeDependencies, runProbe, runWatch,
};

function failProbe() {
  process.stderr.write("runtime probe failed\n");
  process.exitCode = 2;
}

if (require.main === module) {
  if (process.argv[2] === "--resolve-runtime-dependencies") {
    if (process.argv.length !== 4) {
      failProbe();
    } else {
      try {
        const resolved = resolveRuntimeDependencies(process.argv[3]);
        resolved.execution_identity = captureRuntimeExecutionIdentity(
          process.argv[3], resolved,
        );
        process.stdout.write(`${JSON.stringify(resolved)}\n`);
      } catch (_error) {
        failProbe();
      }
    }
  } else if (process.argv[2] === "--watch") {
    const interval = process.argv.length === 7 && /^[1-9][0-9]*$/u.test(process.argv[6])
      ? Number(process.argv[6]) : NaN;
    if (process.argv.length !== 7 || !Number.isSafeInteger(interval)) {
      failProbe();
    } else {
      runWatch(process.argv[3], process.argv[4], process.argv[5], interval)
        .catch(failProbe);
    }
  } else if (process.argv.length !== 4) {
    failProbe();
  } else {
    runProbe(process.argv[2], process.argv[3]).then(value => {
      process.stdout.write(`${JSON.stringify(value)}\n`);
    }).catch(failProbe);
  }
}
