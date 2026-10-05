"use client";
import { generateId } from "../../../utils/id.js";
import { createRequestHeaders } from "../../../runtimes/assistant-transport/utils.js";
import { useExternalStoreRuntime } from "../useExternalStoreRuntime.js";
import { useRemoteThreadListRuntime } from "../useRemoteThreadListRuntime.js";
import { useCloudThreadListAdapter } from "../cloud/useCloudThreadListAdapter.js";
import { useCommandQueue } from "./commandQueue.js";
import { createReplayBoundaryStream, useReplayRenderWait } from "./replayBoundaryStream.js";
import { useRunManager } from "./runManager.js";
import { useConvertedState } from "./useConvertedState.js";
import { AssistantMessageAccumulator, AssistantTransportDecoder, DataStreamDecoder, toToolsJSONSchema, unstable_createInitialMessage } from "assistant-stream";
import { asAsyncIterableStream } from "assistant-stream/utils";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useMemo, useRef, useState } from "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/runtimes/assistant-transport/useAssistantTransportRuntime.ts
const convertAppendMessageToCommand = (message) => {
	if (message.role !== "user") throw new Error("Only user messages are supported");
	const parts = [];
	const content = [...message.content, ...message.attachments?.flatMap((a) => a.content) ?? []];
	for (const contentPart of content) if (contentPart.type === "text") parts.push({
		type: "text",
		text: contentPart.text
	});
	else if (contentPart.type === "image") parts.push({
		type: "image",
		image: contentPart.image
	});
	if (parts.length === 0) return null;
	return {
		type: "add-message",
		message: {
			role: "user",
			id: generateId(),
			parts
		},
		parentId: message.parentId,
		sourceId: message.sourceId
	};
};
const readResumeState = async (response) => {
	if (response.status === 204) return null;
	if (!response.ok) throw new Error(`Resume state request failed with status ${response.status}: ${await response.text()}`);
	let value;
	try {
		value = await response.json();
	} catch {
		throw new Error("Resume state response was not valid JSON");
	}
	if (typeof value !== "object" || value === null || !("state" in value) || !("runId" in value) || typeof value.runId !== "string") throw new Error("Resume state response must contain state and runId");
	return {
		runId: value.runId,
		state: value.state
	};
};
const abortable = (signal, start) => new Promise((resolve, reject) => {
	const onAbort = () => reject(signal.reason);
	if (signal.aborted) return onAbort();
	signal.addEventListener("abort", onAbort, { once: true });
	start().then(resolve, reject).finally(() => signal.removeEventListener("abort", onAbort));
});
const symbolAssistantTransportExtras = Symbol("assistant-transport-extras");
const asAssistantTransportExtras = (extras) => {
	if (typeof extras !== "object" || extras == null || !(symbolAssistantTransportExtras in extras)) throw new Error("This method can only be called when you are using useAssistantTransportRuntime");
	return extras;
};
const useAssistantTransportSendCommand = () => {
	const $ = c(2);
	const aui = useAui();
	let t0;
	if ($[0] !== aui.thread) {
		t0 = (command) => {
			const extras = aui.thread.getState().extras;
			asAssistantTransportExtras(extras).sendCommand(command);
		};
		$[0] = aui.thread;
		$[1] = t0;
	} else t0 = $[1];
	return t0;
};
function useAssistantTransportState(selector = (t) => t) {
	return useAuiState((s) => selector(asAssistantTransportExtras(s.thread.extras).state));
}
const useAssistantTransportThreadRuntime = (options) => {
	const agentStateRef = useRef(options.initialState);
	const [, rerender] = useState(0);
	const resumeFlagRef = useRef(false);
	const [isReplaying, setIsReplaying] = useState(false);
	const waitForReplayRender = useReplayRenderWait();
	const parentIdRef = useRef(void 0);
	const commandQueue = useCommandQueue({ onQueue: () => runManager.schedule() });
	const enqueueAppendMessage = (message) => {
		const command = convertAppendMessageToCommand(message);
		if (!command) {
			console.warn("[assistant-ui] Skipped add-message command with no supported parts");
			return;
		}
		parentIdRef.current = message.parentId;
		commandQueue.enqueue(command, { schedule: message.startRun ?? message.role === "user" });
	};
	const aui = useAui();
	const runManager = useRunManager({
		onRun: async (signal) => {
			const isResume = resumeFlagRef.current;
			resumeFlagRef.current = false;
			setIsReplaying(false);
			const commands = isResume ? [] : commandQueue.flush();
			if (commands.length === 0 && !isResume) return;
			const parentId = isResume ? void 0 : parentIdRef.current;
			if (!isResume) parentIdRef.current = void 0;
			const threadId = aui.threadListItem.getState().remoteId ?? (isResume ? void 0 : (await abortable(signal, () => aui.threadListItem.initialize())).remoteId);
			const headers = await createRequestHeaders(options.headers);
			let resumeState;
			if (isResume && options.resumeStateApi) {
				const resumeStateResponse = await fetch(options.resumeStateApi, {
					method: "POST",
					headers,
					body: JSON.stringify({ threadId }),
					signal
				});
				const retained = await readResumeState(resumeStateResponse);
				if (retained === null) {
					if (commandQueue.state.queued.length > 0) runManager.schedule();
					return;
				}
				resumeState = retained;
			}
			const bodyValue = typeof options.body === "function" ? await options.body() : options.body;
			const context = runtime.thread.getModelContext();
			const sendCommandsBody = {
				commands,
				...resumeState === void 0 && { state: agentStateRef.current },
				system: context.system,
				tools: context.tools ? toToolsJSONSchema(context.tools) : void 0,
				...threadId !== void 0 && { threadId },
				...parentId !== void 0 && { parentId },
				callSettings: context.callSettings,
				config: context.config,
				...context.callSettings,
				...context.config,
				...bodyValue ?? {}
			};
			let requestBody = sendCommandsBody;
			if (options.prepareSendCommandsRequest) requestBody = await options.prepareSendCommandsRequest(sendCommandsBody);
			if (resumeState !== void 0) {
				requestBody = {
					...requestBody,
					runId: resumeState.runId
				};
				delete requestBody["state"];
			}
			const response = await fetch(isResume ? options.resumeApi : options.api, {
				method: "POST",
				headers,
				body: JSON.stringify(requestBody),
				signal
			});
			try {
				await options.onResponse?.(response);
			} catch (error) {
				response.body?.cancel().catch(() => {});
				throw error;
			}
			if (!response.ok) throw new Error(`Status ${response.status}: ${await response.text()}`);
			if (!response.body) throw new Error("Response body is null");
			if (resumeState !== void 0) {
				agentStateRef.current = resumeState.state;
				rerender((prev) => prev + 1);
			}
			const body = await createReplayBoundaryStream(response, {
				setReplaying: setIsReplaying,
				waitForRender: waitForReplayRender
			});
			const protocol = options.protocol ?? "data-stream";
			const strict = isResume ? false : options.strict ?? true;
			const decoder = protocol === "assistant-transport" ? new AssistantTransportDecoder({ strict }) : new DataStreamDecoder({ strict });
			let err;
			const stream = body.pipeThrough(decoder).pipeThrough(new AssistantMessageAccumulator({
				initialMessage: unstable_createInitialMessage({ unstable_state: agentStateRef.current ?? null }),
				throttle: isResume,
				strict,
				onError: (error_0) => {
					err = error_0;
				}
			}));
			let markedDelivered = false;
			for await (const chunk of asAsyncIterableStream(stream)) {
				if (chunk.metadata.unstable_state === agentStateRef.current) continue;
				if (!markedDelivered) {
					commandQueue.markDelivered();
					markedDelivered = true;
				}
				agentStateRef.current = chunk.metadata.unstable_state;
				rerender((prev) => prev + 1);
			}
			if (err) throw new Error(err);
			if (!markedDelivered) commandQueue.markDelivered();
			if (isResume && commandQueue.state.queued.length > 0) runManager.schedule();
		},
		onFinish: options.onFinish,
		onCancel: () => {
			setIsReplaying(false);
			const cmds = [...commandQueue.state.inTransit, ...commandQueue.state.queued];
			commandQueue.reset();
			parentIdRef.current = void 0;
			options.onCancel?.({
				commands: cmds,
				updateState: (updater) => {
					agentStateRef.current = updater(agentStateRef.current);
					rerender((prev_0) => prev_0 + 1);
				}
			});
		},
		onError: async (error_1) => {
			resumeFlagRef.current = false;
			setIsReplaying(false);
			const inTransitCmds = [...commandQueue.state.inTransit];
			const queuedCmds = [...commandQueue.state.queued];
			commandQueue.reset();
			parentIdRef.current = void 0;
			try {
				await options.onError?.(error_1, {
					commands: inTransitCmds,
					updateState: (updater) => {
						agentStateRef.current = updater(agentStateRef.current);
						rerender((prev) => prev + 1);
					}
				});
			} finally {
				options.onCancel?.({
					commands: queuedCmds,
					updateState: (updater) => {
						agentStateRef.current = updater(agentStateRef.current);
						rerender((prev) => prev + 1);
					},
					error: error_1
				});
			}
		}
	});
	const [toolStatuses, setToolStatuses] = useState({});
	const pendingCommands = useMemo(() => [...commandQueue.state.inTransit, ...commandQueue.state.queued], [commandQueue.state]);
	const converted = useConvertedState(options.converter, agentStateRef.current, pendingCommands, runManager.isRunning, toolStatuses);
	const messages = useMemo(() => {
		const pendingIds = new Set(pendingCommands.flatMap((command_0) => command_0.type === "add-message" && command_0.message.role === "user" ? [command_0.message.id] : []));
		if (!converted.messages.some((message_0) => pendingIds.has(message_0.id))) return converted.messages;
		return converted.messages.map((message_1) => pendingIds.has(message_1.id) ? {
			...message_1,
			metadata: {
				...message_1.metadata,
				isOptimistic: true
			}
		} : message_1);
	}, [converted.messages, pendingCommands]);
	const runtime = useExternalStoreRuntime({
		messages,
		state: converted.state,
		isRunning: converted.isRunning,
		isLoading: isReplaying,
		adapters: options.adapters,
		unstable_enableToolInvocations: true,
		setToolStatuses,
		extras: {
			[symbolAssistantTransportExtras]: true,
			sendCommand: (command_1) => {
				commandQueue.enqueue(command_1.type === "add-message" && command_1.message.role === "user" ? {
					...command_1,
					message: {
						...command_1.message,
						id: command_1.message.id ?? generateId()
					}
				} : command_1);
			},
			state: agentStateRef.current
		},
		onNew: async (message_2) => enqueueAppendMessage(message_2),
		...options.capabilities?.edit && { onEdit: async (message_3) => enqueueAppendMessage(message_3) },
		...commandQueue.state.queued.length > 0 && { onReload: async (parentId_0) => {
			parentIdRef.current = parentId_0;
			runManager.schedule();
		} },
		onCancel: async () => {
			resumeFlagRef.current = false;
			runManager.cancel();
		},
		onResume: async () => {
			if (!options.resumeApi) throw new Error("Must pass resumeApi to options to resume runs");
			resumeFlagRef.current = true;
			runManager.schedule();
		},
		onAddToolResult: async (toolOptions) => {
			const command_2 = {
				type: "add-tool-result",
				toolCallId: toolOptions.toolCallId,
				result: toolOptions.result,
				toolName: toolOptions.toolName,
				isError: toolOptions.isError,
				...toolOptions.artifact !== void 0 && { artifact: toolOptions.artifact },
				...toolOptions.modelContent !== void 0 && { modelContent: toolOptions.modelContent }
			};
			commandQueue.enqueue(command_2);
		},
		onLoadExternalState: async (state) => {
			agentStateRef.current = state;
			rerender((prev_1) => prev_1 + 1);
		}
	});
	return runtime;
};
/**
* @alpha This is an experimental API that is subject to change.
*/
const useAssistantTransportRuntime = (options) => {
	const adapter = useCloudThreadListAdapter({ cloud: options.cloud });
	return useRemoteThreadListRuntime({
		runtimeHook: function RuntimeHook() {
			return useAssistantTransportThreadRuntime(options);
		},
		adapter,
		allowNesting: true
	});
};
//#endregion
export { useAssistantTransportRuntime, useAssistantTransportSendCommand, useAssistantTransportState };
