import { isRecord } from "../../../utils/json/is-json.js";
import { InMemoryThreadListAdapter } from "../../../runtimes/remote-thread-list/adapter/in-memory.js";
import { useAssistantCloudThreadHistoryAdapter } from "./AssistantCloudThreadHistoryAdapter.js";
import { CloudFileAttachmentAdapter } from "./CloudFileAttachmentAdapter.js";
import { CORE_SDK } from "./sdkIdentity.js";
import { useMemo, useState } from "@assistant-ui/tap/react-shim";
import { AssistantCloud } from "assistant-cloud";
//#region src/react/runtimes/cloud/createCloudThreadListAdapter.ts
const toCustom = (value) => isRecord(value) ? value : void 0;
const baseUrl = typeof process !== "undefined" ? process.env.NEXT_PUBLIC_ASSISTANT_BASE_URL : void 0;
const autoCloud = baseUrl ? new AssistantCloud({
	baseUrl,
	anonymous: true
}) : void 0;
const useCloudRuntimeAdapters = (cloudRef) => {
	const history = useAssistantCloudThreadHistoryAdapter(cloudRef);
	const [attachments] = useState(() => new CloudFileAttachmentAdapter(() => cloudRef.current));
	return useMemo(() => ({
		history,
		attachments,
		feedback: history.feedback
	}), [history, attachments]);
};
const CLOUD_THREAD_PAGE_SIZE = 20;
const parseListCursor = (after) => {
	const fallback = {
		activeCursor: after,
		archivedCursor: void 0,
		activeExhausted: false,
		archivedExhausted: false
	};
	if (!after || !after.startsWith("{")) return fallback;
	try {
		const parsed = JSON.parse(after);
		if (!isRecord(parsed)) return fallback;
		return {
			activeCursor: typeof parsed.a === "string" ? parsed.a : void 0,
			archivedCursor: typeof parsed.r === "string" ? parsed.r : void 0,
			activeExhausted: parsed.ae === true,
			archivedExhausted: parsed.re === true
		};
	} catch {
		return fallback;
	}
};
/**
* Builds the `RemoteThreadListAdapter` for an assistant-cloud backend without
* requiring a hook call site, so plain code (a Vue or Svelte setup function,
* a module-level config) can construct it. Options are read through the
* getter on every call, so a stable adapter can follow changing `create` and
* `delete` callbacks; swapping to a different `cloud` instance requires a new
* adapter (and `reload()` on the list). Without a `cloud` instance (and
* without `NEXT_PUBLIC_ASSISTANT_BASE_URL`), the adapter falls back to an
* in-memory list. `useCloudThreadListAdapter` wraps this for the React
* hook signature.
*/
const createCloudThreadListAdapter = (options) => {
	const getOptions = typeof options === "function" ? options : () => options;
	const unstable_useAdapters = function useCloudAdapters() {
		return useCloudRuntimeAdapters({ get current() {
			return getOptions().cloud ?? autoCloud;
		} });
	};
	const cloud = getOptions().cloud ?? autoCloud;
	if (!cloud) {
		const inMemory = new InMemoryThreadListAdapter();
		inMemory.initialize = async (threadId) => {
			return {
				remoteId: threadId,
				externalId: (await getOptions().create?.(threadId))?.externalId
			};
		};
		return inMemory;
	}
	cloud.registerSdk?.(CORE_SDK);
	const sdk = getOptions().sdk;
	if (sdk) cloud.registerSdk?.(sdk);
	return {
		list: async ({ after } = {}) => {
			const { activeCursor, archivedCursor, activeExhausted, archivedExhausted } = parseListCursor(after);
			const [{ threads: activeThreads }, { threads: archivedThreads }] = await Promise.all([activeExhausted ? Promise.resolve({ threads: [] }) : cloud.threads.list({
				limit: CLOUD_THREAD_PAGE_SIZE,
				...activeCursor ? { after: activeCursor } : {}
			}), archivedExhausted ? Promise.resolve({ threads: [] }) : cloud.threads.list({
				is_archived: true,
				limit: CLOUD_THREAD_PAGE_SIZE,
				...archivedCursor ? { after: archivedCursor } : {}
			})]);
			const activeNext = !activeExhausted && activeThreads.length === CLOUD_THREAD_PAGE_SIZE ? activeThreads.at(-1)?.id : void 0;
			const archivedNext = !archivedExhausted && archivedThreads.length === CLOUD_THREAD_PAGE_SIZE ? archivedThreads.at(-1)?.id : void 0;
			return {
				threads: [...activeThreads, ...archivedThreads].map((t) => ({
					status: t.is_archived ? "archived" : "regular",
					remoteId: t.id,
					title: t.title,
					lastMessageAt: t.last_message_at ? new Date(t.last_message_at) : void 0,
					externalId: t.external_id ?? void 0,
					custom: toCustom(t.metadata)
				})),
				nextCursor: activeNext || archivedNext ? JSON.stringify({
					a: activeNext,
					r: archivedNext,
					...activeNext === void 0 ? { ae: true } : {},
					...archivedNext === void 0 ? { re: true } : {}
				}) : void 0
			};
		},
		initialize: async (threadId) => {
			const t = await (getOptions().create?.(threadId) ?? Promise.resolve());
			const external_id = t ? t.externalId : void 0;
			const { thread_id: remoteId } = await cloud.threads.create({
				last_message_at: /* @__PURE__ */ new Date(),
				external_id,
				...external_id !== void 0 && getOptions().upsert ? { upsert: true } : {}
			});
			return {
				externalId: external_id,
				remoteId
			};
		},
		rename: async (threadId, newTitle) => {
			return cloud.threads.update(threadId, { title: newTitle });
		},
		updateCustom: async (threadId, custom) => {
			return cloud.threads.update(threadId, { metadata: custom ?? null });
		},
		archive: async (threadId) => {
			return cloud.threads.update(threadId, { is_archived: true });
		},
		unarchive: async (threadId) => {
			return cloud.threads.update(threadId, { is_archived: false });
		},
		delete: async (threadId) => {
			await getOptions().delete?.(threadId);
			return cloud.threads.delete(threadId);
		},
		generateTitle: async (threadId, messages) => {
			const filteredMessages = messages.map((msg) => ({
				...msg,
				content: msg.content.filter((part) => part.type === "text" || part.type === "tool-call")
			}));
			return cloud.runs.stream({
				thread_id: threadId,
				assistant_id: "system/thread_title",
				messages: filteredMessages
			});
		},
		fetch: async (threadId) => {
			const thread = await cloud.threads.get(threadId);
			return {
				status: thread.is_archived ? "archived" : "regular",
				remoteId: thread.id,
				title: thread.title,
				lastMessageAt: thread.last_message_at ? new Date(thread.last_message_at) : void 0,
				externalId: thread.external_id ?? void 0,
				custom: toCustom(thread.metadata)
			};
		},
		unstable_useAdapters
	};
};
//#endregion
export { autoCloud, createCloudThreadListAdapter, useCloudRuntimeAdapters };
