//#region src/CloudMessagePersistence.ts
const CLOUD_MESSAGE_PAGE_SIZE = 200;
/**
* Appends, updates and loads cloud messages while mapping local ids to cloud
* ids and chaining parent_id. A parent that is still being created is awaited,
* so concurrent appends land under the right parent.
*/
var CloudMessagePersistence = class {
	idMapping = /* @__PURE__ */ new Map();
	getCloud;
	constructor(cloud) {
		this.getCloud = typeof cloud === "function" ? cloud : () => cloud;
	}
	/**
	* Persist a message to the cloud.
	*
	* @param threadId - Remote thread ID
	* @param messageId - Local message ID (used for tracking)
	* @param parentId - Local parent message ID (or null for first message)
	* @param format - Message format (e.g., "aui/v0", "ai-sdk/v6")
	* @param content - Message content (format-specific)
	*/
	async append(threadId, messageId, parentId, format, content) {
		const cloud = this.getCloud();
		const existing = this.idMapping.get(messageId);
		if (existing instanceof Promise) {
			await existing;
			return;
		}
		const task = (async () => {
			const parentEntry = parentId ? this.idMapping.get(parentId) : void 0;
			const resolvedParentId = parentId ? await parentEntry ?? parentId : null;
			const { message_id } = await cloud.threads.messages.create(threadId, {
				parent_id: resolvedParentId,
				format,
				content
			});
			return message_id;
		})();
		this.idMapping.set(messageId, task);
		try {
			const remoteId = await task;
			if (this.idMapping.get(messageId) === task) this.idMapping.set(messageId, remoteId);
		} catch (err) {
			if (this.idMapping.get(messageId) === task) this.idMapping.delete(messageId);
			throw err;
		}
	}
	/**
	* Update an already-persisted message in the cloud.
	*/
	async update(threadId, messageId, _format, content) {
		const cloud = this.getCloud();
		const remoteId = await this.getRemoteId(messageId);
		if (!remoteId) {
			console.warn(`Skipping update for message ${messageId}: no remote id is mapped.`);
			return;
		}
		await cloud.threads.messages.update(threadId, remoteId, { content });
	}
	/**
	* Check if a message has been persisted (or is currently being persisted).
	*/
	isPersisted(messageId) {
		return this.idMapping.has(messageId);
	}
	/**
	* Get the remote ID for a local message ID (resolved).
	* Returns undefined if not persisted.
	*/
	async getRemoteId(messageId) {
		const entry = this.idMapping.get(messageId);
		if (!entry) return void 0;
		return entry;
	}
	getResolvedRemoteId(messageId) {
		const entry = this.idMapping.get(messageId);
		return typeof entry === "string" ? entry : void 0;
	}
	record(localId, remoteId) {
		this.idMapping.set(localId, remoteId);
	}
	/**
	* Load messages from the cloud and populate the ID mapping.
	*
	* The list endpoint caps a response at 200 rows, so pages are followed by
	* message ID cursor until a short page and concatenated in server order.
	*
	* The ID mapping is populated so that `isPersisted()` returns true for
	* loaded messages, preventing re-persistence of already-stored messages.
	*
	* A loaded ID that an append already maps keeps the remote ID from that append, and falls back to the loaded ID if the append fails.
	*
	* @param threadId - Remote thread ID
	* @param format - Optional format filter
	* @returns Array of cloud messages
	*/
	async load(threadId, format) {
		const idMapping = this.idMapping;
		const cloud = this.getCloud();
		const messages = [];
		const seen = /* @__PURE__ */ new Set();
		let after;
		while (true) {
			const page = await cloud.threads.messages.list(threadId, {
				...format ? { format } : void 0,
				limit: CLOUD_MESSAGE_PAGE_SIZE,
				...after ? { after } : void 0
			});
			const last = page.messages.at(-1);
			if (!last) break;
			const fresh = page.messages.filter((m) => !seen.has(m.id));
			if (fresh.length === 0) break;
			for (const m of fresh) seen.add(m.id);
			messages.push(...fresh);
			if (page.messages.length < CLOUD_MESSAGE_PAGE_SIZE) break;
			after = last.id;
		}
		if (this.idMapping === idMapping) for (const m of messages) {
			const entry = idMapping.get(m.id);
			if (entry === void 0) idMapping.set(m.id, m.id);
			else if (entry instanceof Promise) entry.catch(() => {
				const current = idMapping.get(m.id);
				if (current === void 0 || current === entry) idMapping.set(m.id, m.id);
			});
		}
		return messages;
	}
	/**
	* Reset the ID mapping (call when switching threads).
	*
	* Pending `load()` and `append()` calls are not cancelled and still settle
	* normally, but their results no longer populate the ID mapping.
	*/
	reset() {
		this.idMapping = /* @__PURE__ */ new Map();
	}
};
//#endregion
export { CloudMessagePersistence };
