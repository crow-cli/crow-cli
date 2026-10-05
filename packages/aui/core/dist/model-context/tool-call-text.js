//#region src/model-context/tool-call-text.ts
const resolveToolCallText = (text, part) => {
	if (!(part.status?.type === "running" || part.status?.type === "requires-action")) {
		const value = text.complete;
		if (typeof value !== "function") return value ?? null;
		return value({
			args: part.args,
			result: part.result
		});
	}
	const value = text.running;
	if (typeof value !== "function") return value ?? null;
	return value({ args: part.args });
};
//#endregion
export { resolveToolCallText };
