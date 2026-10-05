//#region src/react/adapters/TitleGenerationAdapter.ts
const createSimpleTitleAdapter = () => {
	return { async generateTitle(messages) {
		const firstUserMessage = messages.find((m) => m.role === "user");
		if (!firstUserMessage) return "New Thread";
		const textPart = firstUserMessage.content.find((p) => p.type === "text");
		if (!textPart || textPart.type !== "text") return "New Thread";
		const text = textPart.text.trim();
		return text.length > 50 ? `${text.slice(0, 47)}...` : text;
	} };
};
//#endregion
export { createSimpleTitleAdapter };
