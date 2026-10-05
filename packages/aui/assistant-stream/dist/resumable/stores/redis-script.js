import { createHash } from "node:crypto";
//#region src/resumable/stores/redis-script.ts
function redisScriptSha(script) {
	return createHash("sha1").update(script).digest("hex");
}
async function runCachedRedisScript(runSha, runSource) {
	try {
		return await runSha();
	} catch (error) {
		if (!(error instanceof Error) || !error.message.includes("NOSCRIPT")) throw error;
		return runSource();
	}
}
//#endregion
export { redisScriptSha, runCachedRedisScript };
