import { APPEND_IF_UNCHANGED_SCRIPT, DELETE_IF_UNCHANGED_SCRIPT, FINALIZE_IF_UNCHANGED_SCRIPT, RedisResumableStreamStore, appendIfUnchangedArgs, deleteIfUnchangedArgs, finalizeIfUnchangedArgs } from "./redis-impl.js";
import { redisScriptSha, runCachedRedisScript } from "./redis-script.js";
//#region src/resumable/stores/ioredis.ts
const APPEND_IF_UNCHANGED_SHA = redisScriptSha(APPEND_IF_UNCHANGED_SCRIPT);
const FINALIZE_IF_UNCHANGED_SHA = redisScriptSha(FINALIZE_IF_UNCHANGED_SCRIPT);
const DELETE_IF_UNCHANGED_SHA = redisScriptSha(DELETE_IF_UNCHANGED_SCRIPT);
/**
* Resumable stream store backed by [`ioredis`](https://www.npmjs.com/package/ioredis)
* v5 or v6. Accepts a `Redis` or `Cluster` instance.
*/
function createIoredisResumableStreamStore(client, options) {
	return new RedisResumableStreamStore(adapt(client), options);
}
function adapt(client) {
	return {
		async setNX(key, value, ttlSec) {
			return await client.set(key, value, "EX", ttlSec, "NX") === "OK";
		},
		async get(key) {
			return client.get(key);
		},
		async del(keys) {
			if (keys.length === 0) return;
			await client.del(...keys);
		},
		async xRange(key, start, end) {
			return (await client.xrangeBuffer(key, start, end)).map(([idBuf, fieldArray]) => ({
				id: idBuf.toString("utf8"),
				fields: bufferFieldsToRecord(fieldArray)
			}));
		},
		async pipeline(commands) {
			if (commands.length === 0) return;
			const pipe = client.pipeline();
			for (const cmd of commands) applyPipelineCommand(pipe, cmd);
			const results = await pipe.exec() ?? [];
			for (const [err] of results) if (err) throw err;
		},
		async appendIfUnchanged(options) {
			return await runScript(client, APPEND_IF_UNCHANGED_SHA, APPEND_IF_UNCHANGED_SCRIPT, 2, appendIfUnchangedArgs(options).map((arg) => typeof arg === "string" ? arg : toBuffer(arg))) === 1;
		},
		async finalizeIfUnchanged(options) {
			return await runScript(client, FINALIZE_IF_UNCHANGED_SHA, FINALIZE_IF_UNCHANGED_SCRIPT, 2, finalizeIfUnchangedArgs(options)) === 1;
		},
		async deleteIfUnchanged(options) {
			return await runScript(client, DELETE_IF_UNCHANGED_SHA, DELETE_IF_UNCHANGED_SCRIPT, options.dataKeys.length + 1, deleteIfUnchangedArgs(options)) === 1;
		}
	};
}
async function runScript(client, sha, script, keyCount, args) {
	return runCachedRedisScript(() => client.evalsha(sha, keyCount, ...args), () => client.eval(script, keyCount, ...args));
}
function applyPipelineCommand(pipe, cmd) {
	switch (cmd.type) {
		case "xAdd":
			pipe.xadd(cmd.key, "*", ...toFieldArgs(cmd.fields));
			return;
		case "expire":
			pipe.expire(cmd.key, cmd.ttlSec);
			return;
	}
}
function toFieldArgs(fields) {
	const args = [];
	for (const [k, v] of Object.entries(fields)) args.push(k, typeof v === "string" ? v : toBuffer(v));
	return args;
}
function toBuffer(bytes) {
	if (Buffer.isBuffer(bytes)) return bytes;
	return Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}
function bufferFieldsToRecord(fields) {
	const out = {};
	for (let i = 0; i + 1 < fields.length; i += 2) {
		const key = fields[i]?.toString("utf8");
		const value = fields[i + 1];
		if (key !== void 0 && value !== void 0) out[key] = new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
	}
	return out;
}
//#endregion
export { createIoredisResumableStreamStore };
