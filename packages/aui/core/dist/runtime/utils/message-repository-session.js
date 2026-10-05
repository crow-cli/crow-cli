import { MessageRepository } from "./message-repository.js";
//#region src/runtime/utils/message-repository-session.ts
const createMessageRepositorySession = (options = {}) => {
	const repository = new MessageRepository();
	let exportedRepository;
	const getMessages = () => {
		return repository.getMessages();
	};
	const tryGetMessage = (messageId) => {
		try {
			return repository.getMessage(messageId);
		} catch {
			return;
		}
	};
	const tryGetMessages = (messageId) => {
		try {
			return repository.getMessages(messageId);
		} catch {
			return;
		}
	};
	const hasMessage = (messageId) => {
		return tryGetMessage(messageId) !== void 0;
	};
	const addOrUpdateMessage = (parentId, message) => {
		repository.addOrUpdateMessage(parentId, message);
		exportedRepository = void 0;
	};
	const deleteMessage = (messageId, replacementId) => {
		repository.deleteMessage(messageId, replacementId);
		exportedRepository = void 0;
	};
	const tryDeleteMessage = (messageId) => {
		if (!hasMessage(messageId)) return false;
		deleteMessage(messageId);
		return true;
	};
	const switchToBranch = (messageId) => {
		repository.switchToBranch(messageId);
		exportedRepository = void 0;
	};
	const resetHead = (messageId) => {
		repository.resetHead(messageId);
		exportedRepository = void 0;
	};
	const clear = () => {
		repository.clear();
		exportedRepository = void 0;
	};
	const updateMessage = (messageId, updater) => {
		const item = tryGetMessage(messageId);
		if (!item) return false;
		const message = updater(item.message);
		if (message === item.message) return false;
		addOrUpdateMessage(item.parentId, message);
		return true;
	};
	const applyExternalMessageRepository = (loaded) => {
		const headId = loaded.headId ?? loaded.messages.at(-1)?.message.id ?? null;
		const ids = /* @__PURE__ */ new Set();
		let degenerate = false;
		for (const { message } of loaded.messages) {
			if (ids.has(message.id)) {
				degenerate = true;
				break;
			}
			ids.add(message.id);
		}
		if (headId !== null && !ids.has(headId)) degenerate = true;
		if (!degenerate) {
			clear();
			let pending = [...loaded.messages];
			const importedIds = /* @__PURE__ */ new Set();
			while (pending.length > 0) {
				const unresolved = [];
				let progressed = false;
				for (const item of pending) {
					if (item.parentId !== null && !importedIds.has(item.parentId)) {
						unresolved.push(item);
						continue;
					}
					addOrUpdateMessage(item.parentId, item.message);
					importedIds.add(item.message.id);
					progressed = true;
				}
				if (!progressed) {
					degenerate = true;
					break;
				}
				pending = unresolved;
			}
		}
		if (degenerate) {
			clear();
			let previousId = null;
			for (const { message } of loaded.messages) {
				const existing = tryGetMessage(message.id);
				addOrUpdateMessage(existing ? existing.parentId : previousId, message);
				previousId = message.id;
			}
			resetHead(previousId);
		} else resetHead(headId);
	};
	return {
		getMessages,
		get headId() {
			return repository.headId;
		},
		export: () => {
			exportedRepository ??= options.decorateExport ? options.decorateExport(repository.export(), repository) : repository.export();
			return exportedRepository;
		},
		tryGetMessage,
		tryGetMessages,
		hasMessage,
		addOrUpdateMessage,
		deleteMessage,
		tryDeleteMessage,
		switchToBranch,
		resetHead,
		clear,
		updateMessage,
		applyExternalMessageRepository
	};
};
//#endregion
export { createMessageRepositorySession };
