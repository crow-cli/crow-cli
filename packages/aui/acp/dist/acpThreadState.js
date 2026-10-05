import { applySessionUpdateToContent, attachToolCallApproval, permissionOptionToApprovalOption, resolveToolCallApproval, userPartsFromBlock } from "./conversions.js";
//#region src/acpThreadState.ts
const EMPTY_ACP_THREAD_STATE = {
	loadState: { type: "idle" },
	connectionState: "disconnected",
	sessionId: void 0,
	agentInfo: void 0,
	agentCapabilities: void 0,
	messageOrder: [],
	messagesById: {},
	headId: null,
	run: { type: "idle" },
	replay: { type: "idle" },
	permissions: {},
	plan: void 0,
	sessionTitle: void 0,
	currentModeId: void 0,
	availableCommands: void 0,
	configOptions: void 0,
	usage: void 0,
	toolCallStatuses: {}
};
const createAcpThreadState = () => EMPTY_ACP_THREAD_STATE;
const isAcpStateRunning = (state) => state.run.type === "running";
const withMessage = (state, message, headId = message.id) => ({
	...state,
	messageOrder: state.messagesById[message.id] ? state.messageOrder : [...state.messageOrder, message.id],
	messagesById: {
		...state.messagesById,
		[message.id]: message
	},
	headId
});
const runningAssistant = (state) => {
	if (state.run.type !== "running") return void 0;
	const message = state.messagesById[state.run.assistantId];
	return message?.role === "assistant" ? message : void 0;
};
/** A replayed turn ended before this process saw it: complete, reason unknown. */
const REPLAY_MESSAGE_STATUS = {
	type: "complete",
	reason: "unknown"
};
const replayId = (seq) => `acp-replay-${seq}`;
/** The message at the tip of the transcript, when it has the wanted role. */
const headMessage = (state, role) => {
	if (state.headId === null) return void 0;
	const head = state.messagesById[state.headId];
	return head?.role === role ? head : void 0;
};
const appendUserParts = (content, parts) => {
	const last = content[content.length - 1];
	const first = parts[0];
	if (parts.length === 1 && last?.type === "text" && first?.type === "text") return [...content.slice(0, -1), {
		...last,
		text: last.text + first.text
	}];
	return [...content, ...parts];
};
/**
* The message an incoming `session/update` belongs to: the run's assistant
* while a turn is live, the transcript tip during a replay. Outside both there
* is nothing to write into and the update is dropped — a chunk that arrives
* after `run-end` is a late duplicate, not a reason to reopen a finished
* message, and an agent streaming into a session nobody is running or loading
* has no client-side target.
*/
const activeAssistant = (state) => {
	if (state.run.type === "running") return runningAssistant(state);
	if (state.replay.type !== "active") return void 0;
	return headMessage(state, "assistant");
};
/**
* The assistant message a replayed update lands in, minting one when the
* transcript tip is a user turn (or empty). History alternates, so a role
* change at the tip is the boundary between two replayed messages — the same
* rule the agent's own emitter follows when it starts a new message.
*/
const ensureReplayAssistant = (state) => {
	if (state.replay.type !== "active") return state;
	if (headMessage(state, "assistant")) return state;
	const message = {
		role: "assistant",
		id: replayId(state.replay.seq),
		parentId: state.headId,
		createdAt: Date.now(),
		status: REPLAY_MESSAGE_STATUS,
		content: []
	};
	return {
		...withMessage(state, message),
		replay: {
			type: "active",
			seq: state.replay.seq + 1
		}
	};
};
const patchAssistant = (state, patch) => {
	const message = activeAssistant(state);
	if (!message) return state;
	const next = patch(message);
	if (!next || next === message) return state;
	return {
		...state,
		messagesById: {
			...state.messagesById,
			[message.id]: next
		}
	};
};
const cancelPermissions = (state) => {
	const approvalIds = Object.keys(state.permissions);
	if (approvalIds.length === 0) return state;
	let next = state;
	for (const approvalId of approvalIds) next = patchAssistantAt(next, approvalId, (message) => ({
		...message,
		content: resolveToolCallApproval(message.content, approvalId, { resolution: "cancelled" })
	}));
	return {
		...next,
		permissions: {}
	};
};
const patchAssistantAt = (state, approvalId, patch) => {
	const approval = state.permissions[approvalId];
	if (!approval) return state;
	for (const id of state.messageOrder) {
		const message = state.messagesById[id];
		if (message?.role !== "assistant") continue;
		const next = patch(message, approval);
		if (!next || next === message) continue;
		return {
			...state,
			messagesById: {
				...state.messagesById,
				[id]: next
			}
		};
	}
	return state;
};
const reduceSessionUpdate = (state, update) => {
	switch (update.sessionUpdate) {
		case "plan": return state.plan === update.entries ? state : {
			...state,
			plan: update.entries
		};
		case "session_info_update": {
			if (update.title === void 0) return state;
			const title = update.title ?? void 0;
			return state.sessionTitle === title ? state : {
				...state,
				sessionTitle: title
			};
		}
		case "current_mode_update": return state.currentModeId === update.currentModeId ? state : {
			...state,
			currentModeId: update.currentModeId
		};
		case "available_commands_update": return state.availableCommands === update.availableCommands ? state : {
			...state,
			availableCommands: update.availableCommands
		};
		case "config_option_update": return state.configOptions === update.configOptions ? state : {
			...state,
			configOptions: update.configOptions
		};
		case "usage_update": {
			const usage = {
				used: update.used,
				size: update.size,
				cost: update.cost ?? null
			};
			return {
				...state,
				usage
			};
		}
		case "user_message_chunk": {
			if (state.replay.type !== "active") return state;
			const parts = userPartsFromBlock(update.content);
			if (parts.length === 0) return state;
			const existing = headMessage(state, "user");
			if (existing) return {
				...state,
				messagesById: {
					...state.messagesById,
					[existing.id]: {
						...existing,
						content: appendUserParts(existing.content, parts)
					}
				}
			};
			const message = {
				role: "user",
				id: replayId(state.replay.seq),
				parentId: state.headId,
				createdAt: Date.now(),
				content: parts,
				attachments: []
			};
			return {
				...withMessage(state, message),
				replay: {
					type: "active",
					seq: state.replay.seq + 1
				}
			};
		}
		default: {
			const toolCall = update;
			const toolCallId = typeof toolCall.toolCallId === "string" ? toolCall.toolCallId : void 0;
			const knownStatus = toolCallId === void 0 ? void 0 : state.toolCallStatuses[toolCallId];
			const next = patchAssistant(ensureReplayAssistant(state), (message) => {
				const content = applySessionUpdateToContent(message.content, toolCall, knownStatus);
				return content === void 0 ? void 0 : {
					...message,
					content
				};
			});
			const reportedStatus = toolCall.status ?? void 0;
			if (toolCallId === void 0 || reportedStatus === void 0) return next;
			return next.toolCallStatuses[toolCallId] === reportedStatus ? next : {
				...next,
				toolCallStatuses: {
					...next.toolCallStatuses,
					[toolCallId]: reportedStatus
				}
			};
		}
	}
};
const reduceAcpThreadState = (state, event) => {
	switch (event.type) {
		case "load-start": return state.loadState.type === "loading" ? state : {
			...state,
			loadState: { type: "loading" }
		};
		case "load-ready": return state.loadState.type === "loading" ? {
			...state,
			loadState: { type: "ready" }
		} : state;
		case "load-error": return {
			...state,
			loadState: {
				type: "error",
				error: event.error
			}
		};
		case "connection": return {
			...state,
			connectionState: event.connectionState,
			sessionId: event.sessionId,
			...event.agentInfo !== void 0 && { agentInfo: event.agentInfo },
			...event.agentCapabilities !== void 0 && { agentCapabilities: event.agentCapabilities },
			...event.sessionModes !== void 0 && { currentModeId: event.sessionModes.currentModeId },
			...event.sessionConfigOptions !== void 0 && { configOptions: event.sessionConfigOptions }
		};
		case "append-message": return withMessage(state, event.message);
		case "replace-messages": {
			const messagesById = {};
			const messageOrder = [];
			for (const message of event.messages) {
				messagesById[message.id] = message;
				messageOrder.push(message.id);
			}
			return {
				...state,
				messagesById,
				messageOrder,
				headId: event.headId,
				run: { type: "idle" },
				replay: { type: "idle" },
				permissions: {},
				toolCallStatuses: {}
			};
		}
		case "run-start": return {
			...withMessage(state, event.message),
			run: {
				type: "running",
				assistantId: event.message.id
			},
			replay: { type: "idle" },
			toolCallStatuses: {}
		};
		case "replay-start": return state.replay.type === "active" ? state : {
			...state,
			replay: {
				type: "active",
				seq: 0
			}
		};
		case "replay-end": return state.replay.type === "active" ? {
			...state,
			replay: { type: "idle" }
		} : state;
		case "session-update": return reduceSessionUpdate(state, event.update);
		case "permission-request": {
			const toolCallId = event.request.toolCall.toolCallId;
			const approval = {
				id: event.approvalId,
				options: event.request.options.map(permissionOptionToApprovalOption)
			};
			const next = patchAssistant(state, (message) => ({
				...message,
				status: {
					type: "requires-action",
					reason: "tool-calls"
				},
				content: attachToolCallApproval(message.content, event.request.toolCall, approval)
			}));
			return {
				...next,
				permissions: {
					...next.permissions,
					[event.approvalId]: {
						approvalId: event.approvalId,
						toolCallId,
						options: approval.options
					}
				}
			};
		}
		case "permission-resolved": {
			const next = patchAssistantAt(state, event.approvalId, (message) => ({
				...message,
				status: { type: "running" },
				content: resolveToolCallApproval(message.content, event.approvalId, {
					approved: event.approved,
					...event.optionId !== void 0 && { optionId: event.optionId },
					...event.cancelled && { resolution: "cancelled" }
				})
			}));
			const { [event.approvalId]: _removed, ...remaining } = next.permissions;
			return {
				...next,
				permissions: remaining
			};
		}
		case "permissions-cancelled": {
			const next = cancelPermissions(state);
			const assistant = runningAssistant(next);
			if (!assistant || assistant.status.type !== "requires-action") return next;
			return patchAssistant(next, (message) => ({
				...message,
				status: { type: "running" }
			}));
		}
		case "reset-thread": return {
			...state,
			messageOrder: [],
			messagesById: {},
			headId: null,
			run: { type: "idle" },
			replay: { type: "idle" },
			permissions: {},
			plan: void 0,
			sessionTitle: void 0,
			currentModeId: void 0,
			availableCommands: void 0,
			configOptions: void 0,
			usage: void 0,
			toolCallStatuses: {}
		};
		case "run-end": {
			const next = cancelPermissions(state);
			const assistant = runningAssistant(next);
			if (!assistant) return {
				...next,
				run: { type: "idle" }
			};
			return {
				...next,
				messagesById: {
					...next.messagesById,
					[assistant.id]: {
						...assistant,
						status: event.status
					}
				},
				run: { type: "idle" }
			};
		}
		case "run-handoff": {
			const settled = cancelPermissions(state);
			const previous = runningAssistant(settled);
			const messagesById = previous ? {
				...settled.messagesById,
				[previous.id]: {
					...previous,
					status: event.status
				}
			} : settled.messagesById;
			return {
				...withMessage({
					...settled,
					messagesById
				}, event.message),
				run: {
					type: "running",
					assistantId: event.message.id
				},
				replay: { type: "idle" },
				toolCallStatuses: {}
			};
		}
		default: return state;
	}
};
//#endregion
export { EMPTY_ACP_THREAD_STATE, createAcpThreadState, isAcpStateRunning, reduceAcpThreadState };
