import { generateId } from "../../core/utils/generateId.js";
import { ResumableStreamError, validateStreamId } from "../errors.js";
import "../constants.js";
//#region src/resumable/stores/redis-impl.ts
const DEFAULT_POLL_INTERVAL_MS = 100;
const DEFAULT_KEY_PREFIX = "aui:resumable";
const FIELD_CHUNK = "c";
const FIELD_FIN = "fin";
const FIELD_ERROR = "error";
const FIN_DONE = "done";
const FIN_ERROR = "error";
const STREAM_START_ID = "0-0";
const FINALIZE_IF_UNCHANGED_SCRIPT = `
redis.replicate_commands()
if redis.call("GET", KEYS[1]) ~= ARGV[1] then
  return 0
end
local xadd = { "XADD", KEYS[2], "*" }
for i = 4, #ARGV do
  table.insert(xadd, ARGV[i])
end
redis.call(unpack(xadd))
redis.call("EXPIRE", KEYS[2], ARGV[3])
redis.call("SET", KEYS[1], ARGV[2], "EX", ARGV[3])
return 1
`;
const FINALIZE_IF_UNCHANGED_KEY_COUNT = 2;
const APPEND_IF_UNCHANGED_SCRIPT = `
redis.replicate_commands()
if redis.call("GET", KEYS[1]) ~= ARGV[1] then
  return 0
end
local xadd = { "XADD", KEYS[2], "*" }
for i = 3, #ARGV do
  table.insert(xadd, ARGV[i])
end
redis.call(unpack(xadd))
redis.call("EXPIRE", KEYS[2], ARGV[2])
redis.call("EXPIRE", KEYS[1], ARGV[2])
return 1
`;
const APPEND_IF_UNCHANGED_KEY_COUNT = 2;
const DELETE_IF_UNCHANGED_SCRIPT = `
if redis.call("GET", KEYS[1]) ~= ARGV[1] then
  return 0
end
redis.call("DEL", unpack(KEYS))
return 1
`;
function finalizeIfUnchangedArgs(options) {
	return [
		options.metaKey,
		options.dataKey,
		options.expectedMeta,
		options.nextMeta,
		String(options.ttlSec),
		...Object.entries(options.fields).flat()
	];
}
function appendIfUnchangedArgs(options) {
	return [
		options.metaKey,
		options.dataKey,
		options.expectedMeta,
		String(options.ttlSec),
		...Object.entries(options.fields).flat()
	];
}
function deleteIfUnchangedArgs(options) {
	return [
		options.metaKey,
		...options.dataKeys,
		options.expectedMeta
	];
}
var RedisResumableStreamStore = class {
	client;
	keyPrefix;
	defaultTtlMs;
	pollIntervalMs;
	maxChunkBytes;
	constructor(client, options = {}) {
		this.client = client;
		this.keyPrefix = options.keyPrefix ?? DEFAULT_KEY_PREFIX;
		this.defaultTtlMs = options.defaultTtlMs ?? 864e5;
		this.pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
		this.maxChunkBytes = options.maxChunkBytes;
	}
	acquiredGenerations = /* @__PURE__ */ new Map();
	async acquire(streamId, options) {
		return (await this.acquireLease(streamId, options)).role;
	}
	async acquireLease(streamId, options) {
		validateStreamId(streamId);
		const ttlSec = msToSec(options?.ttlMs ?? this.defaultTtlMs);
		const generation = generateId();
		const meta = JSON.stringify({
			status: "streaming",
			ttlSec,
			generation
		});
		if (!await this.client.setNX(this.metaKey(streamId), meta, ttlSec)) return { role: "consumer" };
		this.acquiredGenerations.set(streamId, generation);
		return {
			role: "producer",
			lease: { token: generation }
		};
	}
	isSupersededGeneration(streamId, meta, lease) {
		if (lease) return meta.generation !== lease.token;
		const acquired = this.acquiredGenerations.get(streamId);
		return acquired !== void 0 && meta.generation !== acquired;
	}
	assertOwnedGeneration(streamId, meta, lease) {
		if (this.isSupersededGeneration(streamId, meta, lease)) throw new ResumableStreamError("missing", `Stream superseded by a new acquisition: ${streamId}`);
	}
	async append(streamId, chunk, lease) {
		validateStreamId(streamId);
		if (this.maxChunkBytes !== void 0 && chunk.byteLength > this.maxChunkBytes) throw new Error(`Chunk exceeds maxChunkBytes (${chunk.byteLength} > ${this.maxChunkBytes})`);
		const metaKey = this.metaKey(streamId);
		const existingRaw = await this.client.get(metaKey);
		if (existingRaw === null) throw new Error(`Stream not found: ${streamId}`);
		const meta = parseMeta(existingRaw);
		if (!meta) throw new Error(`Stream not found: ${streamId}`);
		this.assertOwnedGeneration(streamId, meta, lease);
		if (meta.status !== "streaming") throw new ResumableStreamError("finalized", `Stream already finalized: ${streamId}`);
		const ttlSec = meta.ttlSec ?? msToSec(this.defaultTtlMs);
		const dataKey = this.dataKey(streamId, meta.generation);
		if (!this.client.appendIfUnchanged) {
			await this.client.pipeline([
				{
					type: "xAdd",
					key: dataKey,
					fields: { [FIELD_CHUNK]: chunk }
				},
				{
					type: "expire",
					key: dataKey,
					ttlSec
				},
				{
					type: "expire",
					key: metaKey,
					ttlSec
				}
			]);
			return;
		}
		if (await this.client.appendIfUnchanged({
			metaKey,
			expectedMeta: existingRaw,
			dataKey,
			fields: { [FIELD_CHUNK]: chunk },
			ttlSec
		})) return;
		const current = await this.readMeta(streamId);
		if (!current) throw new Error(`Stream not found: ${streamId}`);
		this.assertOwnedGeneration(streamId, current, lease);
		if (current.status !== "streaming") throw new ResumableStreamError("finalized", `Stream already finalized: ${streamId}`);
		throw new ResumableStreamError("missing", `Stream changed while appending: ${streamId}`);
	}
	async finalize(streamId, status, error, lease) {
		validateStreamId(streamId);
		const metaKey = this.metaKey(streamId);
		const existingRaw = await this.client.get(metaKey);
		if (existingRaw === null) throw new Error(`Stream not found: ${streamId}`);
		const existing = parseMeta(existingRaw);
		if (!existing) throw new Error(`Stream not found: ${streamId}`);
		if (existing.status !== "streaming") return false;
		if (this.isSupersededGeneration(streamId, existing, lease)) return false;
		const ttlSec = existing.ttlSec ?? msToSec(this.defaultTtlMs);
		const meta = JSON.stringify({
			status,
			...status === "error" && { error: error ?? "Stream errored" },
			ttlSec,
			...existing.generation !== void 0 && { generation: existing.generation }
		});
		const fields = { [FIELD_FIN]: status === "error" ? FIN_ERROR : FIN_DONE };
		if (status === "error") fields[FIELD_ERROR] = error ?? "Stream errored";
		const dataKey = this.dataKey(streamId, existing.generation);
		if (!await this.client.finalizeIfUnchanged({
			metaKey,
			expectedMeta: existingRaw,
			nextMeta: meta,
			dataKey,
			fields,
			ttlSec
		})) return false;
		this.clearAcquiredGeneration(streamId, existing.generation);
		return true;
	}
	async *read(streamId, cursor, signal) {
		validateStreamId(streamId);
		const metaKey = this.metaKey(streamId);
		const initialMeta = await this.client.get(metaKey);
		if (initialMeta === null) throw new Error(`Stream not found: ${streamId}`);
		const generation = parseMeta(initialMeta)?.generation;
		const dataKey = this.dataKey(streamId, generation);
		let lastId = cursor === "" ? STREAM_START_ID : cursor;
		while (true) {
			if (signal.aborted) return;
			const start = lastId === STREAM_START_ID ? "-" : `(${lastId}`;
			const entries = await this.client.xRange(dataKey, start, "+");
			for (const entry of entries) {
				if (signal.aborted) return;
				lastId = entry.id;
				const fin = readString(entry.fields[FIELD_FIN]);
				if (fin === FIN_DONE) return;
				if (fin === FIN_ERROR) throw new Error(readString(entry.fields[FIELD_ERROR]) ?? "Stream errored");
				const raw = entry.fields[FIELD_CHUNK];
				if (raw === void 0) continue;
				yield {
					cursor: entry.id,
					chunk: toBytes(raw)
				};
			}
			if (entries.length > 0) continue;
			const currentMeta = await this.client.get(metaKey);
			if (currentMeta === null) return;
			if (parseMeta(currentMeta)?.generation !== generation) return;
			await sleep(this.pollIntervalMs, signal);
		}
	}
	async status(streamId) {
		validateStreamId(streamId);
		const meta = await this.client.get(this.metaKey(streamId));
		if (meta === null) return "missing";
		const parsed = parseMeta(meta);
		if (parsed?.status === "streaming") return "streaming";
		if (parsed?.status === "done") return "done";
		if (parsed?.status === "error") return "error";
		return "missing";
	}
	async delete(streamId) {
		validateStreamId(streamId);
		const metaKey = this.metaKey(streamId);
		const acquiredGeneration = this.acquiredGenerations.get(streamId);
		let existingRaw = await this.client.get(metaKey);
		const legacyDataKey = this.dataKey(streamId);
		if (existingRaw === null) {
			this.clearAcquiredGeneration(streamId, acquiredGeneration);
			await this.client.del([...acquiredGeneration === void 0 ? [] : [this.dataKey(streamId, acquiredGeneration)], legacyDataKey]);
			return;
		}
		const generation = parseMeta(existingRaw)?.generation;
		if (!this.client.deleteIfUnchanged) {
			this.clearAcquiredGeneration(streamId, acquiredGeneration);
			await this.client.del([metaKey, .../* @__PURE__ */ new Set([this.dataKey(streamId, generation), legacyDataKey])]);
			return;
		}
		while (true) {
			if (await this.client.deleteIfUnchanged({
				metaKey,
				expectedMeta: existingRaw,
				dataKeys: [.../* @__PURE__ */ new Set([this.dataKey(streamId, generation), legacyDataKey])]
			})) {
				this.clearAcquiredGeneration(streamId, acquiredGeneration);
				return;
			}
			const currentRaw = await this.client.get(metaKey);
			if (currentRaw === null || parseMeta(currentRaw)?.generation !== generation) {
				this.clearAcquiredGeneration(streamId, acquiredGeneration);
				if (generation !== void 0) await this.client.del([this.dataKey(streamId, generation)]);
				return;
			}
			existingRaw = currentRaw;
		}
	}
	clearAcquiredGeneration(streamId, generation) {
		if (this.acquiredGenerations.get(streamId) === generation) this.acquiredGenerations.delete(streamId);
	}
	async readMeta(streamId) {
		const raw = await this.client.get(this.metaKey(streamId));
		if (raw === null) return void 0;
		return parseMeta(raw);
	}
	metaKey(streamId) {
		return `${this.keyPrefix}:{${streamId}}:meta`;
	}
	dataKey(streamId, generation) {
		const base = `${this.keyPrefix}:{${streamId}}:data`;
		return generation ? `${base}:${generation}` : base;
	}
};
function parseMeta(value) {
	try {
		const parsed = JSON.parse(value);
		return parsed && typeof parsed === "object" ? parsed : void 0;
	} catch {
		return;
	}
}
function msToSec(ms) {
	return Math.max(1, Math.ceil(ms / 1e3));
}
function sleep(ms, signal) {
	return new Promise((resolve) => {
		if (signal.aborted) {
			resolve();
			return;
		}
		const timer = setTimeout(() => {
			signal.removeEventListener("abort", onAbort);
			resolve();
		}, ms);
		const onAbort = () => {
			clearTimeout(timer);
			resolve();
		};
		signal.addEventListener("abort", onAbort, { once: true });
	});
}
const SHARED_DECODER = new TextDecoder();
const SHARED_ENCODER = new TextEncoder();
function readString(value) {
	if (value === void 0) return void 0;
	if (typeof value === "string") return value;
	return SHARED_DECODER.decode(value);
}
function toBytes(value) {
	if (value instanceof Uint8Array) return value;
	return SHARED_ENCODER.encode(value);
}
//#endregion
export { APPEND_IF_UNCHANGED_KEY_COUNT, APPEND_IF_UNCHANGED_SCRIPT, DELETE_IF_UNCHANGED_SCRIPT, FINALIZE_IF_UNCHANGED_KEY_COUNT, FINALIZE_IF_UNCHANGED_SCRIPT, RedisResumableStreamStore, appendIfUnchangedArgs, deleteIfUnchangedArgs, finalizeIfUnchangedArgs };
