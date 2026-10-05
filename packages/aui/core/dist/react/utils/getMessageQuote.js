//#region src/react/utils/getMessageQuote.ts
const getMessageQuote = (state) => {
	const metadata = state.message.metadata;
	if (!metadata || typeof metadata !== "object") return void 0;
	return metadata.custom?.quote;
};
//#endregion
export { getMessageQuote };
