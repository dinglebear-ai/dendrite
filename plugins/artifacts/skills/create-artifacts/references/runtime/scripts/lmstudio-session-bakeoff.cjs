#!/usr/bin/env node
// Runs one bounded, structured three-repeat bake-off transaction against the
// sole model already loaded and identity-bound by lmstudio-model-lifecycle.cjs.
// It never mutates model lifecycle state and never persists prompts, reasoning,
// image bytes, or server-side file handles.
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const zlib = require("node:zlib");
const {createRequire} = require("node:module");
const {spawnSync} = require("node:child_process");

const TOOL_VERSION = "lmstudio-session-bakeoff-callback-v2";
const CORPUS_EXPECTED_SHA256 = "8e5c2f9bfbf1fea16f45dc935102e9c9bd6867e9ce53561b2d4602335a8cd017";
const EXPECTED_SOURCE_SHA256 = "9755104caa34833d76c509846821e0f0bdb06e9cb5ae53b7b4f4c92ec5305a90";
const EXPECTED_SOURCE_BYTES = 157_155_006;
const EXPECTED_LOG_SHA256 = "28887f13dd8cd52f9a118561975e6c2d8ea9b83f5b29c55ff96c006c80461e9b";
const EXPECTED_LOG_BYTES = 13_610;
const PYTHON_PREFLIGHT_SHA256 = "345887a6e623303b53ac958334118d156ddefb067625f9fd5cafb13b927c0585";
const PYTHON_PREFLIGHT_PATH = path.resolve(__dirname, "lmstudio-session-bakeoff.py");
const FIXED_CORPUS_PATH = path.resolve(__dirname, "..", "research", "session-bakeoff-corpus-v1.json");
const REVIEWED_SDK = Object.freeze({
  name: "@lmstudio/sdk",
  version: "1.5.0",
  entrySha256: "f657b4df6408212756deb8001bb66540c1072818879dc298740f9e05de237ef3",
  closureSha256: "a5ca5d8499398a31eee23963b77c320594092698222fd6010ae5a56b5b925dcc",
  dependencyClosureSha256: "8eb5d5bafa79d0f7ba2f341615b3faeb07fd4919116bd63aab8fd09503fdbe20",
});
const MAX_INPUT_BYTES = 16 * 1024 * 1024;
const MAX_PROMPT_BYTES = 64 * 1024;
const MAX_RESULT_BYTES = 2 * 1024 * 1024;
const MAX_CLAIMS = 128;
const MAX_CITATIONS = 32;
const MAX_PACKET_CANONICAL_BYTES = 16_384;
const MAX_CONSERVATIVE_INPUT_TOKENS = 20_480;
const MAX_OUTPUT_TOKENS = 8_192;
const MAX_REASONING_TOKENS = 4_096;
const RESERVED_CONTEXT_TOKENS = 4_096;
const TARGET_CONTEXT_TOKENS = 32_768;
const COMPLETE_STOP_REASON = "eosFound";
const REQUIRED_REPEATS = 3;
const PACKET_ROTATION_OFFSETS = [0, 3, 6];
const MAX_CALLBACK_DEADLINE_MS = 7_200_000;
const VISION_OUTPUT_TOKENS = 64;
const SYNTHETIC_VISION_SHA256 = "32d8d17e13795dd62f3e8a39d033ccecd74ab4a707b77515f7c8dd0ba6cb25d3";
const SYNTHETIC_VISION_GOLD = Object.freeze({
  top_bar_present: true,
  left_sidebar_present: true,
  main_panel_present: true,
  status_text: "ERR",
  status_state: "error",
  anomaly_color: "rose",
  anomaly_position: "upper_right",
  anomaly_shape: "square",
});
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const TOKEN_PATTERN = /^[0-9a-f]{64}$/;
const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const STATES = new Set([
  "requested", "diagnosed", "implemented", "test_passed", "built", "installed",
  "live_verified", "observed", "unresolved", "failed_attempt", "not_done", "partial",
]);
const POLARITIES = new Set(["affirmed", "negated", "uncertain"]);
const DISPOSITIONS = new Set([
  "used", "duplicate", "administrative", "non_substantive", "superseded",
  "no_additional_value",
]);

class CallbackError extends Error {}

function fail(message) {
  throw new CallbackError(message);
}

function sortValue(value) {
  if (Array.isArray(value)) return value.map(sortValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, sortValue(value[key])]));
  }
  return value;
}

function canonicalBytes(value) {
  assertFinite(value, "canonical value");
  return Buffer.from(JSON.stringify(sortValue(value)), "utf8");
}

function sha256Bytes(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function sha256Value(value) {
  return sha256Bytes(canonicalBytes(value));
}

function assertFinite(value, label) {
  if (typeof value === "number" && !Number.isFinite(value)) fail(`${label} contains a non-finite number`);
  if (Array.isArray(value)) value.forEach(item => assertFinite(item, label));
  else if (value && typeof value === "object") Object.values(value).forEach(item => assertFinite(item, label));
}

function requireObject(value, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail(`${label} must be an object`);
  return value;
}

function requireArray(value, label) {
  if (!Array.isArray(value)) fail(`${label} must be an array`);
  return value;
}

function exactKeys(value, keys, label) {
  const expected = new Set(keys);
  const unsupported = Object.keys(value).filter(key => !expected.has(key));
  const missing = keys.filter(key => !(key in value));
  if (unsupported.length) fail(`${label} has unsupported fields: ${unsupported.sort().join(", ")}`);
  if (missing.length) fail(`${label} omitted required fields: ${missing.sort().join(", ")}`);
}

function optionalKeys(value, required, optional, label) {
  const allowed = new Set([...required, ...optional]);
  const unsupported = Object.keys(value).filter(key => !allowed.has(key));
  const missing = required.filter(key => !(key in value));
  if (unsupported.length) fail(`${label} has unsupported fields: ${unsupported.sort().join(", ")}`);
  if (missing.length) fail(`${label} omitted required fields: ${missing.sort().join(", ")}`);
}

function requireString(value, label, maximum = 4096) {
  if (typeof value !== "string" || !value || Buffer.byteLength(value, "utf8") > maximum) {
    fail(`${label} must be a non-empty bounded string`);
  }
  return value;
}

function requireId(value, label) {
  const text = requireString(value, label, 128);
  if (!ID_PATTERN.test(text)) fail(`${label} is not a valid identifier`);
  return text;
}

function requireSha(value, label) {
  const text = requireString(value, label, 64);
  if (!SHA256_PATTERN.test(text)) fail(`${label} must be a lowercase SHA-256 digest`);
  return text;
}

function requireInteger(value, label, minimum, maximum) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    fail(`${label} must be an integer between ${minimum} and ${maximum}`);
  }
  return value;
}

function parseStrictJson(text, label) {
  let index = 0;
  const length = text.length;
  const whitespace = () => {
    while (index < length && /[\x20\x09\x0a\x0d]/.test(text[index])) index += 1;
  };
  const parseString = () => {
    if (text[index] !== '"') fail(`${label} contains invalid JSON string syntax`);
    const start = index++;
    let escaped = false;
    while (index < length) {
      const character = text[index++];
      if (escaped) {
        escaped = false;
      } else if (character === "\\") {
        escaped = true;
      } else if (character === '"') {
        const raw = text.slice(start, index);
        try {
          return JSON.parse(raw);
        } catch {
          fail(`${label} contains an invalid JSON string`);
        }
      } else if (character.charCodeAt(0) < 0x20) {
        fail(`${label} contains a control character in a string`);
      }
    }
    fail(`${label} contains an unterminated JSON string`);
  };
  const parseValue = () => {
    whitespace();
    if (index >= length) fail(`${label} ended before a JSON value`);
    if (text[index] === '"') return parseString();
    if (text[index] === "{") {
      index += 1;
      whitespace();
      const result = {};
      const seen = new Set();
      if (text[index] === "}") {
        index += 1;
        return result;
      }
      while (true) {
        whitespace();
        const key = parseString();
        if (seen.has(key)) fail(`${label} contains duplicate key ${key}`);
        seen.add(key);
        whitespace();
        if (text[index++] !== ":") fail(`${label} omitted an object colon`);
        result[key] = parseValue();
        whitespace();
        const delimiter = text[index++];
        if (delimiter === "}") return result;
        if (delimiter !== ",") fail(`${label} has an invalid object delimiter`);
      }
    }
    if (text[index] === "[") {
      index += 1;
      whitespace();
      const result = [];
      if (text[index] === "]") {
        index += 1;
        return result;
      }
      while (true) {
        result.push(parseValue());
        whitespace();
        const delimiter = text[index++];
        if (delimiter === "]") return result;
        if (delimiter !== ",") fail(`${label} has an invalid array delimiter`);
      }
    }
    for (const [literal, value] of [["true", true], ["false", false], ["null", null]]) {
      if (text.startsWith(literal, index)) {
        index += literal.length;
        return value;
      }
    }
    const match = text.slice(index).match(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/);
    if (!match) fail(`${label} contains an invalid JSON token`);
    index += match[0].length;
    const value = Number(match[0]);
    if (!Number.isFinite(value)) fail(`${label} contains a non-finite number`);
    return value;
  };
  const value = parseValue();
  whitespace();
  if (index !== length) fail(`${label} has trailing JSON content`);
  assertFinite(value, label);
  return value;
}

function readRegularBytes(file, label, maximum = MAX_INPUT_BYTES) {
  let before;
  try {
    before = fs.lstatSync(file, { bigint: true });
  } catch (error) {
    fail(`${label} cannot be read: ${error.message}`);
  }
  if (!before.isFile() || before.isSymbolicLink() || before.size > BigInt(maximum)) {
    fail(`${label} must be a bounded regular non-symlink file`);
  }
  const raw = fs.readFileSync(file);
  const after = fs.lstatSync(file, { bigint: true });
  for (const field of ["dev", "ino", "size", "mtimeNs", "ctimeNs"]) {
    if (before[field] !== after[field]) fail(`${label} changed while being read`);
  }
  return raw;
}

function readRegularJson(file, label, maximum = MAX_INPUT_BYTES) {
  const raw = readRegularBytes(file, label, maximum);
  return { value: parseStrictJson(raw.toString("utf8"), label), raw };
}

function writeBoundedJson(file, value) {
  const parent = path.dirname(file);
  const parentStat = fs.lstatSync(parent);
  if (!parentStat.isDirectory() || parentStat.isSymbolicLink()) fail("output parent must be a non-symlink directory");
  if (fs.existsSync(file)) {
    const outputStat = fs.lstatSync(file);
    if (!outputStat.isFile() || outputStat.isSymbolicLink()) fail("output must be a regular non-symlink file");
  }
  const data = Buffer.concat([canonicalBytes(value), Buffer.from("\n")]);
  if (data.length > MAX_RESULT_BYTES) fail("callback output exceeds the byte limit");
  const temporary = path.join(parent, `.${path.basename(file)}.${process.pid}.${crypto.randomBytes(8).toString("hex")}`);
  let descriptor;
  try {
    descriptor = fs.openSync(temporary, "wx", 0o600);
    fs.writeFileSync(descriptor, data);
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    fs.renameSync(temporary, file);
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
}

function validateLoopbackEndpoint(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    fail("endpoint must be a valid WebSocket URL");
  }
  if (!new Set(["ws:", "wss:"]).has(parsed.protocol)
      || !new Set(["127.0.0.1", "localhost", "[::1]"]).has(parsed.hostname)
      || parsed.username || parsed.password || parsed.search || parsed.hash
      || (parsed.pathname !== "/" && parsed.pathname !== "")) {
    fail("endpoint must be a bare loopback WebSocket URL");
  }
  return parsed.toString().replace(/\/$/, "");
}

function requireEnvironment(name, maximum = 4096) {
  return requireString(process.env[name], `environment ${name}`, maximum);
}

function validateBundle(value) {
  const bundle = requireObject(value, "bundle");
  exactKeys(bundle, [
    "schema_version", "kind", "tool_version", "corpus_sha256", "corpus_manifest",
    "prepared_binding", "execution_contract", "evaluation_limitations", "packets", "bundle_sha256",
  ], "bundle");
  if (bundle.schema_version !== 2 || bundle.kind !== "session_bakeoff_bundle"
      || bundle.tool_version !== "lmstudio-session-bakeoff-v2") fail("unsupported bundle contract");
  if (bundle.corpus_sha256 !== CORPUS_EXPECTED_SHA256) fail("bundle corpus differs from the compiled corpus");
  const corpus = requireObject(bundle.corpus_manifest, "bundle corpus manifest");
  if (corpus.manifest_sha256 !== CORPUS_EXPECTED_SHA256) fail("bundle corpus manifest seal changed");
  const unsignedCorpus = {...corpus};
  delete unsignedCorpus.manifest_sha256;
  if (sha256Value(unsignedCorpus) !== CORPUS_EXPECTED_SHA256) {
    fail("bundle corpus differs from the compiled corpus; resealing is forbidden");
  }
  const contracts = requireObject(corpus.source_contracts, "bundle source contracts");
  if (contracts.expected_source_sha256 !== EXPECTED_SOURCE_SHA256
      || contracts.expected_source_bytes !== EXPECTED_SOURCE_BYTES
      || contracts.expected_corroborating_log_sha256 !== EXPECTED_LOG_SHA256
      || contracts.expected_corroborating_log_bytes !== EXPECTED_LOG_BYTES
      || contracts.prepared !== "session-deep-dive-prepared-v4"
      || contracts.redaction !== "session-deep-dive-redaction-v6") {
    fail("bundle source contracts changed");
  }
  const execution = requireObject(bundle.execution_contract, "bundle execution contract");
  const expectedExecution = {
    max_semantic_units_per_packet: 24,
    max_canonical_packet_bytes: MAX_PACKET_CANONICAL_BYTES,
    max_conservative_input_tokens: MAX_CONSERVATIVE_INPUT_TOKENS,
    max_output_tokens: MAX_OUTPUT_TOKENS,
    max_reasoning_tokens: MAX_REASONING_TOKENS,
    reserved_context_tokens: RESERVED_CONTEXT_TOKENS,
    target_context_tokens: TARGET_CONTEXT_TOKENS,
    required_repeats: REQUIRED_REPEATS,
    packet_rotation_offsets: PACKET_ROTATION_OFFSETS,
  };
  if (sha256Value(execution) !== sha256Value(expectedExecution)
      || MAX_CONSERVATIVE_INPUT_TOKENS + MAX_OUTPUT_TOKENS + RESERVED_CONTEXT_TOKENS !== TARGET_CONTEXT_TOKENS) {
    fail("bundle execution contract differs from the frozen 32K-safe budget");
  }
  const limitations = requireArray(bundle.evaluation_limitations, "bundle evaluation limitations");
  if (limitations.length !== 4 || sha256Value(limitations) !== sha256Value(corpus.evaluation_limitations)) {
    fail("bundle must preserve the four frozen evaluation limitations");
  }
  limitations.forEach(item => requireString(item, "bundle evaluation limitation", 768));
  const declared = requireSha(bundle.bundle_sha256, "bundle sha256");
  const unsigned = {...bundle};
  delete unsigned.bundle_sha256;
  if (sha256Value(unsigned) !== declared) fail("bundle SHA-256 seal does not match");
  const binding = requireObject(bundle.prepared_binding, "bundle prepared binding");
  exactKeys(binding, [
    "source_sha256", "source_bytes", "manifest_sha256", "prepare_seal_sha256",
    "record_index_sha256", "unit_index_sha256", "media_ledger_sha256",
    "validation_receipt_sha256", "corroborating_log_sha256", "corroborating_log_bytes",
    "selected_inputs_sha256", "corpus_file_sha256",
  ], "bundle prepared binding");
  if (binding.source_sha256 !== EXPECTED_SOURCE_SHA256 || binding.source_bytes !== EXPECTED_SOURCE_BYTES
      || binding.corroborating_log_sha256 !== EXPECTED_LOG_SHA256
      || binding.corroborating_log_bytes !== EXPECTED_LOG_BYTES) fail("bundle source binding changed");
  for (const [key, digest] of Object.entries(binding)) {
    if (key.endsWith("sha256")) requireSha(digest, `bundle prepared ${key}`);
  }
  const packets = requireArray(bundle.packets, "bundle packets");
  if (packets.length !== 8) fail("bundle must contain the eight fixed packets");
  const expectedPacketIds = ["A", "B1", "B2", "C", "D", "E1", "E2", "F"];
  const globalInputs = new Set();
  const selectedHashRows = [];
  for (let packetIndex = 0; packetIndex < packets.length; packetIndex += 1) {
    const packet = requireObject(packets[packetIndex], "bundle packet");
    exactKeys(packet, [
      "packet_id", "title", "input_units", "selection_receipts",
      "canonical_packet_bytes", "canonical_packet_characters",
    ], "bundle packet");
    if (packet.packet_id !== expectedPacketIds[packetIndex]) fail("bundle packet order or identity changed");
    requireString(packet.title, "bundle packet title", 256);
    const units = requireArray(packet.input_units, "bundle input units");
    if (!units.length || units.length > 24) fail("bundle packet must contain 1-24 inputs");
    const packetPayload = {packet_id: packet.packet_id, title: packet.title, input_units: packet.input_units};
    const packetBytes = canonicalBytes(packetPayload);
    if (packet.canonical_packet_bytes !== packetBytes.length
        || packet.canonical_packet_characters !== [...packetBytes.toString("utf8")].length
        || packetBytes.length > MAX_PACKET_CANONICAL_BYTES) {
      fail("bundle canonical packet size attestation changed");
    }
    for (const unit of units) {
      requireObject(unit, "bundle input");
      const inputId = requireId(unit.input_id, "bundle input id");
      if (globalInputs.has(inputId)) fail("bundle input id is duplicated");
      globalInputs.add(inputId);
      requireSha(unit.content_sha256, "bundle input content sha256");
      selectedHashRows.push({input_id: inputId, content_sha256: unit.content_sha256});
      if (!new Set(["primary_transcript", "corroborating_session_log"]).has(unit.source_class)) {
        fail("bundle input source class is invalid");
      }
      requireString(unit.text, "bundle input text", 32_768);
      requireArray(unit.visual_evidence, "bundle visual evidence");
      if (unit.source_class === "primary_transcript") {
        exactKeys(unit, [
          "input_id", "normalized_unit_id", "source_class", "source_selectors", "semantic_kind",
          "text", "content_sha256", "visual_evidence",
        ], "primary bundle input");
        requireId(unit.normalized_unit_id, "bundle normalized unit id");
        requireArray(unit.source_selectors, "bundle source selectors");
        if (sha256Value({semantic_kind: unit.semantic_kind, text: unit.text}) !== unit.content_sha256) {
          fail("bundle primary content hash changed");
        }
      } else {
        exactKeys(unit, [
          "input_id", "log_id", "line_start", "line_end", "source_class", "authority",
          "semantic_kind", "text", "content_sha256", "visual_evidence",
        ], "corroborating bundle input");
        if (unit.authority !== "corroborating_not_authoritative"
            || unit.semantic_kind !== "corroborating_summary") {
          fail("corroborating input lost its non-authoritative label");
        }
        if (sha256Value({semantic_kind: unit.semantic_kind, text: unit.text}) !== unit.content_sha256) {
          fail("bundle corroborating content hash changed");
        }
      }
    }
    requireArray(packet.selection_receipts, "bundle selection receipts");
  }
  if (binding.selected_inputs_sha256 !== sha256Value(selectedHashRows)) {
    fail("bundle selected-input closure changed");
  }
  assertSafe(bundle, "bundle");
  return bundle;
}

function runPythonPreflight(args, bundle) {
  const toolStat = fs.lstatSync(PYTHON_PREFLIGHT_PATH);
  if (!toolStat.isFile() || toolStat.isSymbolicLink()
      || fs.realpathSync(PYTHON_PREFLIGHT_PATH) !== PYTHON_PREFLIGHT_PATH
      || sha256Bytes(fs.readFileSync(PYTHON_PREFLIGHT_PATH)) !== PYTHON_PREFLIGHT_SHA256) {
    fail("Python preflight tool differs from the compiled reviewed tool");
  }
  const command = [
    PYTHON_PREFLIGHT_PATH, "preflight", "--corpus", FIXED_CORPUS_PATH, "--bundle", args.bundle,
    "--prepared-workdir", args.preparedWorkdir, "--corroborating-log", args.corroboratingLog,
  ];
  const completed = spawnSync(process.env.PYTHON || "python3", command, {
    encoding: "utf8",
    timeout: 35_000,
    maxBuffer: 128 * 1024,
    env: {PATH: process.env.PATH || ""},
  });
  if (completed.error) fail(`Python redaction preflight failed: ${completed.error.message}`);
  if (completed.status !== 0) {
    fail(`Python redaction preflight failed closed: ${(completed.stderr || "no diagnostic").slice(0, 512).trim()}`);
  }
  const receipt = requireObject(parseStrictJson(completed.stdout, "Python preflight receipt"), "Python preflight receipt");
  exactKeys(receipt, [
    "schema_version", "kind", "validated", "corpus_sha256", "bundle_sha256",
    "prepared_binding_sha256", "redaction_contract", "safety_contract", "receipt_sha256",
  ], "Python preflight receipt");
  const unsigned = {...receipt};
  delete unsigned.receipt_sha256;
  if (receipt.schema_version !== 1 || receipt.kind !== "session_bakeoff_preflight_receipt"
      || receipt.validated !== true || receipt.corpus_sha256 !== CORPUS_EXPECTED_SHA256
      || receipt.bundle_sha256 !== bundle.bundle_sha256
      || receipt.prepared_binding_sha256 !== sha256Value(bundle.prepared_binding)
      || receipt.redaction_contract !== "session-deep-dive-redaction-v6"
      || receipt.safety_contract !== "strict_keys_and_v6_defense_in_depth-v1"
      || receipt.receipt_sha256 !== sha256Value(unsigned)) {
    fail("Python preflight receipt binding changed");
  }
  assertSafe(receipt, "Python preflight receipt");
  return receipt;
}

function verifyPreparedAgainstBundle(args, bundle) {
  const workStat = fs.lstatSync(args.preparedWorkdir);
  if (!workStat.isDirectory() || workStat.isSymbolicLink()) {
    fail("prepared workdir must be a non-symlink directory");
  }
  if (fs.readdirSync(args.preparedWorkdir).some(name => /\.jsonl(?:\.gz)?$/i.test(name))) {
    fail("prepared workdir contains raw JSONL");
  }
  const readSidecar = (name, label) => readRegularJson(path.join(args.preparedWorkdir, name), label);
  const manifestInput = readSidecar("manifest.json", "prepared manifest");
  const sealInput = readSidecar("prepare-seal.json", "prepare seal");
  const recordInput = readSidecar("record-index.json", "record index");
  const unitInput = readSidecar("unit-index.json", "unit index");
  const mediaInput = readSidecar("media-ledger.json", "media ledger");
  const hashes = {
    manifest_sha256: sha256Bytes(manifestInput.raw),
    prepare_seal_sha256: sha256Bytes(sealInput.raw),
    record_index_sha256: sha256Bytes(recordInput.raw),
    unit_index_sha256: sha256Bytes(unitInput.raw),
    media_ledger_sha256: sha256Bytes(mediaInput.raw),
  };
  for (const [key, digest] of Object.entries(hashes)) {
    if (bundle.prepared_binding[key] !== digest) fail(`prepared ${key} differs from bundle binding`);
  }
  const prepared = requireObject(manifestInput.value, "prepared manifest");
  exactKeys(prepared, [
    "schema_version", "prepared_contract", "redaction_contract", "session_id", "source",
    "record_index_sha256", "unit_index_sha256", "media_ledger_sha256",
  ], "prepared manifest");
  const source = requireObject(prepared.source, "prepared source");
  exactKeys(source, ["sha256", "bytes"], "prepared source");
  if (prepared.schema_version !== 4 || prepared.prepared_contract !== "session-deep-dive-prepared-v4"
      || prepared.redaction_contract !== "session-deep-dive-redaction-v6"
      || prepared.session_id !== bundle.corpus_manifest.session_id
      || source.sha256 !== EXPECTED_SOURCE_SHA256 || source.bytes !== EXPECTED_SOURCE_BYTES
      || prepared.record_index_sha256 !== hashes.record_index_sha256
      || prepared.unit_index_sha256 !== hashes.unit_index_sha256
      || prepared.media_ledger_sha256 !== hashes.media_ledger_sha256) {
    fail("prepared manifest contract or closure binding changed");
  }
  const expectedSeal = {
    schema_version: 4,
    kind: "session-deep-dive-prepare-seal-v4",
    prepared_contract: "session-deep-dive-prepared-v4",
    redaction_contract: "session-deep-dive-redaction-v6",
    source_sha256: EXPECTED_SOURCE_SHA256,
    manifest_sha256: hashes.manifest_sha256,
    record_index_sha256: hashes.record_index_sha256,
    unit_index_sha256: hashes.unit_index_sha256,
    media_ledger_sha256: hashes.media_ledger_sha256,
  };
  if (sha256Value(sealInput.value) !== sha256Value(expectedSeal)) fail("prepare seal closure changed");

  const recordIndex = requireObject(recordInput.value, "record index");
  exactKeys(recordIndex, ["schema_version", "kind", "source_sha256", "records"], "record index");
  if (recordIndex.schema_version !== 4 || recordIndex.kind !== "session-deep-dive-record-index-v4"
      || recordIndex.source_sha256 !== EXPECTED_SOURCE_SHA256) fail("record index contract changed");
  const recordMap = new Map();
  for (const rowValue of requireArray(recordIndex.records, "record rows")) {
    const row = requireObject(rowValue, "record row");
    exactKeys(row, ["record_id", "turn_id", "normalized_unit_ids"], "record row");
    requireInteger(row.record_id, "record id", 1, 10_000_000);
    requireString(row.turn_id, "record turn id", 64);
    const key = `${row.record_id}\u0000${row.turn_id}`;
    if (recordMap.has(key)) fail("record selector is ambiguous");
    const ids = requireArray(row.normalized_unit_ids, "record normalized units");
    if (!ids.length || new Set(ids).size !== ids.length) fail("record normalized units are empty or duplicated");
    ids.forEach(id => requireId(id, "normalized unit id"));
    recordMap.set(key, ids);
  }
  const unitIndex = requireObject(unitInput.value, "unit index");
  exactKeys(unitIndex, ["schema_version", "kind", "source_sha256", "units"], "unit index");
  if (unitIndex.schema_version !== 4 || unitIndex.kind !== "session-deep-dive-unit-index-v4"
      || unitIndex.source_sha256 !== EXPECTED_SOURCE_SHA256) fail("unit index contract changed");
  const unitMap = new Map();
  for (const unitValue of requireArray(unitIndex.units, "normalized units")) {
    const unit = requireObject(unitValue, "normalized unit");
    exactKeys(unit, ["normalized_unit_id", "source_selectors", "semantic_kind", "text", "content_sha256"], "normalized unit");
    const id = requireId(unit.normalized_unit_id, "normalized unit id");
    if (unitMap.has(id)) fail("normalized unit id is ambiguous");
    requireString(unit.text, "normalized unit text", 32_768);
    if (sha256Value({semantic_kind: unit.semantic_kind, text: unit.text}) !== unit.content_sha256) {
      fail("normalized unit content hash changed");
    }
    unitMap.set(id, unit);
  }
  for (const [selectorKey, ids] of recordMap) {
    for (const id of ids) {
      const unit = unitMap.get(id);
      if (!unit) fail("record index references an unknown normalized unit");
      const reciprocal = unit.source_selectors.some(row => `${row.record_id}\u0000${row.turn_id}` === selectorKey);
      if (!reciprocal) fail("record/unit mapping is not reciprocal");
    }
  }
  for (const [id, unit] of unitMap) {
    for (const selector of requireArray(unit.source_selectors, "unit source selectors")) {
      const ids = recordMap.get(`${selector.record_id}\u0000${selector.turn_id}`) || [];
      if (!ids.includes(id)) fail("unit/record mapping is not reciprocal");
    }
  }

  const ledger = requireObject(mediaInput.value, "media ledger");
  exactKeys(ledger, ["schema_version", "contract", "source_sha256", "occurrences", "assets", "groups"], "media ledger");
  if (ledger.schema_version !== 1 || ledger.contract !== "session-deep-dive-media-ledger-v1"
      || ledger.source_sha256 !== EXPECTED_SOURCE_SHA256) fail("media ledger contract changed");
  const assets = new Set();
  for (const asset of requireArray(ledger.assets, "media assets")) {
    exactKeys(requireObject(asset, "media asset"), ["asset_sha256", "media_type", "width", "height", "byte_length"], "media asset");
    const digest = requireSha(asset.asset_sha256, "media asset sha256");
    if (assets.has(digest)) fail("media asset is duplicated");
    assets.add(digest);
  }
  const occurrenceMap = new Map();
  const occurrenceBySelector = new Map();
  for (const occurrence of requireArray(ledger.occurrences, "media occurrences")) {
    exactKeys(requireObject(occurrence, "media occurrence"), [
      "occurrence_id", "record_id", "turn_id", "ordinal", "asset_sha256", "visual_group",
    ], "media occurrence");
    const id = requireId(occurrence.occurrence_id, "media occurrence id");
    if (occurrenceMap.has(id) || !assets.has(occurrence.asset_sha256)) fail("media occurrence binding is invalid");
    occurrenceMap.set(id, occurrence);
    const key = `${occurrence.record_id}\u0000${occurrence.turn_id}\u0000${occurrence.visual_group}`;
    if (!occurrenceBySelector.has(key)) occurrenceBySelector.set(key, []);
    occurrenceBySelector.get(key).push(occurrence);
  }
  const groupMap = new Map();
  for (const group of requireArray(ledger.groups, "media groups")) {
    exactKeys(requireObject(group, "media group"), ["visual_group", "occurrence_ids", "asset_sha256s"], "media group");
    const id = requireId(group.visual_group, "visual group id");
    if (groupMap.has(id)) fail("visual group is duplicated");
    const occurrenceIds = requireArray(group.occurrence_ids, "group occurrences");
    const assetHashes = requireArray(group.asset_sha256s, "group assets");
    const expectedAssets = [...new Set(occurrenceIds.map(item => {
      const occurrence = occurrenceMap.get(item);
      if (!occurrence || occurrence.visual_group !== id) fail("visual group occurrence binding changed");
      return occurrence.asset_sha256;
    }))].sort();
    if (sha256Value(assetHashes) !== sha256Value(expectedAssets)) fail("visual group asset closure changed");
    groupMap.set(id, group);
  }

  const logRaw = readRegularBytes(args.corroboratingLog, "corroborating partial log", 1024 * 1024);
  if (logRaw.length !== EXPECTED_LOG_BYTES || sha256Bytes(logRaw) !== EXPECTED_LOG_SHA256) {
    fail("corroborating partial log differs from the pinned log");
  }
  const logLines = logRaw.toString("utf8").split(/\r?\n/u);
  for (let packetIndex = 0; packetIndex < bundle.packets.length; packetIndex += 1) {
    const packet = bundle.packets[packetIndex];
    const corpusPacket = bundle.corpus_manifest.packets[packetIndex];
    const expectedReceipts = [];
    const selectedUnitIds = [];
    for (const selector of corpusPacket.primary_units) {
      const ids = recordMap.get(`${selector.record_id}\u0000${selector.turn_id}`);
      if (!ids || !ids.length) fail(`packet ${packet.packet_id} selector is missing from record index`);
      const receipt = {record_id: selector.record_id, turn_id: selector.turn_id, normalized_unit_ids: ids};
      if (selector.visual_group !== undefined) {
        const occurrences = occurrenceBySelector.get(`${selector.record_id}\u0000${selector.turn_id}\u0000${selector.visual_group}`) || [];
        const group = groupMap.get(selector.visual_group);
        if (!occurrences.length || !group) fail("visual selector has no exact bound ledger occurrence");
        if (selector.multi_image === true && new Set(group.asset_sha256s).size < 2) {
          fail("multi-image selector has fewer than two distinct bound assets");
        }
        receipt.visual_evidence = {
          visual_group: selector.visual_group,
          occurrence_ids: occurrences.map(row => row.occurrence_id).sort(),
          asset_sha256s: group.asset_sha256s,
          multi_image: selector.multi_image === true,
        };
      }
      expectedReceipts.push(receipt);
      ids.forEach(id => { if (!selectedUnitIds.includes(id)) selectedUnitIds.push(id); });
    }
    const primaryInputs = packet.input_units.filter(unit => unit.source_class === "primary_transcript");
    if (sha256Value(primaryInputs.map(unit => unit.normalized_unit_id)) !== sha256Value(selectedUnitIds)) {
      fail(`packet ${packet.packet_id} normalized-unit selection changed`);
    }
    for (const input of primaryInputs) {
      const unit = unitMap.get(input.normalized_unit_id);
      if (!unit || sha256Value(input.source_selectors) !== sha256Value(unit.source_selectors)
          || input.content_sha256 !== unit.content_sha256 || input.text !== unit.text) {
        fail(`packet ${packet.packet_id} normalized-unit content changed`);
      }
    }
    for (const selector of corpusPacket.corroborating_units) {
      expectedReceipts.push({log_id: selector.log_id, line_start: selector.line_start, line_end: selector.line_end});
      const input = packet.input_units.find(unit => unit.log_id === selector.log_id);
      const text = logLines.slice(selector.line_start - 1, selector.line_end).join("\n");
      if (!input || input.text !== text || input.authority !== "corroborating_not_authoritative") {
        fail(`packet ${packet.packet_id} corroborating range changed`);
      }
    }
    if (sha256Value(packet.selection_receipts) !== sha256Value(expectedReceipts)) {
      fail(`packet ${packet.packet_id} selector receipts changed`);
    }
  }
  assertSafe(recordIndex, "record index");
  assertSafe(unitIndex, "unit index");
  assertSafe(ledger, "media ledger");
  return hashes;
}

function validateBinding(value, environment) {
  const binding = requireObject(value, "lifecycle binding");
  exactKeys(binding, [
    "schema_version", "kind", "identifier", "model_key", "selected_variant", "profile",
  ], "lifecycle binding");
  if (binding.schema_version !== 1 || binding.kind !== "session_bakeoff_lifecycle_binding") {
    fail("unsupported lifecycle binding contract");
  }
  for (const [field, environmentField] of [
    ["identifier", "identifier"], ["model_key", "modelKey"],
    ["selected_variant", "selectedVariant"], ["profile", "profile"],
  ]) {
    requireString(binding[field], `binding ${field}`, 512);
    if (binding[field] !== environment[environmentField]) fail(`binding ${field} differs from lifecycle environment`);
  }
  return binding;
}

function packetResponseJsonSchema(bundle, packet) {
  const inputIds = packet.input_units.map(unit => unit.input_id);
  const predicates = [
    ...bundle.corpus_manifest.gold_facts.map(fact => fact.fact_id),
    ...bundle.corpus_manifest.critical_contradictions.map(rule => rule.rule_id),
  ];
  const claim = {
    type: "object", additionalProperties: false,
    properties: {
      claim_id: {type: "string", minLength: 1, maxLength: 128},
      predicate_id: {type: "string", enum: predicates},
      polarity: {type: "string", enum: [...POLARITIES]},
      state: {type: "string", enum: [...STATES]},
      text: {type: "string", minLength: 1, maxLength: 4096},
      citations: {type: "array", minItems: 1, maxItems: MAX_CITATIONS, uniqueItems: true, items: {type: "string", enum: inputIds}},
    },
    required: ["claim_id", "predicate_id", "polarity", "state", "text", "citations"],
  };
  return {
    type: "object", additionalProperties: false,
    properties: {
      schema_version: {const: 2},
      kind: {const: "session_bakeoff_packet_response"},
      corpus_sha256: {const: bundle.corpus_sha256},
      bundle_sha256: {const: bundle.bundle_sha256},
      packet_result: {
        type: "object", additionalProperties: false,
        properties: {
          packet_id: {const: packet.packet_id},
          claims: {type: "array", maxItems: MAX_CLAIMS, items: claim},
          unit_dispositions: {
            type: "array", minItems: inputIds.length, maxItems: inputIds.length,
            items: {
              type: "object", additionalProperties: false,
              properties: {
                input_id: {type: "string", enum: inputIds},
                disposition: {type: "string", enum: [...DISPOSITIONS]},
              },
              required: ["input_id", "disposition"],
            },
          },
        },
        required: ["packet_id", "claims", "unit_dispositions"],
      },
      report_sections: {
        type: "array", minItems: 1, maxItems: 3,
        items: {
          type: "object", additionalProperties: false,
          properties: {
            section_id: {type: "string", minLength: 1, maxLength: 128},
            title: {type: "string", minLength: 1, maxLength: 256},
            purpose: {type: "string", minLength: 1, maxLength: 1024},
            claim_ids: {type: "array", maxItems: MAX_CLAIMS, uniqueItems: true, items: {type: "string", minLength: 1, maxLength: 128}},
          },
          required: ["section_id", "title", "purpose", "claim_ids"],
        },
      },
    },
    required: ["schema_version", "kind", "corpus_sha256", "bundle_sha256", "packet_result", "report_sections"],
  };
}

function validatePacketResponse(value, bundle, packet) {
  const label = `packet ${packet.packet_id}`;
  const response = requireObject(value, `${label} response`);
  exactKeys(response, [
    "schema_version", "kind", "corpus_sha256", "bundle_sha256", "packet_result", "report_sections",
  ], `${label} response`);
  if (response.schema_version !== 2 || response.kind !== "session_bakeoff_packet_response"
      || response.corpus_sha256 !== bundle.corpus_sha256 || response.bundle_sha256 !== bundle.bundle_sha256) {
    fail(`${label} response contract or binding is invalid`);
  }
  const result = requireObject(response.packet_result, `${label} result`);
  exactKeys(result, ["packet_id", "claims", "unit_dispositions"], `${label} result`);
  if (result.packet_id !== packet.packet_id) fail(`${label} result identity changed`);
  const allowedInputs = new Set(packet.input_units.map(unit => unit.input_id));
  const claims = requireArray(result.claims, `${label} claims`);
  if (claims.length > MAX_CLAIMS) fail(`${label} has too many claims`);
  const claimIds = new Set();
  for (const claimValue of claims) {
    const claim = requireObject(claimValue, `${label} claim`);
    exactKeys(claim, ["claim_id", "predicate_id", "polarity", "state", "text", "citations"], `${label} claim`);
    const claimId = requireId(claim.claim_id, `${label} claim id`);
    if (claimIds.has(claimId)) fail(`${label} claim id is duplicated`);
    claimIds.add(claimId);
    const predicates = new Set([
      ...bundle.corpus_manifest.gold_facts.map(fact => fact.fact_id),
      ...bundle.corpus_manifest.critical_contradictions.map(rule => rule.rule_id),
    ]);
    if (!predicates.has(claim.predicate_id) || !POLARITIES.has(claim.polarity)) {
      fail(`${label} claim predicate or polarity is invalid`);
    }
    if (!STATES.has(claim.state)) fail(`${label} claim state is invalid`);
    requireString(claim.text, `${label} claim text`, 4096);
    const citations = requireArray(claim.citations, `${label} citations`);
    if (!citations.length || citations.length > MAX_CITATIONS || new Set(citations).size !== citations.length
        || citations.some(citation => !allowedInputs.has(citation))) {
      fail(`${label} citation does not uniquely resolve`);
    }
  }
  const dispositions = requireArray(result.unit_dispositions, `${label} dispositions`);
  const dispositionInputs = [];
  for (const dispositionValue of dispositions) {
    const disposition = requireObject(dispositionValue, `${label} disposition`);
    exactKeys(disposition, ["input_id", "disposition"], `${label} disposition`);
    dispositionInputs.push(requireId(disposition.input_id, `${label} disposition input id`));
    if (!DISPOSITIONS.has(disposition.disposition)) fail(`${label} disposition is invalid`);
  }
  if (dispositionInputs.length !== allowedInputs.size || new Set(dispositionInputs).size !== dispositionInputs.length
      || dispositionInputs.some(inputId => !allowedInputs.has(inputId))) {
    fail(`${label} must dispose each input exactly once`);
  }
  const sections = requireArray(response.report_sections, `${label} report sections`);
  if (!sections.length || sections.length > 3) fail(`${label} must return 1-3 report sections`);
  const sectionIds = new Set();
  for (const sectionValue of sections) {
    const section = requireObject(sectionValue, `${label} section`);
    exactKeys(section, ["section_id", "title", "purpose", "claim_ids"], `${label} section`);
    const sectionId = requireId(section.section_id, `${label} section id`);
    if (sectionIds.has(sectionId)) fail(`${label} section id is duplicated`);
    sectionIds.add(sectionId);
    requireString(section.title, `${label} section title`, 256);
    requireString(section.purpose, `${label} section purpose`, 1024);
    const references = requireArray(section.claim_ids, `${label} section claims`);
    if (references.length > MAX_CLAIMS || new Set(references).size !== references.length
        || references.some(reference => !claimIds.has(reference))) {
      fail(`${label} section claim reference is invalid`);
    }
  }
  if (unsafeFindings(response, `${label} response`).length) fail(`${label} response contains unsafe material`);
  return response;
}

function validateResponse(value, bundle) {
  const response = requireObject(value, "model response");
  exactKeys(response, [
    "schema_version", "kind", "corpus_sha256", "bundle_sha256", "packet_results", "report_outline",
  ], "model response");
  if (response.schema_version !== 2 || response.kind !== "session_bakeoff_response"
      || response.corpus_sha256 !== bundle.corpus_sha256 || response.bundle_sha256 !== bundle.bundle_sha256) {
    fail("model response contract or binding is invalid");
  }
  const packets = new Map(bundle.packets.map(packet => [packet.packet_id, packet]));
  const results = requireArray(response.packet_results, "model packet results");
  if (results.length !== packets.size) fail("model response must include each packet exactly once");
  const seenPackets = new Set();
  const claimIds = new Set();
  let claimCount = 0;
  for (const resultValue of results) {
    const result = requireObject(resultValue, "model packet result");
    exactKeys(result, ["packet_id", "claims", "unit_dispositions"], "model packet result");
    const packetId = requireId(result.packet_id, "model packet id");
    if (!packets.has(packetId) || seenPackets.has(packetId)) fail("model packet is missing, unknown, or duplicated");
    seenPackets.add(packetId);
    const allowedInputs = new Set(packets.get(packetId).input_units.map(unit => unit.input_id));
    const claims = requireArray(result.claims, "model claims");
    claimCount += claims.length;
    if (claimCount > MAX_CLAIMS) fail("model response has too many claims");
    for (const claimValue of claims) {
      const claim = requireObject(claimValue, "model claim");
      exactKeys(claim, ["claim_id", "predicate_id", "polarity", "state", "text", "citations"], "model claim");
      const claimId = requireId(claim.claim_id, "model claim id");
      if (claimIds.has(claimId)) fail("model claim id is duplicated");
      claimIds.add(claimId);
      const predicates = new Set([
        ...bundle.corpus_manifest.gold_facts.map(fact => fact.fact_id),
        ...bundle.corpus_manifest.critical_contradictions.map(rule => rule.rule_id),
      ]);
      if (!predicates.has(claim.predicate_id) || !POLARITIES.has(claim.polarity)) {
        fail("model claim predicate or polarity is invalid");
      }
      if (!STATES.has(claim.state)) fail("model claim state is invalid");
      requireString(claim.text, "model claim text", 4096);
      const citations = requireArray(claim.citations, "model claim citations");
      if (!citations.length || citations.length > MAX_CITATIONS || new Set(citations).size !== citations.length
          || citations.some(citation => !allowedInputs.has(citation))) {
        fail("model claim citation does not uniquely resolve within its packet");
      }
    }
    const dispositions = requireArray(result.unit_dispositions, "model dispositions");
    const dispositionInputs = [];
    for (const dispositionValue of dispositions) {
      const disposition = requireObject(dispositionValue, "model disposition");
      exactKeys(disposition, ["input_id", "disposition"], "model disposition");
      dispositionInputs.push(requireId(disposition.input_id, "model disposition input id"));
      if (!DISPOSITIONS.has(disposition.disposition)) fail("model disposition is invalid");
    }
    if (new Set(dispositionInputs).size !== dispositionInputs.length
        || dispositionInputs.length !== allowedInputs.size
        || dispositionInputs.some(inputId => !allowedInputs.has(inputId))) {
      fail("model must provide exactly one disposition per packet input");
    }
  }
  const outline = requireArray(response.report_outline, "model report outline");
  if (!outline.length || outline.length > 24) fail("model report outline must have 1-24 sections");
  const sectionIds = new Set();
  for (const sectionValue of outline) {
    const section = requireObject(sectionValue, "model report section");
    exactKeys(section, ["section_id", "title", "purpose", "claim_ids"], "model report section");
    const sectionId = requireId(section.section_id, "model section id");
    if (sectionIds.has(sectionId)) fail("model section id is duplicated");
    sectionIds.add(sectionId);
    requireString(section.title, "model section title", 256);
    requireString(section.purpose, "model section purpose", 1024);
    const references = requireArray(section.claim_ids, "model section claim ids");
    if (references.length > MAX_CLAIMS || new Set(references).size !== references.length
        || references.some(reference => !claimIds.has(reference))) fail("model section claim reference is invalid");
  }
  assertFinite(response, "model response");
  const findings = unsafeFindings(response);
  if (findings.length) fail(`unsafe model response refused: ${findings[0]}`);
  return response;
}

function unsafeFindings(value, label = "response") {
  const findings = [];
  if (Array.isArray(value)) {
    value.forEach((item, index) => findings.push(...unsafeFindings(item, `${label}[${index}]`)));
  } else if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      if (/(?:^|_)(?:raw(?:_media)?|raw_base64|base64(?:url)?|media_payload|pixels?|attachment_path|source_path|absolute_path|home_path|temp_path|file_path|secret|password|authorization|api_key)(?:$|_)/i.test(key)) {
        findings.push(`${label}.${key}: forbidden data-bearing field`);
      }
      findings.push(...unsafeFindings(item, `${label}.${key}`));
    }
  } else if (typeof value === "string") {
    if (/(?:^|[\s'"(])(?:~(?:\/|[A-Za-z0-9._-]+\/)|\/(?:Users|home|private|tmp|var\/folders|Volumes)\/)/i.test(value)) findings.push(`${label}: home, private absolute, or temporary path`);
    if (/(?:^|[\s'"(])(?:[A-Za-z]:[\\/]|\\{2,}[^\\\s]+\\+[^\\\s]+|[A-Za-z0-9._-]+\\[A-Za-z0-9._-]+)/.test(value)) findings.push(`${label}: Windows or UNC path`);
    if (/(?:^|[\s'"(])\.\.\//.test(value)) findings.push(`${label}: parent-relative path`);
    if (/(?:data:|file:|blob:)/i.test(value)) findings.push(`${label}: raw media or local-file URI`);
    if (!(value.length === 64 && SHA256_PATTERN.test(value))
        && /(?<![A-Za-z0-9_+/=-])[A-Za-z0-9_+/=-]{128,}(?![A-Za-z0-9_+/=-])/.test(value)) {
      findings.push(`${label}: base64/base64url-like payload`);
    }
    if (/(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{12,}|\bBearer\s+[A-Za-z0-9._~+/=-]{12,}|(?:password|secret|api[_ -]?key)\s*[:=]\s*\S+)/i.test(value)) findings.push(`${label}: secret-like payload`);
  }
  return findings;
}

function assertSafe(value, label = "value") {
  const findings = unsafeFindings(value, label);
  if (findings.length) fail(`unsafe ${label}: ${findings[0]}`);
}

function fingerprintTreeSync(root) {
  const rootStat = fs.lstatSync(root);
  if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) {
    fail("SDK dependency root must be a non-symlink directory");
  }
  const rows = [];
  const walk = directory => {
    const entries = fs.readdirSync(directory, {withFileTypes: true})
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
          sha256: sha256Bytes(fs.readFileSync(file)),
        });
      } else if (entry.isSymbolicLink()) {
        const target = fs.readlinkSync(file);
        const resolved = path.resolve(path.dirname(file), target);
        if (resolved !== root && !resolved.startsWith(`${root}${path.sep}`)) {
          fail("SDK dependency symlink escapes its reviewed root");
        }
        rows.push({kind: "symlink", path: relative, target});
      } else {
        fail("SDK dependency tree contains an unsupported entry");
      }
    }
  };
  walk(root);
  return {files: rows, sha256: sha256Value(rows)};
}

function packageRootForResolvedEntry(entry, expectedName) {
  let directory = fs.lstatSync(entry).isDirectory() ? entry : path.dirname(entry);
  while (true) {
    const metadataPath = path.join(directory, "package.json");
    if (fs.existsSync(metadataPath)) {
      const metadata = requireObject(
        parseStrictJson(fs.readFileSync(metadataPath, "utf8"), "SDK package metadata"),
        "SDK package metadata",
      );
      if (metadata.name === expectedName) return fs.realpathSync(directory);
    }
    const parent = path.dirname(directory);
    if (parent === directory) break;
    directory = parent;
  }
  fail(`could not bind SDK dependency package root for ${expectedName}`);
}

function fingerprintSdkDependencyClosure(sdkRoot) {
  const queue = [fs.realpathSync(sdkRoot)];
  const packages = new Map();
  const rawEdges = [];
  while (queue.length > 0) {
    const root = fs.realpathSync(queue.shift());
    if (packages.has(root)) continue;
    const metadata = requireObject(
      parseStrictJson(fs.readFileSync(path.join(root, "package.json"), "utf8"), "SDK dependency package metadata"),
      "SDK dependency package metadata",
    );
    requireString(metadata.name, "SDK dependency name", 256);
    requireString(metadata.version, "SDK dependency version", 128);
    const tree = fingerprintTreeSync(root);
    const id = `${metadata.name}@${metadata.version}:${tree.sha256}`;
    packages.set(root, {id, name: metadata.name, version: metadata.version, tree_sha256: tree.sha256});
    const dependencyKinds = new Map();
    for (const dependency of Object.keys(metadata.dependencies || {})) dependencyKinds.set(dependency, "required");
    for (const dependency of Object.keys(metadata.optionalDependencies || {})) dependencyKinds.set(dependency, "optional");
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
        fail(`required SDK dependency is unavailable: ${dependency}: ${error.message}`);
      }
      const childRoot = packageRootForResolvedEntry(resolved, dependency);
      queue.push(childRoot);
      rawEdges.push({from_root: root, dependency, to_root: childRoot});
    }
  }
  const nodes = [...packages.values()].sort((left, right) => left.id.localeCompare(right.id));
  const edges = rawEdges.map(edge => ({
    from: packages.get(edge.from_root).id,
    dependency: edge.dependency,
    to: packages.get(edge.to_root).id,
  })).sort((left, right) => JSON.stringify(sortValue(left)).localeCompare(JSON.stringify(sortValue(right))));
  const graph = {nodes, edges};
  return {graph, sha256: sha256Value(graph)};
}

function immutableFileIdentity(statValue) {
  return {
    device: String(statValue.dev), inode: String(statValue.ino), size: String(statValue.size),
    mode: String(statValue.mode), mtime_ns: String(statValue.mtimeNs), ctime_ns: String(statValue.ctimeNs),
  };
}

function verifyReviewedSdkFromEnvironment() {
  const supplied = requireEnvironment("LMSTUDIO_BAKEOFF_SDK_ENTRY_PATH", 4096);
  if (!path.isAbsolute(supplied)) fail("LMSTUDIO_BAKEOFF_SDK_ENTRY_PATH must be absolute");
  const pathStat = fs.lstatSync(supplied);
  if (!pathStat.isFile() || pathStat.isSymbolicLink() || fs.realpathSync(supplied) !== supplied) {
    fail("LMSTUDIO_BAKEOFF_SDK_ENTRY_PATH must be an absolute regular non-symlink real path");
  }
  const environmentDigests = {
    entrySha256: requireSha(requireEnvironment("LMSTUDIO_BAKEOFF_SDK_ENTRY_SHA256", 64), "SDK entry environment digest"),
    closureSha256: requireSha(requireEnvironment("LMSTUDIO_BAKEOFF_SDK_CLOSURE_SHA256", 64), "SDK closure environment digest"),
    dependencyClosureSha256: requireSha(requireEnvironment("LMSTUDIO_BAKEOFF_SDK_DEPENDENCY_CLOSURE_SHA256", 64), "SDK dependency closure environment digest"),
  };
  const entry = fs.realpathSync(supplied);
  const flags = fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0);
  let descriptor;
  try {
    descriptor = fs.openSync(entry, flags);
    const initialDescriptorIdentity = immutableFileIdentity(fs.fstatSync(descriptor, {bigint: true}));
    const initialPathIdentity = immutableFileIdentity(fs.lstatSync(entry, {bigint: true}));
    if (sha256Value(initialDescriptorIdentity) !== sha256Value(initialPathIdentity)) {
      fail("LM Studio SDK entry changed while it was opened");
    }
    const sdkRoot = packageRootForResolvedEntry(entry, REVIEWED_SDK.name);
    const metadata = requireObject(
      parseStrictJson(fs.readFileSync(path.join(sdkRoot, "package.json"), "utf8"), "reviewed SDK metadata"),
      "reviewed SDK metadata",
    );
    const digestEntry = () => {
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
    };
    const first = {
      entrySha256: digestEntry(),
      closureSha256: fingerprintTreeSync(sdkRoot).sha256,
      dependencyClosureSha256: fingerprintSdkDependencyClosure(sdkRoot).sha256,
    };
    const second = {
      entrySha256: digestEntry(),
      closureSha256: fingerprintTreeSync(sdkRoot).sha256,
      dependencyClosureSha256: fingerprintSdkDependencyClosure(sdkRoot).sha256,
    };
    const finalDescriptorIdentity = immutableFileIdentity(fs.fstatSync(descriptor, {bigint: true}));
    const finalPathIdentity = immutableFileIdentity(fs.lstatSync(entry, {bigint: true}));
    if (metadata.name !== REVIEWED_SDK.name || metadata.version !== REVIEWED_SDK.version
        || sha256Value(first) !== sha256Value(second)
        || sha256Value(initialDescriptorIdentity) !== sha256Value(finalDescriptorIdentity)
        || sha256Value(initialDescriptorIdentity) !== sha256Value(finalPathIdentity)
        || first.entrySha256 !== REVIEWED_SDK.entrySha256
        || first.closureSha256 !== REVIEWED_SDK.closureSha256
        || first.dependencyClosureSha256 !== REVIEWED_SDK.dependencyClosureSha256
        || sha256Value(first) !== sha256Value(environmentDigests)) {
      fail("installed SDK or dependency closure differs from lifecycle and compiled reviewed digests");
    }
    return Object.freeze({entryPath: entry, ...first, packageIdentity: {name: metadata.name, version: metadata.version}});
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
  }
}

function createClient(reviewedSdk, endpoint) {
  const sdk = require(reviewedSdk.entryPath);
  if (!sdk || typeof sdk.LMStudioClient !== "function") fail("official SDK entry omitted LMStudioClient");
  const client = new sdk.LMStudioClient({
    baseUrl: endpoint,
    verboseErrorMessages: false,
    logger: {debug() {}, info() {}, warn() {}, error() {}},
  });
  return {client, packageIdentity: reviewedSdk.packageIdentity};
}

async function disposeClient(client) {
  if (!client || typeof client[Symbol.asyncDispose] !== "function") {
    fail("official SDK client does not expose async disposal");
  }
  await client[Symbol.asyncDispose]();
}

function normalizeSnapshot(info, loadConfig, processingState) {
  requireObject(info, "loaded model info");
  requireObject(loadConfig, "loaded model config");
  requireObject(processingState, "loaded model processing state");
  for (const field of [
    "modelKey", "identifier", "indexedModelIdentifier", "selectedVariant", "instanceReference",
  ]) requireString(info[field], `loaded model ${field}`, 1024);
  if (info.deviceIdentifier !== null) fail("loaded model is not local-only");
  requireInteger(info.contextLength, "loaded model context length", 1, 10_000_000);
  for (const field of ["ttlMs", "lastUsedTime"]) {
    if (info[field] !== null) requireInteger(info[field], `loaded model ${field}`, 0, Number.MAX_SAFE_INTEGER);
  }
  if (processingState.status !== "idle" || processingState.queued !== 0) fail("loaded model is not idle with an empty queue");
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
    load_config: sortValue(loadConfig),
    processing_state: {status: "idle", queued: 0},
  };
}

function lifecycleEnvironment() {
  const contextLengthText = requireEnvironment("LMSTUDIO_BAKEOFF_CONTEXT_LENGTH", 16);
  if (!/^[1-9][0-9]*$/.test(contextLengthText)) fail("lifecycle context length environment is invalid");
  const processToken = requireEnvironment("LMSTUDIO_BAKEOFF_PROCESS_TOKEN", 64);
  if (!TOKEN_PATTERN.test(processToken)) fail("lifecycle process token is invalid");
  const boundEndpoint = validateLoopbackEndpoint(requireEnvironment("LMSTUDIO_BAKEOFF_ENDPOINT", 256));
  return {
    identifier: requireEnvironment("LMSTUDIO_BAKEOFF_IDENTIFIER", 1024),
    modelKey: requireEnvironment("LMSTUDIO_BAKEOFF_MODEL_KEY", 1024),
    selectedVariant: requireEnvironment("LMSTUDIO_BAKEOFF_SELECTED_VARIANT", 1024),
    profile: requireEnvironment("LMSTUDIO_BAKEOFF_PROFILE", 256),
    snapshotSha256: requireSha(requireEnvironment("LMSTUDIO_BAKEOFF_SNAPSHOT_SHA256", 64), "lifecycle snapshot sha256"),
    instanceReference: requireEnvironment("LMSTUDIO_BAKEOFF_INSTANCE_REFERENCE", 1024),
    indexedModelIdentifier: requireEnvironment("LMSTUDIO_BAKEOFF_INDEXED_MODEL_IDENTIFIER", 2048),
    contextLength: Number(contextLengthText),
    loadConfigSha256: requireSha(requireEnvironment("LMSTUDIO_BAKEOFF_LOAD_CONFIG_SHA256", 64), "lifecycle load-config sha256"),
    processTokenSha256: sha256Bytes(Buffer.from(processToken, "utf8")),
    endpoint: boundEndpoint,
  };
}

function verifySnapshot(snapshot, environment) {
  const expected = {
    identifier: environment.identifier,
    model_key: environment.modelKey,
    selected_variant: environment.selectedVariant,
    instance_reference: environment.instanceReference,
    indexed_model_identifier: environment.indexedModelIdentifier,
    context_length: environment.contextLength,
  };
  for (const [field, value] of Object.entries(expected)) {
    if (snapshot[field] !== value) fail(`loaded snapshot ${field} differs from lifecycle binding`);
  }
  if (sha256Value(snapshot.load_config) !== environment.loadConfigSha256) fail("loaded config digest differs from lifecycle binding");
  if (sha256Value(snapshot) !== environment.snapshotSha256) fail("loaded snapshot digest differs from lifecycle binding");
}

async function boundedStructuredResponse(model, chat, options, label) {
  const controller = new AbortController();
  let timer;
  try {
    const prediction = model.respond(chat, {
      maxTokens: options.maxTokens,
      reasoningBudget: options.reasoningBudget,
      temperature: 0,
      contextOverflowPolicy: "stopAtLimit",
      structured: {type: "json", jsonSchema: options.schema},
      signal: controller.signal,
    });
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => {
        controller.abort(new Error(`${label} deadline exceeded`));
        reject(new CallbackError(`${label} exceeded its deadline`));
      }, options.deadlineMs);
    });
    const result = await Promise.race([Promise.resolve(prediction), deadline]);
    requireObject(result, `${label} result`);
    const stats = requireObject(result.stats, `${label} stats`);
    if (stats.stopReason !== COMPLETE_STOP_REASON) {
      fail(`${label} ended with incomplete stop reason ${String(stats.stopReason)}`);
    }
    const content = requireString(result.content, `${label} content`, MAX_RESULT_BYTES);
    return {value: parseStrictJson(content, `${label} content`), stopReason: stats.stopReason};
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const typeBytes = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(Buffer.concat([typeBytes, data])));
  return Buffer.concat([length, typeBytes, data, checksum]);
}

function syntheticVisionPng() {
  const width = 32;
  const height = 32;
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8;
  header[9] = 2;
  const pixels = Buffer.alloc(height * (1 + width * 3));
  const glyphs = {
    E: ["111", "100", "110", "100", "111"],
    R: ["110", "101", "110", "101", "101"],
  };
  const statusText = "ERR";
  for (let y = 0; y < height; y += 1) {
    const row = y * (1 + width * 3);
    pixels[row] = 0;
    for (let x = 0; x < width; x += 1) {
      const offset = row + 1 + x * 3;
      let color = [5, 10, 20];
      if (y < 5) color = [17, 42, 62];
      if (y === 4) color = [21, 188, 223];
      if (x < 8 && y > 5) color = [11, 25, 42];
      if (x >= 10 && x <= 29 && y >= 7 && y <= 28) color = [19, 34, 52];
      if (x >= 13 && x <= 25 && (y === 15 || y === 19 || y === 23)) color = [160, 174, 192];
      if (x >= 24 && x <= 27 && y >= 9 && y <= 12) color = [239, 71, 111];
      const glyphY = y - 17;
      if (glyphY >= 0 && glyphY < 5) {
        for (let glyphIndex = 0; glyphIndex < statusText.length; glyphIndex += 1) {
          const glyphX = x - (11 + glyphIndex * 4);
          if (glyphX >= 0 && glyphX < 3 && glyphs[statusText[glyphIndex]][glyphY][glyphX] === "1") {
            color = [240, 245, 255];
          }
        }
      }
      [pixels[offset], pixels[offset + 1], pixels[offset + 2]] = color;
    }
  }
  const png = Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk("IHDR", header), pngChunk("IDAT", zlib.deflateSync(pixels, {level: 9})),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
  if (sha256Bytes(png) !== SYNTHETIC_VISION_SHA256) fail("synthetic vision fixture bytes changed");
  return png;
}

function syntheticVisionSha256() {
  return sha256Bytes(syntheticVisionPng());
}

function syntheticVisionGold() {
  return {...SYNTHETIC_VISION_GOLD};
}

async function runVisionProbe(client, model, deadlineMs) {
  if (model.vision !== true) fail("vision probe requested for a model not declared vision-enabled");
  const png = syntheticVisionPng();
  const image = await client.files.prepareImageBase64("synthetic-32x32.png", png.toString("base64"));
  if (!image || typeof image.isImage !== "function" || !image.isImage()) fail("SDK did not recognize the synthetic probe as an image");
  const result = await boundedStructuredResponse(
    model,
    [{
      role: "user",
      content: [
        "Inspect this synthetic 32 by 32 UI schematic.",
        "Report whether a top bar, left sidebar, and main panel are visibly present;",
        "read the three-letter status label; classify its state; and classify the",
        "anomalous colored shape by color, position, and shape.",
      ].join(" "),
      images: [image],
    }],
    {
      deadlineMs: Math.min(deadlineMs, 30_000), maxTokens: VISION_OUTPUT_TOKENS, reasoningBudget: 32,
      schema: {
        type: "object", additionalProperties: false,
        properties: {
          top_bar_present: {type: "boolean"},
          left_sidebar_present: {type: "boolean"},
          main_panel_present: {type: "boolean"},
          status_text: {type: "string", enum: ["ERR", "OK", "WARN", "NONE", "UNREADABLE"]},
          status_state: {type: "string", enum: ["error", "ready", "warning", "none", "unreadable"]},
          anomaly_color: {type: "string", enum: ["rose", "cyan", "gray", "none", "unreadable"]},
          anomaly_position: {type: "string", enum: ["upper_right", "upper_left", "lower_right", "lower_left", "none", "unreadable"]},
          anomaly_shape: {type: "string", enum: ["square", "circle", "triangle", "none", "unreadable"]},
        },
        required: Object.keys(SYNTHETIC_VISION_GOLD),
      },
    },
    "vision probe",
  );
  const value = requireObject(result.value, "vision probe response");
  exactKeys(value, Object.keys(SYNTHETIC_VISION_GOLD), "vision probe response");
  for (const field of ["top_bar_present", "left_sidebar_present", "main_panel_present"]) {
    if (typeof value[field] !== "boolean") fail(`vision probe ${field} must be boolean`);
  }
  const allowedValues = {
    status_text: new Set(["ERR", "OK", "WARN", "NONE", "UNREADABLE"]),
    status_state: new Set(["error", "ready", "warning", "none", "unreadable"]),
    anomaly_color: new Set(["rose", "cyan", "gray", "none", "unreadable"]),
    anomaly_position: new Set(["upper_right", "upper_left", "lower_right", "lower_left", "none", "unreadable"]),
    anomaly_shape: new Set(["square", "circle", "triangle", "none", "unreadable"]),
  };
  for (const [field, allowed] of Object.entries(allowedValues)) {
    if (!allowed.has(value[field])) fail(`vision probe ${field} is outside the finite vocabulary`);
  }
  if (unsafeFindings(value, "vision probe response").length) fail("vision probe response was unsafe");
  const fields = Object.keys(SYNTHETIC_VISION_GOLD);
  const matchedFactIds = [];
  const missingFactIds = [];
  fields.forEach((field, index) => {
    const factId = `V${String(index + 1).padStart(2, "0")}`;
    (value[field] === SYNTHETIC_VISION_GOLD[field] ? matchedFactIds : missingFactIds).push(factId);
  });
  return {
    fixture_id: "synthetic-ui-canary-v1",
    image_sha256: sha256Bytes(png),
    stop_reason: result.stopReason,
    observed: value,
    matched_fact_ids: matchedFactIds,
    missing_fact_ids: missingFactIds,
    score: matchedFactIds.length,
    maximum_score: fields.length,
    passed: missingFactIds.length === 0,
  };
}

function bakeoffPrompt(bundle, packet) {
  const packetEnvelope = {
    schema_version: 1,
    kind: "session_bakeoff_packet_input",
    corpus_sha256: bundle.corpus_sha256,
    bundle_sha256: bundle.bundle_sha256,
    execution_contract: bundle.execution_contract,
    packet,
  };
  const prompt = [
    `You are producing packet ${packet.packet_id} of the evidence plan for a standalone HTML deep-dive report.`,
    "Use every input exactly once through unit_dispositions. Make exhaustive, atomic claims; cite only input_id values from the same packet.",
    "Keep requested, diagnosed, implemented, test-passed, built, installed, live-verified, failed, and unresolved states distinct.",
    "Preserve wrong turns and contradictions. Corroborating log inputs are explicitly non-authoritative and cannot replace primary transcript evidence.",
    "Do not emit secrets, raw media, base64, or private attachment paths. Safe repository-relative paths and ordinary HTTPS documentation URLs are allowed. Return only JSON matching the supplied schema.",
    canonicalBytes(packetEnvelope).toString("utf8"),
  ].join("\n\n");
  if (Buffer.byteLength(prompt, "utf8") > MAX_PROMPT_BYTES) fail("bake-off prompt exceeds the byte limit");
  return prompt;
}

async function packetPromptMetrics(model, chat, schema) {
  if (typeof model.applyPromptTemplate !== "function" || typeof model.countTokens !== "function") {
    fail("loaded model does not expose exact prompt token accounting");
  }
  const formatted = await model.applyPromptTemplate(chat);
  requireString(formatted, "formatted packet prompt", MAX_PROMPT_BYTES);
  const formattedTokens = await model.countTokens(formatted);
  requireInteger(formattedTokens, "formatted packet prompt tokens", 1, 1_000_000);
  const schemaBytes = canonicalBytes(schema).length;
  const conservativeInputTokens = formattedTokens + schemaBytes;
  if (conservativeInputTokens > MAX_CONSERVATIVE_INPUT_TOKENS) {
    fail(
      `packet conservative input bound ${conservativeInputTokens} exceeds `
      + `${MAX_CONSERVATIVE_INPUT_TOKENS} tokens`,
    );
  }
  return {
    formatted_prompt_tokens: formattedTokens,
    schema_utf8_bytes_as_token_upper_bound: schemaBytes,
    conservative_input_tokens: conservativeInputTokens,
  };
}

async function runInferenceBatch(client, bundle, args, environment) {
  const startedAt = Date.now();
  const remainingDeadline = label => {
    const remaining = args.deadlineMs - (Date.now() - startedAt);
    if (remaining < 1_000) fail(`${label} has no remaining callback deadline`);
    return remaining;
  };
  const loaded = await client.llm.listLoaded();
  if (!Array.isArray(loaded) || loaded.length !== 1) {
    fail("callback requires exactly one already-loaded LLM");
  }
  const loadedModel = loaded[0];
  const info = await loadedModel.getModelInfo();
  const loadConfig = await loadedModel.getLoadConfig();
  const processingState = await loadedModel.getInstanceProcessingState();
  const snapshot = normalizeSnapshot(info, loadConfig, processingState);
  verifySnapshot(snapshot, environment);
  if (snapshot.context_length < TARGET_CONTEXT_TOKENS) {
    fail(`loaded context is smaller than the frozen ${TARGET_CONTEXT_TOKENS}-token contract`);
  }
  const visionProbe = await runVisionProbe(
    client, loadedModel, remainingDeadline("vision probe"),
  );
  const repeatRuns = [];
  for (let repeatIndex = 1; repeatIndex <= args.repeats; repeatIndex += 1) {
    const packetResults = [];
    const reportOutline = [];
    const packetRuns = [];
    const packetOrder = rotatedPackets(bundle.packets, repeatIndex);
    for (const packet of packetOrder) {
      const schema = packetResponseJsonSchema(bundle, packet);
      const chat = [
        {role: "system", content: "Ground every report claim in the provided bounded evidence."},
        {role: "user", content: bakeoffPrompt(bundle, packet)},
      ];
      const metrics = await packetPromptMetrics(loadedModel, chat, schema);
      if (metrics.conservative_input_tokens + args.maxTokens + RESERVED_CONTEXT_TOKENS
          > TARGET_CONTEXT_TOKENS) {
        fail(`repeat ${repeatIndex} packet ${packet.packet_id} exceeds the frozen 32K context budget`);
      }
      const prediction = await boundedStructuredResponse(
        loadedModel,
        chat,
        {
          deadlineMs: remainingDeadline(`repeat ${repeatIndex} packet ${packet.packet_id}`),
          maxTokens: args.maxTokens,
          reasoningBudget: args.reasoningBudget,
          schema,
        },
        `repeat ${repeatIndex} packet ${packet.packet_id} prediction`,
      );
      const packetResponse = validatePacketResponse(prediction.value, bundle, packet);
      packetResults.push(packetResponse.packet_result);
      reportOutline.push(...packetResponse.report_sections);
      packetRuns.push({
        packet_id: packet.packet_id,
        semantic_unit_count: packet.input_units.length,
        canonical_packet_bytes: packet.canonical_packet_bytes,
        canonical_packet_characters: packet.canonical_packet_characters,
        ...metrics,
        stop_reason: prediction.stopReason,
      });
    }
    const response = validateResponse({
      schema_version: 2,
      kind: "session_bakeoff_response",
      corpus_sha256: bundle.corpus_sha256,
      bundle_sha256: bundle.bundle_sha256,
      packet_results: packetResults,
      report_outline: reportOutline,
    }, bundle);
    repeatRuns.push({
      repeat_index: repeatIndex,
      packet_order: packetOrder.map(packet => packet.packet_id),
      packet_runs: packetRuns,
      response,
    });
  }
  return {visionProbe, repeatRuns};
}

function parseArgs(argv) {
  const values = {};
  const fields = new Map([
    ["--bundle", "bundle"], ["--binding", "binding"],
    ["--prepared-workdir", "preparedWorkdir"], ["--corroborating-log", "corroboratingLog"],
    ["--output", "output"], ["--deadline-ms", "deadlineMs"],
    ["--max-tokens", "maxTokens"], ["--reasoning-budget", "reasoningBudget"],
    ["--repeats", "repeats"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const field = fields.get(argv[index]);
    if (!field || index + 1 >= argv.length) fail(`unknown or incomplete option: ${argv[index]}`);
    values[field] = argv[++index];
  }
  for (const field of [
    "bundle", "binding", "preparedWorkdir", "corroboratingLog", "output", "deadlineMs",
    "maxTokens", "reasoningBudget", "repeats",
  ]) {
    if (values[field] === undefined) fail(`missing required option ${field}`);
  }
  values.deadlineMs = requireInteger(
    Number(values.deadlineMs), "deadline milliseconds", 1_000, MAX_CALLBACK_DEADLINE_MS,
  );
  values.maxTokens = requireInteger(Number(values.maxTokens), "max tokens", 1_024, MAX_OUTPUT_TOKENS);
  values.reasoningBudget = requireInteger(Number(values.reasoningBudget), "reasoning budget", 0, MAX_REASONING_TOKENS);
  values.repeats = requireInteger(Number(values.repeats), "repeat count", REQUIRED_REPEATS, REQUIRED_REPEATS);
  if (values.reasoningBudget > values.maxTokens) fail("reasoning budget cannot exceed max tokens");
  return values;
}

function rotatedPackets(packets, repeatIndex) {
  const offset = PACKET_ROTATION_OFFSETS[repeatIndex - 1];
  if (offset === undefined || packets.length !== 8) fail("repeat rotation contract changed");
  return [...packets.slice(offset), ...packets.slice(0, offset)];
}

async function main(argv = process.argv.slice(2)) {
  // Fail before parsing user-controlled paths unless the lifecycle supplied the
  // exact reviewed SDK entry and all three independently reviewed digests.
  const reviewedSdk = verifyReviewedSdkFromEnvironment();
  const args = parseArgs(argv);
  const environment = lifecycleEnvironment();
  const bundleInput = readRegularJson(args.bundle, "bake-off bundle");
  const bundle = validateBundle(bundleInput.value);
  const bindingInput = readRegularJson(args.binding, "lifecycle binding", 64 * 1024);
  validateBinding(bindingInput.value, environment);
  const pythonReceipt = runPythonPreflight(args, bundle);
  verifyPreparedAgainstBundle(args, bundle);
  const {client, packageIdentity} = createClient(reviewedSdk, environment.endpoint);
  let completedOutput;
  try {
    const {visionProbe, repeatRuns} = await runInferenceBatch(client, bundle, args, environment);
    const output = {
      schema_version: 2,
      kind: "session_bakeoff_callback_result",
      tool_version: TOOL_VERSION,
      corpus_sha256: bundle.corpus_sha256,
      bundle_sha256: bundle.bundle_sha256,
      ranking_status: "provisional_visual_evidence",
      evaluation_limitations: bundle.evaluation_limitations,
      input_hashes: {
        bundle_file_sha256: sha256Bytes(bundleInput.raw),
        binding_file_sha256: sha256Bytes(bindingInput.raw),
        sdk_entry_sha256: reviewedSdk.entrySha256,
        sdk_closure_sha256: reviewedSdk.closureSha256,
        sdk_dependency_closure_sha256: reviewedSdk.dependencyClosureSha256,
        python_preflight_receipt_sha256: pythonReceipt.receipt_sha256,
      },
      lifecycle_binding: {
        identifier: environment.identifier,
        model_key: environment.modelKey,
        selected_variant: environment.selectedVariant,
        profile: environment.profile,
        instance_reference: environment.instanceReference,
        indexed_model_identifier: environment.indexedModelIdentifier,
        context_length: environment.contextLength,
        snapshot_sha256: environment.snapshotSha256,
        load_config_sha256: environment.loadConfigSha256,
        process_token_sha256: environment.processTokenSha256,
        endpoint_sha256: sha256Bytes(Buffer.from(environment.endpoint, "utf8")),
      },
      sdk: packageIdentity,
      inference: {
        deadline_ms: args.deadlineMs,
        repeat_count: args.repeats,
        packet_call_count: args.repeats * bundle.packets.length,
        maximum_inference_call_count: 1 + args.repeats * bundle.packets.length,
        max_tokens: args.maxTokens,
        reasoning_budget: args.reasoningBudget,
        temperature: 0,
        seed_policy: "per_request_seed_unavailable_sdk_1_5_0",
        context_overflow_policy: "stopAtLimit",
        target_context_tokens: TARGET_CONTEXT_TOKENS,
        reserved_context_tokens: RESERVED_CONTEXT_TOKENS,
        conservative_input_token_limit: MAX_CONSERVATIVE_INPUT_TOKENS,
        vision_probe: visionProbe,
      },
      repeat_runs: repeatRuns,
    };
    completedOutput = output;
  } finally {
    await disposeClient(client);
  }
  if (completedOutput === undefined) fail("callback completed without a bounded result");
  completedOutput.inference.vision_probe.cleanup_boundary = "client_async_dispose_completed";
  completedOutput.result_sha256 = sha256Value(completedOutput);
  writeBoundedJson(args.output, completedOutput);
  process.stdout.write(`${JSON.stringify({
    ok: true, kind: completedOutput.kind, result_sha256: completedOutput.result_sha256,
  })}\n`);
}

if (require.main === module) {
  main().catch(error => {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`error: ${message}\n`);
    process.exitCode = 2;
  });
}

module.exports = {
  main, parseStrictJson, syntheticVisionPng, syntheticVisionSha256, syntheticVisionGold,
  packetResponseJsonSchema, bakeoffPrompt, rotatedPackets, assertSafe,
  validateBundle, verifyPreparedAgainstBundle, verifyReviewedSdkFromEnvironment,
  runInferenceBatch, normalizeSnapshot, sha256Value,
};
