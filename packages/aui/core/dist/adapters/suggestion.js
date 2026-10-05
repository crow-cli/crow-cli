import { getThreadMessageText } from "../utils/text.js";
//#region src/adapters/suggestion.ts
const consumeSuggestionResult = async (result, options) => {
	const { signal, onUpdate } = options;
	if (Symbol.asyncIterator in result) for await (const r of result) {
		if (signal.aborted) break;
		onUpdate(r);
	}
	else {
		const suggestions = await result;
		if (signal.aborted) return;
		onUpdate(suggestions);
	}
};
const createSuggestionAdapter = (options) => {
	const count = options.count ?? 3;
	const maxMessages = options.maxMessages ?? 10;
	return { async generate({ messages, signal }) {
		const limit = Math.max(0, Math.floor(maxMessages));
		const transcript = (limit === 0 ? [] : messages.slice(-limit)).map((message) => {
			const text = getThreadMessageText(message).trim();
			if (!text) return null;
			return `${message.role}: ${text}`;
		}).filter((line) => line != null).join("\n");
		let prompt = `Based on the following conversation, suggest exactly ${count} short follow-up prompts that the USER would plausibly send next. Write each prompt in the user's voice as something they would type. Return only the prompts, one per line, with no numbering or extra commentary.\n\nConversation:\n${transcript}`;
		if (options.instructions) prompt += `\n\nAdditional instructions:\n${options.instructions}`;
		return (await options.complete({
			prompt,
			...signal !== void 0 && { signal }
		})).map((s) => s.trim()).filter((s) => s.length > 0).slice(0, count).map((text) => ({ prompt: text }));
	} };
};
//#endregion
export { consumeSuggestionResult, createSuggestionAdapter };
