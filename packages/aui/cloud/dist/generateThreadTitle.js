//#region src/generateThreadTitle.ts
async function generateThreadTitle(cloud, options) {
	const stream = await cloud.runs.stream({
		thread_id: options.threadId,
		assistant_id: "system/thread_title",
		messages: options.messages
	});
	let title = "";
	const reader = stream.getReader();
	try {
		while (true) {
			const { done, value: chunk } = await reader.read();
			if (done) break;
			if (chunk.type === "text-delta") title += chunk.textDelta;
		}
	} finally {
		reader.releaseLock();
	}
	title = title.trim();
	if (title) await cloud.threads.update(options.threadId, { title });
	return title || null;
}
//#endregion
export { generateThreadTitle };
