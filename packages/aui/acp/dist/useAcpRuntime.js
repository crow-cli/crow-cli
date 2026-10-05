"use client";
import { AcpClient } from "./AcpClient.js";
import { isAcpStateRunning } from "./acpThreadState.js";
import { AcpThreadController } from "./AcpThreadController.js";
import { acpExtras } from "./acpExtras.js";
import { projectAcpThreadRepository } from "./acpMessageProjection.js";
import { useAcpControllerState } from "./useAcpControllerState.js";
import { invokeUserCallback } from "@assistant-ui/core/internal";
import { createMessageQueue } from "@assistant-ui/core";
import { useExternalStoreRuntime, useExternalStoreSharedOptions, useRuntimeAdapters } from "@assistant-ui/core/react";
import { useCallback, useEffect, useInsertionEffect, useMemo, useRef, useState } from "react";
//#region src/useAcpRuntime.ts
const createRegistry = (key, client, ownsClient) => {
	let disposeTimer;
	return {
		key,
		client,
		controller: new AcpThreadController({ client }),
		activate() {
			if (disposeTimer === void 0) return;
			clearTimeout(disposeTimer);
			disposeTimer = void 0;
		},
		release() {
			if (!ownsClient) return;
			disposeTimer ??= setTimeout(() => {
				disposeTimer = void 0;
				client.cancel().then(() => client.dispose(), () => client.dispose());
			}, 0);
		}
	};
};
const toError = (error) => error instanceof Error ? error : new Error(String(error));
const buildManagedClientOptions = (options) => {
	const { url } = options;
	if (!url) throw new Error("useAcpRuntime requires either `client` or `url`");
	return {
		url,
		...options.cwd !== void 0 && { cwd: options.cwd },
		mcpServers: options.mcpServers ?? [],
		...options.clientInfo && { clientInfo: options.clientInfo }
	};
};
function useAcpRuntime(options) {
	const runtimeAdapters = useRuntimeAdapters();
	const webSocketFactory = options.webSocketFactory;
	const webSocketFactoryRef = useRef(webSocketFactory);
	useEffect(() => {
		webSocketFactoryRef.current = webSocketFactory;
	}, [webSocketFactory]);
	const stableWebSocketFactory = useMemo(() => (url) => {
		const factory = webSocketFactoryRef.current;
		if (factory) return factory(url);
		return new WebSocket(url);
	}, []);
	const externalClient = options.client;
	const managedClientOptions = externalClient ? void 0 : buildManagedClientOptions(options);
	const registryKey = externalClient ? "external" : JSON.stringify(managedClientOptions);
	const createRegistryClient = () => externalClient ? externalClient : new AcpClient({
		...managedClientOptions,
		webSocketFactory: stableWebSocketFactory
	});
	const ownsClient = !externalClient;
	const [pinned, setPinned] = useState(() => createRegistry(registryKey, createRegistryClient(), ownsClient));
	let registry = pinned;
	if (externalClient ? registry.client !== externalClient : registry.key !== registryKey) {
		registry = createRegistry(registryKey, createRegistryClient(), ownsClient);
		setPinned(registry);
	}
	const { controller, client } = registry;
	useEffect(() => {
		registry.activate();
		controller.attach();
		return () => {
			controller.detach();
			registry.release();
		};
	}, [controller, registry]);
	const permissions = options.permissions;
	const autoConnect = options.autoConnect;
	const restoreOnConnect = options.restoreOnConnect;
	const onErrorRef = useRef(options.onError);
	const onCancelRef = useRef(options.onCancel);
	useEffect(() => {
		onErrorRef.current = options.onError;
		onCancelRef.current = options.onCancel;
	});
	const reportError = useCallback((error) => {
		invokeUserCallback("acp", "onError", onErrorRef.current, toError(error));
	}, []);
	const reportCancel = useCallback(() => {
		invokeUserCallback("acp", "onCancel", onCancelRef.current);
	}, []);
	useEffect(() => {
		let cancelled = false;
		(async () => {
			await controller.updateOptions({
				client,
				permissions,
				autoConnect,
				restoreOnConnect,
				onError: reportError,
				onCancel: reportCancel
			});
			if (cancelled) return;
			await controller.load();
		})().catch(reportError);
		return () => {
			cancelled = true;
		};
	}, [
		autoConnect,
		client,
		controller,
		permissions,
		reportCancel,
		reportError,
		restoreOnConnect
	]);
	const adapters = options.adapters;
	const adapterAdapters = useMemo(() => ({
		attachments: adapters?.attachments ?? runtimeAdapters?.attachments,
		speech: adapters?.speech,
		dictation: adapters?.dictation,
		voice: adapters?.voice,
		feedback: adapters?.feedback
	}), [adapters, runtimeAdapters]);
	const state = useAcpControllerState(controller);
	const messageRepository = useMemo(() => projectAcpThreadRepository(state), [state]);
	const extras = useMemo(() => acpExtras.provide({
		setConfigOption: (configId, value) => controller.setConfigOption(configId, value),
		connectionState: state.connectionState,
		sessionId: state.sessionId,
		agentInfo: state.agentInfo,
		agentCapabilities: state.agentCapabilities,
		plan: state.plan,
		sessionTitle: state.sessionTitle,
		currentModeId: state.currentModeId,
		availableCommands: state.availableCommands,
		configOptions: state.configOptions,
		usage: state.usage
	}), [controller, state]);
	const shared = useExternalStoreSharedOptions(options);
	const isLoading = state.loadState.type === "loading";
	const isRunning = isAcpStateRunning(state);
	const enableQueue = options.unstable_enableMessageQueue === true;
	const queues = useRef(/* @__PURE__ */ new Map());
	const appendTarget = useRef(controller);
	const activeQueueRef = useRef(null);
	useInsertionEffect(() => {
		appendTarget.current = controller;
	}, [controller]);
	const sessionId = state.sessionId;
	const activeQueue = useMemo(() => {
		if (!enableQueue) return null;
		const key = sessionId ?? "";
		const existing = queues.current.get(key);
		if (existing) return existing;
		const queue = {
			edges: 0,
			controller: null
		};
		queue.controller = createMessageQueue({ run: (message) => {
			const edges = queue.edges;
			const releaseIfNoRun = () => {
				if (queue.edges === edges) queue.controller?.notifyIdle();
			};
			appendTarget.current.append(message).then(releaseIfNoRun, releaseIfNoRun);
		} });
		queues.current.set(key, queue);
		return queue;
	}, [enableQueue, sessionId]);
	useEffect(() => {
		if (enableQueue) return;
		for (const queue of queues.current.values()) queue.controller?.clear();
		queues.current.clear();
	}, [enableQueue]);
	const queueController = activeQueue?.controller ?? null;
	useInsertionEffect(() => {
		activeQueueRef.current = activeQueue;
	}, [activeQueue]);
	const holdActiveQueue = useCallback(() => {
		activeQueueRef.current?.controller?.hold();
	}, []);
	const [queueTick, setQueueTick] = useState(0);
	useEffect(() => queueController?.subscribe(() => setQueueTick((tick) => tick + 1)), [queueController]);
	const wasRunning = useRef(isRunning);
	const openQueue = useRef(null);
	useEffect(() => {
		if (!activeQueue) return;
		const queue = activeQueue.controller;
		if (openQueue.current !== activeQueue) {
			openQueue.current = activeQueue;
			wasRunning.current = isRunning;
			queue?.release();
			if (isRunning) {
				activeQueue.edges += 1;
				queue?.notifyBusy();
			}
			return;
		}
		const previous = wasRunning.current;
		wasRunning.current = isRunning;
		if (previous === isRunning) return;
		if (isRunning) {
			activeQueue.edges += 1;
			queue?.notifyBusy();
		} else queue?.notifyIdle();
	}, [activeQueue, isRunning]);
	const queueAdapter = useMemo(() => {
		if (!queueController) return void 0;
		const { adapter } = queueController;
		return {
			get items() {
				return adapter.items;
			},
			get steerItems() {
				return adapter.steerItems;
			},
			enqueue: (message) => adapter.enqueue(message),
			steer: (message) => adapter.steer(message),
			sendNow: (message) => {
				controller.steer(message);
			},
			move: (queueItemId, placement) => adapter.move(queueItemId, placement),
			edit: (queueItemId, message) => adapter.edit(queueItemId, message),
			remove: (queueItemId) => adapter.remove(queueItemId),
			__internal_setDispatchTransform: (transform) => adapter.__internal_setDispatchTransform?.(transform)
		};
	}, [
		controller,
		queueController,
		queueTick
	]);
	const [threads, setThreads] = useState([]);
	const [threadsLoading, setThreadsLoading] = useState(false);
	const refreshInFlight = useRef(void 0);
	const refreshThreads = useCallback(() => {
		refreshInFlight.current ??= (async () => {
			setThreadsLoading(true);
			try {
				const page = await client.listSessions(options.cwd !== void 0 ? { cwd: options.cwd } : void 0);
				setThreads(page.sessions);
			} catch (error) {
				reportError(error);
			} finally {
				setThreadsLoading(false);
				refreshInFlight.current = void 0;
			}
		})();
		return refreshInFlight.current;
	}, [
		client,
		options.cwd,
		reportError
	]);
	useEffect(() => {
		if (state.connectionState !== "connected") return;
		refreshThreads();
	}, [
		isRunning,
		refreshThreads,
		state.connectionState,
		state.sessionId
	]);
	const threadList = useMemo(() => ({
		threadId: state.sessionId,
		isLoading: threadsLoading,
		threads: threads.map((session) => ({
			status: "regular",
			id: session.sessionId,
			...session.title !== void 0 && { title: session.title },
			custom: {
				cwd: session.cwd,
				...session.updatedAt !== void 0 && { updatedAt: session.updatedAt }
			}
		})),
		onSwitchToNewThread: async () => {
			holdActiveQueue();
			await controller.switchToNewThread();
			await refreshThreads();
		},
		onSwitchToThread: async (threadId) => {
			holdActiveQueue();
			await controller.switchToThread(threadId);
			await refreshThreads();
		},
		onDelete: async (threadId) => {
			if (threadId === state.sessionId) holdActiveQueue();
			await controller.deleteThread(threadId);
			const deleted = queues.current.get(threadId);
			if (deleted) {
				deleted.controller?.clear();
				queues.current.delete(threadId);
			}
			await refreshThreads();
		}
	}), [
		controller,
		holdActiveQueue,
		refreshThreads,
		state.sessionId,
		threads,
		threadsLoading
	]);
	const store = useMemo(() => ({
		...shared,
		isLoading,
		isRunning,
		unstable_persistsHistory: true,
		messageRepository,
		extras,
		onNew: (message) => message.steer === true ? controller.steer(message) : controller.append(message),
		onCancel: () => controller.cancel(),
		onRespondToToolApproval: (approval) => controller.respondToApproval(approval),
		setMessages: (messages) => controller.applyExternalMessages(messages),
		onImport: (messages) => controller.applyExternalMessages(messages),
		...queueAdapter !== void 0 && { queue: queueAdapter },
		adapters: {
			...adapterAdapters,
			threadList
		}
	}), [
		adapterAdapters,
		controller,
		extras,
		isLoading,
		isRunning,
		messageRepository,
		queueAdapter,
		shared,
		threadList
	]);
	return useExternalStoreRuntime(store);
}
//#endregion
export { useAcpRuntime };
