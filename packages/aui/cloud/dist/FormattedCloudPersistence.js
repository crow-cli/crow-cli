//#region src/FormattedCloudPersistence.ts
/**
* Wraps a CloudMessagePersistence with a MessageFormatAdapter's encode and
* decode. The persistence parameter is typed structurally, so a caller does
* not need to import the class.
*/
const createFormattedPersistence = (persistence, adapter) => ({
	append: async (threadId, item) => {
		const messageId = adapter.getId(item.message);
		const encoded = adapter.encode(item);
		return persistence.append(threadId, messageId, item.parentId, adapter.format, encoded);
	},
	update: persistence.update ? async (threadId, item, messageId) => {
		const encoded = adapter.encode(item);
		return persistence.update(threadId, messageId, adapter.format, encoded);
	} : void 0,
	load: async (threadId) => {
		return { messages: (await persistence.load(threadId, adapter.format)).filter((m) => m.format === adapter.format).map((m) => adapter.decode({
			id: m.id,
			parent_id: m.parent_id,
			format: m.format,
			content: m.content
		})).reverse() };
	},
	isPersisted: (messageId) => persistence.isPersisted(messageId)
});
//#endregion
export { createFormattedPersistence };
