//#region src/utils/text.ts
const getThreadMessageText = (message) => {
	return message.content.filter((part) => part.type === "text").map((part) => part.text).join("\n\n");
};
//#endregion
export { getThreadMessageText };
