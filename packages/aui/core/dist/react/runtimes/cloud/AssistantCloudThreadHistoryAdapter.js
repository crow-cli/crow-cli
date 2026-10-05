import { isJSONValueEqual } from "../../../utils/json/is-json-equal.js";
import { runCleanups } from "../../../subscribable/subscribable.js";
import { appendToolInteraction, readToolInteractionLog } from "../../../runtime/utils/tool-interactions.js";
import { isStoredMessageStatus, parseStoredThreadSteps } from "../../../runtime/utils/stored-message-parts.js";
import { auiV0DecodeSafely, auiV0Encode } from "./auiV0.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
import { getClientId, useAui } from "@assistant-ui/store";
import { CloudAPIError, CloudEngagementReporter, CloudMessagePersistence, CloudRunReporter, createFormattedPersistence, createRunTelemetryToolCall, deriveRunOutcome, describeRunError, extractRunTelemetryModelId, normalizeRunTelemetryUsage, truncateRunTelemetryText } from "assistant-cloud";
import { extractAISDKRunTelemetry } from "assistant-cloud/ai-sdk";
//#region src/react/runtimes/cloud/AssistantCloudThreadHistoryAdapter.ts
const globalPersistence = /* @__PURE__ */ new WeakMap();
const runLedgers = /* @__PURE__ */ new WeakMap();
const runLedgerOf = (persistence) => {
	let ledger = runLedgers.get(persistence);
	if (!ledger) {
		ledger = {
			settled: /* @__PURE__ */ new Set(),
			reported: /* @__PURE__ */ new Set()
		};
		runLedgers.set(persistence, ledger);
	}
	return ledger;
};
const isSettledMessage = (message) => message.role === "assistant" && (message.status.type === "complete" || message.status.type === "incomplete");
const mergeInteractionLogs = (stored, current) => {
	const incoming = readToolInteractionLog(current);
	if (!stored) return incoming;
	if (!incoming) return stored;
	const omitted = Math.max(stored.omitted ?? 0, incoming.omitted ?? 0);
	let merged = {
		entries: stored.entries,
		...omitted ? { omitted } : void 0
	};
	for (const entry of incoming.entries) {
		if (merged.entries.some((existing) => existing.type === entry.type && existing.occurredAt === entry.occurredAt && isJSONValueEqual(existing.payload, entry.payload))) continue;
		merged = appendToolInteraction(merged, entry);
	}
	return merged;
};
const RETRIED_COPY_STATUSES = /* @__PURE__ */ new Set([
	401,
	403,
	408,
	429
]);
const THREAD_REFUSAL_STATUSES = /* @__PURE__ */ new Set([402, 404]);
const isRefusedCopy = (error) => error instanceof CloudAPIError && error.status >= 400 && error.status < 500 && !RETRIED_COPY_STATUSES.has(error.status);
var AssistantCloudThreadHistoryAdapter = class {
	cloudRef;
	getAui;
	runReporter;
	copiedThreads = /* @__PURE__ */ new Map();
	copyQueues = /* @__PURE__ */ new Map();
	constructor(cloudRef, getAui) {
		this.cloudRef = cloudRef;
		this.getAui = getAui;
		this.runReporter = new CloudRunReporter(() => this.cloudRef.current);
	}
	get aui() {
		return this.getAui();
	}
	getCloud() {
		return this.cloudRef.current;
	}
	ownsThread(threadId) {
		const live = this.aui.threadListItem;
		if (!live.source) return false;
		const { id, remoteId } = live.getState();
		return id === threadId || remoteId === threadId;
	}
	getPersistence(threadListItem = this.aui.threadListItem) {
		const key = getClientId(threadListItem);
		if (!globalPersistence.has(key)) globalPersistence.set(key, new CloudMessagePersistence(() => this.cloudRef.current));
		return globalPersistence.get(key);
	}
	get _persistence() {
		return this.getPersistence();
	}
	/**
	* A send is the moment the runtime creates the remote thread, so that one
	* event waits for the id; every other event reads the id that already
	* exists, because initializing a thread nobody has written to would create
	* an empty remote thread just to attribute an event. A thread the list does
	* not know resolves to nothing, which declines the event.
	*/
	async resolveEngagementEventIds(threadId, messageId, options) {
		const threadListItem = this.getThreadListItem(threadId);
		if (!threadListItem) return void 0;
		let remoteThreadId = threadListItem.getState().remoteId;
		if (!remoteThreadId && options?.awaitThread) remoteThreadId = await threadListItem.initialize().then((result) => result.remoteId).catch(() => void 0);
		const remoteMessageId = messageId ? this.getPersistence(threadListItem).getResolvedRemoteId(messageId) : void 0;
		return {
			...remoteThreadId ? { thread_id: remoteThreadId } : void 0,
			...remoteMessageId ? { message_id: remoteMessageId } : void 0
		};
	}
	feedback = { submit: ({ message, type, comment }) => {
		(async () => {
			const threadListItem = this.tryGetKeyedThreadListItem();
			const remoteThreadId = threadListItem?.getState().remoteId;
			if (!threadListItem || !remoteThreadId) {
				console.warn(`[assistant-ui] Skipping feedback for message ${message.id}: the thread has no remote id.`);
				return;
			}
			const cloudMessageId = await this.getPersistence(threadListItem).getRemoteId(message.id);
			if (!cloudMessageId) {
				console.warn(`[assistant-ui] Skipping feedback for message ${message.id}: no cloud message id is mapped.`);
				return;
			}
			await this.cloudRef.current.threads.messages.feedback(remoteThreadId, cloudMessageId, {
				type,
				...comment ? { comment } : void 0
			});
		})().catch((error) => {
			console.error("[assistant-ui] Cloud feedback submission failed:", error);
		});
	} };
	tryGetKeyedThreadListItem() {
		const live = this.aui.threadListItem;
		if (!live.source) return void 0;
		const id = live.getState().id;
		if (id === void 0) return void 0;
		return this.aui.threads.getState().threadItems.some((item) => item.id === id || item.remoteId === id) ? this.aui.threads.item({ id }) : live;
	}
	getThreadListItem(threadId) {
		const current = this.aui.threadListItem;
		if (current.source) {
			const currentState = current.getState();
			if (currentState.id === threadId || currentState.remoteId === threadId) return current;
		}
		const listed = this.aui.threads.getState().threadItems.find((item) => item.id === threadId || item.remoteId === threadId);
		return listed ? this.aui.threads.item({ id: listed.id }) : void 0;
	}
	withFormat(formatAdapter) {
		const adapter = this;
		let threadListItem;
		const pinCurrent = () => {
			const next = adapter.tryGetKeyedThreadListItem();
			if (next) threadListItem = next;
			return threadListItem;
		};
		const resolvePinned = () => threadListItem ?? pinCurrent();
		const getTargetFormatted = (item) => createFormattedPersistence(adapter.getPersistence(item), formatAdapter);
		return {
			pin() {
				pinCurrent();
			},
			async append(item) {
				const pinned = resolvePinned();
				if (!pinned) throw new Error("Cannot persist cloud history without a thread list item.");
				const remoteId = pinned.getState().remoteId ?? (await pinned.initialize()).remoteId;
				await getTargetFormatted(pinned).append(remoteId, item);
			},
			async update(item, localMessageId) {
				const pinned = resolvePinned();
				const remoteId = pinned?.getState().remoteId;
				if (!remoteId || !pinned) return;
				await getTargetFormatted(pinned).update?.(remoteId, item, localMessageId);
			},
			async delete() {
				throw new Error("Assistant Cloud does not support deleting thread messages yet.");
			},
			reportTelemetry(items, options) {
				const encodedRunMessages = items.map((item) => formatAdapter.encode(item));
				adapter._reportRunTelemetry(formatAdapter.format, encodedRunMessages, options, resolvePinned(), mergeRunMessageInfo(extractLastRunMessageInfo(items, formatAdapter), options?.message ? extractRunMessageInfo(options.message, "aui/v0") : void 0));
			},
			async load() {
				const pinned = pinCurrent();
				const live = adapter.aui.threadListItem;
				const remoteId = live.source ? live.getState().remoteId : void 0;
				if (!remoteId) return { messages: [] };
				return getTargetFormatted(pinned ?? live).load(remoteId);
			}
		};
	}
	async append({ parentId, message }) {
		const { remoteId } = await this.aui.threadListItem.initialize();
		const persistence = this._persistence;
		await this._writeMessage(persistence, remoteId, message, (encoded) => persistence.append(remoteId, message.id, parentId, "aui/v0", encoded));
	}
	async update(item) {
		const persistence = this._persistence;
		if (!persistence.isPersisted(item.message.id)) return this.append(item);
		const { message } = item;
		const remoteId = this.aui.threadListItem.getState().remoteId;
		if (!remoteId) return;
		await this._writeMessage(persistence, remoteId, message, (encoded) => persistence.update(remoteId, message.id, "aui/v0", encoded));
	}
	get unstable_copy() {
		const telemetry = this.cloudRef.current?.telemetry;
		return telemetry?.enabled === false || telemetry?.messages === false ? void 0 : this.copy;
	}
	copy = async (branch, messageIds) => {
		const cloud = this.cloudRef.current;
		if (messageIds.length === 0) return;
		const threadListItem = this.tryGetKeyedThreadListItem();
		if (!threadListItem) throw new Error("Cannot copy cloud history without a thread list item.");
		const remoteId = (await threadListItem.initialize()).remoteId;
		const persistence = this.getPersistence(threadListItem);
		const task = (this.copyQueues.get(remoteId) ?? Promise.resolve()).catch(() => void 0).then(() => this.copyBranch(cloud, remoteId, persistence, branch, messageIds));
		this.copyQueues.set(remoteId, task);
		try {
			await task;
		} finally {
			if (this.copyQueues.get(remoteId) === task) this.copyQueues.delete(remoteId);
		}
	};
	async copyBranch(cloud, remoteId, persistence, branch, messageIds) {
		let inventory = this.copiedThreads.get(remoteId);
		if (!inventory) {
			inventory = (async () => {
				const copied = {
					stored: /* @__PURE__ */ new Set(),
					refused: /* @__PURE__ */ new Set(),
					closed: false,
					interactions: /* @__PURE__ */ new Map()
				};
				const seen = /* @__PURE__ */ new Set();
				let after;
				while (true) {
					const page = await cloud.threads.messages.list(remoteId, {
						limit: 200,
						...after ? { after } : void 0
					});
					const fresh = page.messages.filter((row) => !seen.has(row.id));
					for (const row of fresh) {
						seen.add(row.id);
						if (!row.external_id || row.format !== "aui/v0") continue;
						copied.stored.add(row.external_id);
						persistence.record(row.external_id, row.id);
						const decoded = auiV0DecodeSafely(row);
						for (const part of decoded?.message.content ?? []) {
							if (part.type !== "tool-call") continue;
							const merged = mergeInteractionLogs(copied.interactions.get(part.toolCallId), part.unstable_interactions);
							if (merged) copied.interactions.set(part.toolCallId, merged);
						}
					}
					const last = page.messages.at(-1);
					if (fresh.length === 0 || page.messages.length < 200 || !last) break;
					after = last.id;
				}
				return copied;
			})();
			this.copiedThreads.set(remoteId, inventory);
		}
		let copied;
		try {
			copied = await inventory;
		} catch (error) {
			if (this.copiedThreads.get(remoteId) === inventory) this.copiedThreads.delete(remoteId);
			throw error;
		}
		if (copied.closed) return;
		const eligible = branch.filter((message) => message.id.length > 0 && message.id.length <= 255);
		const changed = new Set(messageIds);
		let next = 0;
		let parent;
		for (let index = 0; index < eligible.length; index++) {
			if (!changed.has(eligible[index].id)) continue;
			for (; next <= index; next++) {
				const message = eligible[next];
				if (next !== index && (copied.stored.has(message.id) || copied.refused.has(message.id))) {
					if (copied.stored.has(message.id)) parent = message.id;
					continue;
				}
				const encoded = auiV0Encode(message);
				const content = {
					...encoded,
					content: encoded.content.map((part) => {
						if (part.type !== "tool-call") return part;
						const interactions = mergeInteractionLogs(copied.interactions.get(part.toolCallId), part.unstable_interactions);
						return {
							...part,
							...interactions ? { unstable_interactions: interactions } : void 0
						};
					})
				};
				let message_id;
				try {
					({message_id} = await cloud.threads.messages.create(remoteId, {
						parent_id: null,
						format: "aui/v0",
						content,
						external_id: message.id,
						...parent ? { parent_external_id: parent } : void 0
					}));
				} catch (error) {
					if (!isRefusedCopy(error)) throw error;
					if (THREAD_REFUSAL_STATUSES.has(error.status) || copied.stored.size === 0 && copied.refused.size > 0) {
						copied.closed = true;
						console.warn(`[assistant-ui] The cloud refused copies to thread ${remoteId}; the dashboard shows the conversation as far as it was copied.`, error);
						return;
					}
					copied.refused.add(message.id);
					console.warn(`[assistant-ui] The cloud refused the copy of message ${message.id}; the dashboard shows the conversation without it.`, error);
					continue;
				}
				copied.stored.add(message.id);
				copied.refused.delete(message.id);
				parent = message.id;
				persistence.record(message.id, message_id);
				for (const part of content.content) if (part.type === "tool-call" && part.unstable_interactions) copied.interactions.set(part.toolCallId, part.unstable_interactions);
			}
		}
	}
	async _writeMessage(persistence, remoteId, message, write) {
		const encoded = auiV0Encode(message);
		const ledger = runLedgerOf(persistence);
		const firstSettle = isSettledMessage(message) && !ledger.settled.has(message.id);
		await write(encoded);
		if (!firstSettle) return;
		ledger.settled.add(message.id);
		if (ledger.reported.has(message.id)) return;
		if (!this.cloudRef.current.telemetry.enabled) return;
		const extracted = extractTelemetry("aui/v0", encoded);
		if (!extracted) return;
		ledger.reported.add(message.id);
		this._sendReport(remoteId, extracted, void 0, void 0, extractRunMessageInfo(message, "aui/v0"), persistence);
	}
	async delete() {
		throw new Error("Assistant Cloud does not support deleting thread messages yet.");
	}
	async load() {
		const remoteId = this.aui.threadListItem.getState().remoteId;
		if (!remoteId) return { messages: [] };
		const persistence = this._persistence;
		const rows = (await persistence.load(remoteId, "aui/v0")).filter((m) => m.format === "aui/v0").reverse();
		const loaded = [];
		const loadedIds = /* @__PURE__ */ new Set();
		const { settled } = runLedgerOf(persistence);
		for (const row of rows) {
			const item = auiV0DecodeSafely(row);
			if (!item) continue;
			if (item.parentId && !loadedIds.has(item.parentId)) continue;
			loadedIds.add(item.message.id);
			if (isSettledMessage(item.message)) settled.add(item.message.id);
			loaded.push(item);
		}
		return { messages: loaded };
	}
	_reportRunTelemetry(format, runMessages, options, threadListItem, messageInfo) {
		const item = threadListItem ?? this.aui.threadListItem;
		const remoteId = item.getState().remoteId;
		if (!remoteId) return;
		const extracted = extractRunTelemetry(format, runMessages) ?? (messageInfo?.status !== void 0 ? { status: "incomplete" } : void 0);
		if (!extracted) return;
		this._sendReport(remoteId, extracted, options?.durationMs, options?.stepTimestamps, messageInfo, this.getPersistence(item));
	}
	_sendReport(remoteId, data, durationMs, stepTimestamps, messageInfo, persistence = this._persistence) {
		const mergedSteps = mergeStepTimestamps(data.steps, stepTimestamps);
		const messageId = messageInfo?.localMessageId ? persistence.getResolvedRemoteId(messageInfo.localMessageId) : void 0;
		this.runReporter.report({
			threadId: remoteId,
			status: messageInfo?.status ?? data.status,
			outcome: messageInfo?.outcomeType,
			error: messageInfo?.error,
			errorCode: messageInfo?.errorCode,
			messageId,
			traceId: messageInfo?.traceId,
			modelId: data.modelId,
			provider: messageInfo?.provider,
			usage: data.usage,
			steps: mergedSteps,
			totalSteps: data.totalSteps,
			toolCalls: data.toolCalls,
			durationMs,
			firstTokenMs: messageInfo?.firstTokenMs,
			outputText: data.outputText,
			metadata: data.metadata
		});
	}
};
function mergeStepTimestamps(steps, timestamps) {
	if (!timestamps) return steps;
	if (!steps) return timestamps.map(({ start_ms, end_ms }) => ({
		startMs: start_ms,
		endMs: end_ms
	}));
	const len = Math.min(steps.length, timestamps.length);
	return steps.map((step, index) => ({
		...step,
		...index < len ? {
			startMs: timestamps[index].start_ms,
			endMs: timestamps[index].end_ms
		} : void 0
	}));
}
function extractLastRunMessageInfo(items, formatAdapter) {
	for (let i = items.length - 1; i >= 0; i--) {
		const item = items[i];
		const info = extractRunMessageInfo(item.message, formatAdapter.format, formatAdapter.getId(item.message));
		if (info) return info;
	}
}
function mergeRunMessageInfo(stored, observed) {
	if (!observed) return stored;
	const { localMessageId: _observedId, ...outcome } = observed;
	return {
		...stored,
		...outcome
	};
}
function extractRunMessageInfo(message, format, localMessageId) {
	if (!isRecord(message) || message.role !== "assistant") return void 0;
	const status = isRecord(message.status) ? message.status : void 0;
	const metadata = isRecord(message.metadata) ? message.metadata : void 0;
	const custom = isRecord(metadata?.custom) ? metadata.custom : void 0;
	const firstTokenTime = (isRecord(metadata?.timing) ? metadata.timing : void 0)?.firstTokenTime;
	const firstTokenMs = typeof firstTokenTime === "number" && Number.isFinite(firstTokenTime) ? Math.round(firstTokenTime) : void 0;
	const finishReason = status?.type === "incomplete" ? typeof status.reason === "string" ? status.reason : void 0 : typeof metadata?.finishReason === "string" ? metadata.finishReason : void 0;
	const failed = status?.type === "incomplete" && status.reason === "error";
	const outcome = deriveRunOutcome({
		finishReason,
		isError: failed
	});
	const outcomeType = outcome.outcome;
	const runStatus = outcome.status === "error" ? "error" : status?.type === "incomplete" ? "incomplete" : finishReason !== void 0 ? outcome.status : void 0;
	const failure = failed ? describeRunError(status.error) : {};
	const messageId = localMessageId ?? (typeof message.id === "string" ? message.id : void 0);
	const traceId = format === "aui/v0" ? custom?.traceId : format === "ai-sdk/v6" ? metadata?.traceId : void 0;
	const provider = typeof custom?.provider === "string" ? custom.provider : typeof metadata?.provider === "string" ? metadata.provider : void 0;
	return {
		...messageId ? { localMessageId: messageId } : void 0,
		...runStatus !== void 0 ? { status: runStatus } : void 0,
		...outcomeType ? { outcomeType } : void 0,
		...failure,
		...firstTokenMs != null && firstTokenMs >= 0 ? { firstTokenMs } : void 0,
		...typeof traceId === "string" ? { traceId } : void 0,
		...provider !== void 0 ? { provider } : void 0
	};
}
function isRecord(value) {
	return value !== null && typeof value === "object";
}
const usageTokenKeys = [
	"inputTokens",
	"outputTokens",
	"reasoningTokens",
	"cachedInputTokens",
	"promptTokens",
	"completionTokens"
];
const readTokenCount = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : void 0;
const readStoredTelemetryUsage = (value) => {
	if (!isRecord(value) || Array.isArray(value)) return void 0;
	const usage = {};
	for (const key of usageTokenKeys) {
		const count = readTokenCount(value[key]);
		if (count !== void 0) usage[key] = count;
	}
	const cacheReadTokens = isRecord(value.inputTokenDetails) && !Array.isArray(value.inputTokenDetails) ? readTokenCount(value.inputTokenDetails.cacheReadTokens) : void 0;
	if (cacheReadTokens !== void 0) usage.inputTokenDetails = { cacheReadTokens };
	const reasoningTokens = isRecord(value.outputTokenDetails) && !Array.isArray(value.outputTokenDetails) ? readTokenCount(value.outputTokenDetails.reasoningTokens) : void 0;
	if (reasoningTokens !== void 0) usage.outputTokenDetails = { reasoningTokens };
	return Object.keys(usage).length > 0 ? usage : void 0;
};
const parseStoredTelemetrySteps = (value) => parseStoredThreadSteps(value).map((step) => {
	const usage = readStoredTelemetryUsage(step.usage);
	return usage ? { usage } : {};
});
function extractTelemetry(format, content) {
	switch (format) {
		case "aui/v0": return extractAuiV0(content);
		case "ai-sdk/v6": return extractAISDKRunTelemetry([content]);
		default: return null;
	}
}
function extractRunTelemetry(format, runMessages) {
	if (format === "ai-sdk/v6") return extractAISDKRunTelemetry(runMessages);
	for (let i = runMessages.length - 1; i >= 0; i--) {
		const result = extractTelemetry(format, runMessages[i]);
		if (result) return result;
	}
	return null;
}
function extractAuiV0(content) {
	const msg = content;
	if (msg.role !== "assistant") return null;
	if (msg.status !== void 0 && !isStoredMessageStatus(msg.status)) return null;
	const statusType = isRecord(msg.status) && typeof msg.status.type === "string" ? msg.status.type : void 0;
	if (statusType === "running" || statusType === "requires-action") return null;
	const toolCalls = msg.content?.filter((p) => p.type === "tool-call" && p.toolName && p.toolCallId).map((p) => createRunTelemetryToolCall({
		toolName: p.toolName,
		toolCallId: p.toolCallId,
		args: p.args,
		result: p.result,
		argsText: p.argsText
	}));
	const textParts = msg.content?.filter((p) => p.type === "text" && p.text);
	const outputText = textParts && textParts.length > 0 ? truncateRunTelemetryText(textParts.map((p) => p.text).join("")) : void 0;
	const steps = parseStoredTelemetrySteps(msg.metadata?.steps);
	let inputTokens;
	let outputTokens;
	let reasoningTokens;
	let cachedInputTokens;
	if (steps && steps.length > 0) {
		let totalInput = 0;
		let totalOutput = 0;
		let totalReasoning = 0;
		let totalCachedInput = 0;
		let hasInput = false;
		let hasOutput = false;
		let hasReasoning = false;
		let hasCachedInput = false;
		for (const step of steps) {
			if (!step.usage) continue;
			const usage = normalizeRunTelemetryUsage(step.usage);
			if (!usage) continue;
			if (usage.inputTokens != null) {
				totalInput += usage.inputTokens;
				hasInput = true;
			}
			if (usage.outputTokens != null) {
				totalOutput += usage.outputTokens;
				hasOutput = true;
			}
			if (usage.reasoningTokens != null) {
				totalReasoning += usage.reasoningTokens;
				hasReasoning = true;
			}
			if (usage.cachedInputTokens != null) {
				totalCachedInput += usage.cachedInputTokens;
				hasCachedInput = true;
			}
		}
		inputTokens = hasInput ? totalInput : void 0;
		outputTokens = hasOutput ? totalOutput : void 0;
		reasoningTokens = hasReasoning ? totalReasoning : void 0;
		cachedInputTokens = hasCachedInput ? totalCachedInput : void 0;
	}
	const status = statusType === "incomplete" ? "incomplete" : "completed";
	const metadata = msg.metadata?.custom;
	const modelId = extractRunTelemetryModelId(msg.metadata);
	const telemetrySteps = steps.length > 0 ? steps : void 0;
	return {
		status,
		...toolCalls && toolCalls.length > 0 ? { toolCalls } : void 0,
		...steps?.length ? { totalSteps: steps.length } : void 0,
		...inputTokens != null || outputTokens != null || reasoningTokens != null || cachedInputTokens != null ? { usage: {
			...inputTokens != null ? { inputTokens } : void 0,
			...outputTokens != null ? { outputTokens } : void 0,
			...reasoningTokens != null ? { reasoningTokens } : void 0,
			...cachedInputTokens != null ? { cachedInputTokens } : void 0
		} } : void 0,
		...outputText != null ? { outputText } : void 0,
		...metadata ? { metadata } : void 0,
		...telemetrySteps ? { steps: telemetrySteps } : void 0,
		...modelId ? { modelId } : void 0
	};
}
function useAssistantCloudThreadHistoryAdapter(cloudRef) {
	const aui = useAui();
	const auiRef = useRef(aui);
	useEffect(() => {
		auiRef.current = aui;
	});
	const [adapter] = useState(() => new AssistantCloudThreadHistoryAdapter(cloudRef, () => auiRef.current));
	useAssistantCloudEngagementEvents(adapter, aui);
	return adapter;
}
const engagementTrackers = /* @__PURE__ */ new WeakMap();
const mountedAdapter = (tracker, threadId) => {
	let fallback;
	for (const adapter of tracker.mounted.keys()) {
		if (threadId !== void 0 && adapter.ownsThread(threadId)) return adapter;
		fallback ??= adapter;
	}
	return fallback ?? tracker.lastMounted;
};
const createEngagementTracker = (adapter) => {
	const tracker = {
		mounted: /* @__PURE__ */ new Map(),
		lastMounted: adapter,
		reporter: new CloudEngagementReporter(() => mountedAdapter(tracker).getCloud(), (threadId, messageId, options) => mountedAdapter(tracker, threadId).resolveEngagementEventIds(threadId, messageId, options)),
		host: void 0,
		dispose: void 0
	};
	return tracker;
};
const subscribeEngagementEvents = (aui, reporter) => {
	const reportSuggestions = () => {
		const { mainThreadId } = aui.threads.getState();
		const { isEmpty, suggestions } = aui.thread.getState();
		if (!isEmpty || suggestions.length === 0) return;
		reporter.suggestionsShown(mainThreadId, suggestions.length);
	};
	const unsubscribers = [
		aui.on({
			scope: "*",
			event: "threads.selectionChanged"
		}, (payload) => {
			reporter.threadSwitched(payload.threadId);
		}),
		aui.on({
			scope: "*",
			event: "composer.send"
		}, (payload) => {
			if (payload.messageId) reporter.messageEdited(payload.threadId, {
				messageId: payload.messageId,
				chars: payload.chars
			});
			else reporter.messageSent(payload.threadId, {
				chars: payload.chars,
				attachments: payload.attachments
			});
			if (payload.suggestion) reporter.suggestionClicked(payload.threadId);
		}),
		aui.on({
			scope: "*",
			event: "composer.attachmentAdd"
		}, (payload) => {
			reporter.attachmentAdded(payload.threadId, {
				messageId: payload.messageId,
				contentType: payload.contentType
			});
		}),
		aui.on({
			scope: "*",
			event: "composer.attachmentAddError"
		}, (payload) => {
			reporter.attachmentFailed(payload.threadId, {
				messageId: payload.messageId,
				contentType: payload.contentType
			});
		}),
		aui.on({
			scope: "*",
			event: "composer.cancel"
		}, (payload) => {
			reporter.runStopped(payload.threadId);
		}),
		aui.on({
			scope: "*",
			event: "thread.runStart"
		}, (payload) => {
			reporter.runStarted(payload.threadId);
		}),
		aui.on({
			scope: "*",
			event: "thread.runEnd"
		}, (payload) => {
			reporter.runEnded(payload.threadId);
		}),
		aui.on({
			scope: "*",
			event: "thread.cancelRun"
		}, (payload) => {
			reporter.runStopped(payload.threadId);
		}),
		aui.on({
			scope: "*",
			event: "thread.voiceStarted"
		}, (payload) => {
			reporter.voiceStarted(payload.threadId);
		}),
		aui.on({
			scope: "*",
			event: "message.reload"
		}, (payload) => {
			reporter.messageRegenerated(payload.threadId, payload.messageId);
		}),
		aui.on({
			scope: "*",
			event: "message.branchSwitched"
		}, (payload) => {
			reporter.branchSwitched(payload.threadId, payload.messageId);
		}),
		aui.on({
			scope: "*",
			event: "message.copied"
		}, (payload) => {
			reporter.messageCopied(payload.threadId, payload.messageId);
		}),
		aui.on({
			scope: "*",
			event: "thread.toolApprovalAnswered"
		}, (payload) => {
			if (payload.approved) reporter.toolApproved(payload.threadId, payload.messageId, payload.toolCallId, payload.toolName);
			else reporter.toolRejected(payload.threadId, payload.messageId, payload.toolCallId, payload.toolName);
		}),
		aui.on({
			scope: "*",
			event: "message.speak"
		}, (payload) => {
			reporter.speechStarted(payload.threadId, payload.messageId);
		}),
		aui.on({
			scope: "*",
			event: "message.error"
		}, (payload) => {
			reporter.errorShown(payload.threadId, {
				messageId: payload.messageId,
				reason: payload.reason
			});
		}),
		aui.subscribe(reportSuggestions)
	];
	reportSuggestions();
	return () => runCleanups(unsubscribers);
};
const installEngagementEvents = (tracker, host) => {
	tracker.host = host;
	tracker.dispose = subscribeEngagementEvents(host, tracker.reporter);
};
const uninstallEngagementEvents = (tracker) => {
	const dispose = tracker.dispose;
	tracker.host = void 0;
	tracker.dispose = void 0;
	dispose?.();
};
/**
* The client delivers an event to every listener once per emission, and a
* thread runtime, with this adapter inside it, mounts once per visited
* thread. One subscription set per thread list therefore reports each event
* once, attributed by the thread id the event carries, and the reporter that
* keeps run timing per thread lives as long as the list. The subscriptions
* ride on one mounted thread's client, because a thread's own client stops
* forwarding state notifications once its runtime unmounts, so they move to
* another mounted thread when their host leaves.
*/
const useAssistantCloudEngagementEvents = (adapter, aui) => {
	const $ = c(4);
	let t0;
	let t1;
	if ($[0] !== adapter || $[1] !== aui) {
		t0 = () => {
			const key = getClientId(aui.threads);
			let tracker = engagementTrackers.get(key);
			if (!tracker) {
				tracker = createEngagementTracker(adapter);
				engagementTrackers.set(key, tracker);
			}
			const active = tracker;
			active.mounted.set(adapter, aui);
			active.lastMounted = adapter;
			if (active.host === void 0) installEngagementEvents(active, aui);
			return () => {
				active.mounted.delete(adapter);
				if (active.host !== aui) return;
				uninstallEngagementEvents(active);
				const next = active.mounted.values().next();
				if (!next.done) installEngagementEvents(active, next.value);
			};
		};
		t1 = [adapter, aui];
		$[0] = adapter;
		$[1] = aui;
		$[2] = t0;
		$[3] = t1;
	} else {
		t0 = $[2];
		t1 = $[3];
	}
	useEffect(t0, t1);
};
//#endregion
export { extractAuiV0, useAssistantCloudThreadHistoryAdapter };
