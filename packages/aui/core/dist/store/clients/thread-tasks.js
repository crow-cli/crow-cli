import { COMPLETE_STATUS, toMessagePartStatus } from "../../utils/normalizePartStatus.js";
import { resource } from "@assistant-ui/tap";
//#region src/store/clients/thread-tasks.ts
const getStatusReason = (status) => "reason" in status ? status.reason : void 0;
const getStatusError = (status) => "error" in status ? status.error : void 0;
const MAX_TASK_DEPTH = 32;
const taskKeys = /* @__PURE__ */ new WeakMap();
/** Lookup key for a task client: its document-order index path, unique by construction where ids from nested payloads are not. */
const getTaskKey = (task) => taskKeys.get(task) ?? task.id;
const resolveStatus = (message, partIndex, part) => "status" in message && message.status ? toMessagePartStatus(message, partIndex, part) : COMPLETE_STATUS;
const createTaskDeriver = () => {
	let previous = [];
	let previousEntries = /* @__PURE__ */ new Map();
	return (messages) => {
		const tasks = [];
		const entries = /* @__PURE__ */ new Map();
		let allEntriesReused = true;
		const visit = (threadMessages, parentTaskId, depth, path) => {
			if (depth > MAX_TASK_DEPTH) return;
			for (const [messageIndex, message] of threadMessages.entries()) for (const [partIndex, part] of message.content.entries()) {
				if (part.type !== "tool-call" || part.messages === void 0) continue;
				const nestedMessages = part.messages;
				const status = resolveStatus(message, partIndex, part);
				const statusReason = getStatusReason(status);
				const statusError = getStatusError(status);
				const entryKey = `${path}${messageIndex}.${partIndex}`;
				const previousEntry = previousEntries.get(entryKey);
				const task = previousEntry?.part === part && previousEntry.statusType === status.type && previousEntry.statusReason === statusReason && Object.is(previousEntry.statusError, statusError) && previousEntry.messages === nestedMessages && previousEntry.task.messageId === message.id && previousEntry.task.parentTaskId === parentTaskId && previousEntry.task.depth === depth ? previousEntry.task : {
					id: part.toolCallId,
					toolName: part.toolName,
					args: part.args,
					result: part.result,
					...part.isError === void 0 ? void 0 : { isError: part.isError },
					status,
					timing: part.timing,
					messageId: message.id,
					parentTaskId,
					depth,
					messages: nestedMessages
				};
				if (task !== previousEntry?.task) {
					allEntriesReused = false;
					taskKeys.set(task, entryKey);
				}
				tasks.push(task);
				entries.set(entryKey, {
					task,
					part,
					statusType: status.type,
					statusReason,
					statusError,
					messages: nestedMessages
				});
				visit(nestedMessages, task.id, depth + 1, `${entryKey}.`);
			}
		};
		visit(messages, null, 0, "");
		const result = allEntriesReused && tasks.length === previous.length && tasks.every((task, index) => task === previous[index]) ? previous : tasks;
		previous = result;
		previousEntries = entries;
		return result;
	};
};
const useTaskClient = ({ task }) => ({ getState: () => task });
const TaskClient = resource(useTaskClient);
//#endregion
export { TaskClient, createTaskDeriver, getTaskKey };
