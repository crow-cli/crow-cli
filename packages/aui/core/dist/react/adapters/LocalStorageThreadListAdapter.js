import { isRecord } from "../../utils/json/is-json.js";
import { isStoredMessagePart, isStoredMessageRole, isStoredMessageStatus, parseStoredAttachment, parseStoredDate, parseStoredThreadSteps } from "../../runtime/utils/stored-message-parts.js";
import { RuntimeAdapterProvider } from "../runtimes/RuntimeAdapterProvider.js";
import { createAssistantStream } from "assistant-stream";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useMemo, useRef, useState } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
//#region src/react/adapters/LocalStorageThreadListAdapter.tsx
var KeyedMutationQueue = class {
	tails = /* @__PURE__ */ new Map();
	staleKeys = /* @__PURE__ */ new Set();
	markStale(key) {
		this.staleKeys.add(key);
	}
	async removeStale(key, storage) {
		if (!this.staleKeys.has(key)) return;
		await storage.removeItem(key);
		this.staleKeys.delete(key);
	}
	run(key, mutation) {
		const previous = this.tails.get(key);
		const result = previous ? previous.then(mutation) : mutation();
		const tail = result.then(() => void 0, () => void 0);
		this.tails.set(key, tail);
		tail.then(() => {
			if (this.tails.get(key) === tail) this.tails.delete(key);
		});
		return result;
	}
};
const mutationQueues = /* @__PURE__ */ new WeakMap();
const getMutationQueue = (storage) => {
	let queue = mutationQueues.get(storage);
	if (!queue) {
		queue = new KeyedMutationQueue();
		mutationQueues.set(storage, queue);
	}
	return queue;
};
const parseJSON = (raw) => {
	if (!raw) return void 0;
	try {
		return JSON.parse(raw);
	} catch {
		return;
	}
};
const parseStoredThread = (value) => {
	if (!isRecord(value) || typeof value.remoteId !== "string") return null;
	const status = value.status ?? "regular";
	if (status !== "regular" && status !== "archived") return null;
	return {
		remoteId: value.remoteId,
		status,
		...typeof value.externalId === "string" ? { externalId: value.externalId } : void 0,
		...typeof value.title === "string" ? { title: value.title } : void 0,
		...isRecord(value.custom) ? { custom: value.custom } : void 0
	};
};
const messageModalities = { voice: true };
const isMessageModality = (value) => typeof value === "string" && Object.hasOwn(messageModalities, value);
const parseStoredMessageParts = (content, depth) => content.flatMap((part) => {
	if (!isStoredMessagePart(part)) return [];
	if (part.type !== "tool-call" || part.messages === void 0) return [part];
	const { messages, ...toolCall } = part;
	if (!Array.isArray(messages)) return [toolCall];
	return [{
		...toolCall,
		messages: messages.flatMap((item) => {
			const message = parseStoredThreadMessage(item, depth + 1);
			return message ? [message] : [];
		})
	}];
});
const parseStoredThreadMessage = (value, depth) => {
	if (depth > 100) return null;
	if (!isRecord(value) || typeof value.id !== "string") return null;
	if (!isStoredMessageRole(value.role)) return null;
	if (!Array.isArray(value.content)) return null;
	const createdAt = parseStoredDate(value.createdAt);
	if (!createdAt) return null;
	const metadata = value.metadata;
	if (!isRecord(metadata) || !isRecord(metadata.custom)) return null;
	const modality = isMessageModality(metadata.modality) ? metadata.modality : void 0;
	if (value.role === "assistant") {
		const status = isStoredMessageStatus(value.status) ? value.status : {
			type: "complete",
			reason: "unknown"
		};
		const submittedFeedback = isRecord(metadata.submittedFeedback) ? metadata.submittedFeedback : void 0;
		const submittedFeedbackType = submittedFeedback?.type;
		const submittedFeedbackComment = submittedFeedback?.comment;
		return {
			id: value.id,
			role: "assistant",
			content: parseStoredMessageParts(value.content, depth),
			status,
			createdAt,
			metadata: {
				unstable_state: metadata.unstable_state ?? null,
				unstable_annotations: Array.isArray(metadata.unstable_annotations) ? metadata.unstable_annotations : [],
				unstable_data: Array.isArray(metadata.unstable_data) ? metadata.unstable_data : [],
				steps: parseStoredThreadSteps(metadata.steps),
				...submittedFeedbackType === "positive" || submittedFeedbackType === "negative" ? { submittedFeedback: {
					type: submittedFeedbackType,
					...typeof submittedFeedbackComment === "string" && submittedFeedbackComment !== "" ? { comment: submittedFeedbackComment } : void 0
				} } : void 0,
				...metadata.timing !== void 0 ? { timing: metadata.timing } : void 0,
				...metadata.isOptimistic === true ? { isOptimistic: true } : void 0,
				...modality !== void 0 ? { modality } : void 0,
				custom: metadata.custom
			}
		};
	}
	if (value.role === "user") return {
		id: value.id,
		role: "user",
		content: parseStoredMessageParts(value.content, depth),
		attachments: Array.isArray(value.attachments) ? value.attachments.flatMap((item) => {
			const attachment = parseStoredAttachment(item, isStoredMessagePart);
			return attachment ? [attachment] : [];
		}) : [],
		createdAt,
		metadata: {
			...modality !== void 0 ? { modality } : void 0,
			custom: metadata.custom
		}
	};
	const content = parseStoredMessageParts(value.content, depth);
	if (content.length !== 1) return null;
	return {
		id: value.id,
		role: "system",
		content: [content[0]],
		createdAt,
		metadata: { custom: metadata.custom }
	};
};
const parseStoredThreadMetadata = (raw) => {
	const parsed = parseJSON(raw);
	if (!Array.isArray(parsed)) return [];
	return parsed.flatMap((item) => {
		const thread = parseStoredThread(item);
		return thread ? [thread] : [];
	});
};
const parseStoredMessageRepositoryItem = (value) => {
	if (!isRecord(value)) return null;
	const message = parseStoredThreadMessage(value.message, 0);
	if (!message) return null;
	const parentId = value.parentId;
	if (parentId !== void 0 && parentId !== null && typeof parentId !== "string") return null;
	return {
		message,
		parentId: parentId ?? null,
		...isRecord(value.runConfig) ? { runConfig: value.runConfig } : void 0
	};
};
const parseStoredMessageRepository = (raw) => {
	const parsed = parseJSON(raw);
	if (!isRecord(parsed) || !Array.isArray(parsed.messages)) return { messages: [] };
	const candidateMessages = parsed.messages.flatMap((item) => {
		const parsedItem = parseStoredMessageRepositoryItem(item);
		return parsedItem ? [parsedItem] : [];
	});
	const acceptedIds = /* @__PURE__ */ new Set();
	const messages = candidateMessages.flatMap((item) => {
		if (acceptedIds.has(item.message.id)) return [];
		if (item.parentId !== null && !acceptedIds.has(item.parentId)) return [];
		acceptedIds.add(item.message.id);
		return [item];
	});
	const headId = parsed.headId === null || typeof parsed.headId === "string" && messages.some((item) => item.message.id === parsed.headId) ? parsed.headId : void 0;
	return {
		...headId !== void 0 ? { headId } : void 0,
		messages
	};
};
var AsyncStorageHistoryAdapter = class {
	storage;
	getAui;
	prefix;
	mutationQueue;
	constructor(storage, getAui, prefix, mutationQueue) {
		this.storage = storage;
		this.getAui = getAui;
		this.prefix = prefix;
		this.mutationQueue = mutationQueue;
	}
	get aui() {
		return this.getAui();
	}
	_messagesKey(remoteId) {
		return `${this.prefix}messages:${remoteId}`;
	}
	_threadsKey() {
		return `${this.prefix}threads`;
	}
	async load() {
		const remoteId = this.aui.threadListItem.getState().remoteId;
		if (!remoteId) return { messages: [] };
		const raw = await this.storage.getItem(this._messagesKey(remoteId));
		return parseStoredMessageRepository(raw);
	}
	async _upsert(item, moveHead) {
		const { remoteId } = await this.aui.threadListItem.initialize();
		const key = this._messagesKey(remoteId);
		await this.mutationQueue.run(key, async () => {
			if (await this.mutationQueue.run(this._threadsKey(), async () => {
				const raw = await this.storage.getItem(this._threadsKey());
				const parsed = parseJSON(raw);
				return Array.isArray(parsed) && !parsed.some((thread) => parseStoredThread(thread)?.remoteId === remoteId);
			})) return;
			const raw = await this.storage.getItem(key);
			const repo = parseStoredMessageRepository(raw);
			const idx = repo.messages.findIndex((m) => m.message.id === item.message.id);
			if (idx >= 0) repo.messages[idx] = item;
			else repo.messages.push(item);
			if (moveHead) repo.headId = item.message.id;
			await this.storage.setItem(key, JSON.stringify(repo));
		});
	}
	async append(item) {
		await this._upsert(item, true);
	}
	async update(item) {
		await this._upsert(item, false);
	}
};
const createLocalStorageHistoryAdapter = (storage, getAui, prefix, mutationQueue = getMutationQueue(storage)) => new AsyncStorageHistoryAdapter(storage, getAui, prefix, mutationQueue);
const useLocalStorageThreadAdapters = (storage, prefix, mutationQueue) => {
	const aui = useAui();
	const auiRef = useRef(aui);
	useEffect(() => {
		auiRef.current = aui;
	});
	const [history] = useState(() => createLocalStorageHistoryAdapter(storage, () => auiRef.current, prefix, mutationQueue));
	return useMemo(() => ({ history }), [history]);
};
const createHistoryProvider = (storage, prefix, mutationQueue) => {
	const Provider = (t0) => {
		const $ = c(3);
		const { children } = t0;
		const adapters = useLocalStorageThreadAdapters(storage, prefix, mutationQueue);
		let t1;
		if ($[0] !== adapters || $[1] !== children) {
			t1 = /* @__PURE__ */ jsx(RuntimeAdapterProvider, {
				adapters,
				children
			});
			$[0] = adapters;
			$[1] = children;
			$[2] = t1;
		} else t1 = $[2];
		return t1;
	};
	return Provider;
};
const createLocalStorageAdapter = (options) => {
	const { storage, prefix = "@assistant-ui:", titleGenerator } = options;
	const threadsKey = `${prefix}threads`;
	const messagesKey = (threadId) => `${prefix}messages:${threadId}`;
	const mutationQueue = getMutationQueue(storage);
	const loadThreadMetadata = async () => {
		const raw = await storage.getItem(threadsKey);
		return parseStoredThreadMetadata(raw);
	};
	const saveThreadMetadata = async (threads) => {
		await storage.setItem(threadsKey, JSON.stringify(threads));
	};
	const updateThreadMetadata = async (remoteId, update) => {
		await mutationQueue.run(threadsKey, async () => {
			const threads = await loadThreadMetadata();
			const thread = threads.find((item) => item.remoteId === remoteId);
			if (thread) {
				update(thread);
				await saveThreadMetadata(threads);
			}
		});
	};
	return {
		unstable_Provider: createHistoryProvider(storage, prefix, mutationQueue),
		unstable_useAdapters: function useLocalStorageAdapters() {
			return useLocalStorageThreadAdapters(storage, prefix, mutationQueue);
		},
		async list() {
			return { threads: (await loadThreadMetadata()).map((t) => ({
				remoteId: t.remoteId,
				externalId: t.externalId,
				status: t.status,
				title: t.title,
				custom: t.custom
			})) };
		},
		async initialize(threadId) {
			const remoteId = threadId;
			const key = messagesKey(remoteId);
			return mutationQueue.run(key, async () => {
				await mutationQueue.removeStale(key, storage);
				return mutationQueue.run(threadsKey, async () => {
					const threads = await loadThreadMetadata();
					if (!threads.some((t) => t.remoteId === remoteId)) {
						threads.unshift({
							remoteId,
							status: "regular"
						});
						await saveThreadMetadata(threads);
					}
					return {
						remoteId,
						externalId: void 0
					};
				});
			});
		},
		async rename(remoteId, newTitle) {
			await updateThreadMetadata(remoteId, (thread) => {
				thread.title = newTitle;
			});
		},
		async updateCustom(remoteId, custom) {
			await updateThreadMetadata(remoteId, (thread) => {
				thread.custom = custom;
			});
		},
		async archive(remoteId) {
			await updateThreadMetadata(remoteId, (thread) => {
				thread.status = "archived";
			});
		},
		async unarchive(remoteId) {
			await updateThreadMetadata(remoteId, (thread) => {
				thread.status = "regular";
			});
		},
		async delete(remoteId) {
			const key = messagesKey(remoteId);
			await mutationQueue.run(key, async () => {
				await mutationQueue.run(threadsKey, async () => {
					const filtered = (await loadThreadMetadata()).filter((t) => t.remoteId !== remoteId);
					await saveThreadMetadata(filtered);
				});
				mutationQueue.markStale(key);
				await mutationQueue.removeStale(key, storage);
			});
		},
		async fetch(threadId) {
			const thread = (await loadThreadMetadata()).find((t) => t.remoteId === threadId);
			if (!thread) throw new Error(`Stored thread "${threadId}" not found while fetching thread metadata.`);
			return {
				remoteId: thread.remoteId,
				externalId: thread.externalId,
				status: thread.status,
				title: thread.title,
				custom: thread.custom
			};
		},
		async generateTitle(remoteId, messages) {
			if (titleGenerator) {
				const title = await titleGenerator.generateTitle(messages);
				await updateThreadMetadata(remoteId, (thread) => {
					thread.title = title;
				});
				return createAssistantStream((controller) => {
					controller.appendText(title);
				});
			}
			return createAssistantStream(() => {});
		}
	};
};
//#endregion
export { createLocalStorageAdapter, createLocalStorageHistoryAdapter, parseStoredMessageRepository, parseStoredThreadMetadata };
