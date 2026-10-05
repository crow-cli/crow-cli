import { runCleanups } from "../../subscribable/subscribable.js";
import { useSubscribable } from "./useSubscribable.js";
import { ComposerClient } from "./composer-runtime-client.js";
import { liveRef } from "./liveRef.js";
import { MessageClient } from "./message-runtime-client.js";
import { ThreadMessageClient } from "../clients/thread-message-client.js";
import { submissionThreadMessage } from "../clients/submission-message.js";
import { ThreadSuggestions } from "../clients/suggestions.js";
import { TaskClient, createTaskDeriver, getTaskKey } from "../clients/thread-tasks.js";
import { useAssistantEmit, useClientLookup, useClientResource } from "@assistant-ui/store/client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect } from "@assistant-ui/tap/react-shim";
import { resource, useResource, withKey } from "@assistant-ui/tap";
//#region src/store/runtime-clients/thread-runtime-client.ts
const useMessageClientById = (t0) => {
	const $ = c(8);
	const { runtime, id, threadIdRef, threadId, isLast } = t0;
	let t1;
	if ($[0] !== id || $[1] !== runtime) {
		t1 = runtime.getMessageById(id);
		$[0] = id;
		$[1] = runtime;
		$[2] = t1;
	} else t1 = $[2];
	const messageRuntime = t1;
	let t2;
	if ($[3] !== isLast || $[4] !== messageRuntime || $[5] !== threadId || $[6] !== threadIdRef) {
		t2 = MessageClient({
			runtime: messageRuntime,
			threadIdRef,
			threadId,
			isLast
		});
		$[3] = isLast;
		$[4] = messageRuntime;
		$[5] = threadId;
		$[6] = threadIdRef;
		$[7] = t2;
	} else t2 = $[7];
	return useResource(t2);
};
const MessageClientById = resource(useMessageClientById);
const useThreadClient = (t0) => {
	const $ = c(111);
	const { runtime } = t0;
	const runtimeState = useSubscribable(runtime);
	const emit = useAssistantEmit();
	let t1;
	let t2;
	if ($[0] !== emit || $[1] !== runtime) {
		t1 = () => {
			const unsubscribers = [];
			for (const event of [
				"runStart",
				"runEnd",
				"initialize",
				"modelContextUpdate"
			]) {
				const unsubscribe = runtime.unstable_on(event, () => {
					const threadId = runtime.getState()?.threadId || "unknown";
					emit(`thread.${event}`, { threadId });
				});
				unsubscribers.push(unsubscribe);
			}
			unsubscribers.push(runtime.unstable_on("historyWriteError", (payload) => {
				const threadId_0 = runtime.getState()?.threadId || "unknown";
				emit("thread.historyWriteError", {
					threadId: threadId_0,
					operation: payload.operation,
					messageIds: payload.messageIds,
					message: payload.message
				});
			}), runtime.unstable_on("toolApprovalAnswered", (payload_0) => {
				const threadId_1 = runtime.getState()?.threadId || "unknown";
				emit("thread.toolApprovalAnswered", {
					threadId: threadId_1,
					...payload_0
				});
			}));
			return () => runCleanups(unsubscribers);
		};
		t2 = [runtime, emit];
		$[0] = emit;
		$[1] = runtime;
		$[2] = t1;
		$[3] = t2;
	} else {
		t1 = $[2];
		t2 = $[3];
	}
	useEffect(t1, t2);
	let t3;
	if ($[4] !== runtime) {
		t3 = liveRef(() => runtime.getState().threadId);
		$[4] = runtime;
		$[5] = t3;
	} else t3 = $[5];
	const threadIdRef = t3;
	let t4;
	if ($[6] !== emit || $[7] !== runtime) {
		t4 = (event_0) => {
			emit(event_0, { threadId: runtime.getState().threadId });
		};
		$[6] = emit;
		$[7] = runtime;
		$[8] = t4;
	} else t4 = $[8];
	const emitThreadEvent = t4;
	let t5;
	if ($[9] !== runtime) {
		t5 = (text) => runtime.getState().suggestions.some((suggestion) => suggestion.prompt === text);
		$[9] = runtime;
		$[10] = t5;
	} else t5 = $[10];
	const isSuggestion = t5;
	let t6;
	if ($[11] !== isSuggestion || $[12] !== runtime.composer || $[13] !== threadIdRef) {
		t6 = ComposerClient({
			runtime: runtime.composer,
			threadIdRef,
			isSuggestion
		});
		$[11] = isSuggestion;
		$[12] = runtime.composer;
		$[13] = threadIdRef;
		$[14] = t6;
	} else t6 = $[14];
	const composer = useClientResource(t6);
	let t7;
	if ($[15] !== runtimeState.suggestions) {
		t7 = ThreadSuggestions(runtimeState.suggestions);
		$[15] = runtimeState.suggestions;
		$[16] = t7;
	} else t7 = $[16];
	const suggestions = useClientResource(t7);
	let t8;
	if ($[17] === Symbol.for("react.memo_cache_sentinel")) {
		t8 = createTaskDeriver();
		$[17] = t8;
	} else t8 = $[17];
	const taskDeriver = t8;
	let t9;
	if ($[18] !== runtimeState.messages) {
		t9 = taskDeriver(runtimeState.messages);
		$[18] = runtimeState.messages;
		$[19] = t9;
	} else t9 = $[19];
	const tasks = t9;
	let t10;
	if ($[20] !== tasks) {
		t10 = tasks.map(_temp);
		$[20] = tasks;
		$[21] = t10;
	} else t10 = $[21];
	const taskClients = useClientLookup(t10);
	const submission = composer.state.submission;
	const inTransit = composer.state.inTransit;
	let t11;
	if ($[22] !== inTransit) {
		t11 = inTransit ?? [];
		$[22] = inTransit;
		$[23] = t11;
	} else t11 = $[23];
	let t12;
	if ($[24] !== submission) {
		t12 = submission ? [submission] : [];
		$[24] = submission;
		$[25] = t12;
	} else t12 = $[25];
	let t13;
	if ($[26] !== t11 || $[27] !== t12) {
		t13 = [...t11, ...t12];
		$[26] = t11;
		$[27] = t12;
		$[28] = t13;
	} else t13 = $[28];
	const pending = t13;
	let t14;
	if ($[29] !== pending) {
		t14 = pending.map(submissionThreadMessage);
		$[29] = pending;
		$[30] = t14;
	} else t14 = $[30];
	const pendingMessages = t14;
	const lastIndex = runtimeState.messages.length - 1;
	let t15;
	if ($[31] !== lastIndex || $[32] !== pending || $[33] !== pendingMessages || $[34] !== runtime || $[35] !== runtimeState.messages || $[36] !== runtimeState.threadId || $[37] !== threadIdRef) {
		let t16;
		if ($[39] !== lastIndex || $[40] !== pending.length || $[41] !== runtime || $[42] !== runtimeState.threadId || $[43] !== threadIdRef) {
			t16 = (m, index) => {
				const isLast = index === lastIndex && pending.length > 0 ? false : void 0;
				return withKey(m.id, MessageClientById({
					runtime,
					id: m.id,
					threadIdRef,
					threadId: runtimeState.threadId,
					isLast
				}), [
					runtime,
					m.id,
					threadIdRef,
					runtimeState.threadId,
					isLast
				]);
			};
			$[39] = lastIndex;
			$[40] = pending.length;
			$[41] = runtime;
			$[42] = runtimeState.threadId;
			$[43] = threadIdRef;
			$[44] = t16;
		} else t16 = $[44];
		const t17 = runtimeState.messages.map(t16);
		let t18;
		if ($[45] !== pending || $[46] !== pendingMessages || $[47] !== runtimeState.messages.length) {
			t18 = pending.map((row, index_0) => withKey(row.id, ThreadMessageClient({
				message: pendingMessages[index_0],
				submission: row,
				index: runtimeState.messages.length + index_0,
				isLast: index_0 === pending.length - 1
			}), [
				pendingMessages[index_0],
				row,
				runtimeState.messages.length,
				index_0,
				pending.length
			]));
			$[45] = pending;
			$[46] = pendingMessages;
			$[47] = runtimeState.messages.length;
			$[48] = t18;
		} else t18 = $[48];
		t15 = [...t17, ...t18];
		$[31] = lastIndex;
		$[32] = pending;
		$[33] = pendingMessages;
		$[34] = runtime;
		$[35] = runtimeState.messages;
		$[36] = runtimeState.threadId;
		$[37] = threadIdRef;
		$[38] = t15;
	} else t15 = $[38];
	const messages = useClientLookup(t15);
	const t16 = messages.state.length === 0 && !runtimeState.isLoading;
	let t17;
	if ($[49] !== composer.state || $[50] !== messages.state || $[51] !== runtimeState.capabilities || $[52] !== runtimeState.extras || $[53] !== runtimeState.isDisabled || $[54] !== runtimeState.isLoading || $[55] !== runtimeState.isRunning || $[56] !== runtimeState.speech || $[57] !== runtimeState.state || $[58] !== runtimeState.suggestions || $[59] !== runtimeState.voice || $[60] !== t16 || $[61] !== tasks) {
		t17 = {
			isEmpty: t16,
			isDisabled: runtimeState.isDisabled,
			isLoading: runtimeState.isLoading,
			isRunning: runtimeState.isRunning,
			capabilities: runtimeState.capabilities,
			state: runtimeState.state,
			suggestions: runtimeState.suggestions,
			extras: runtimeState.extras,
			speech: runtimeState.speech,
			voice: runtimeState.voice,
			composer: composer.state,
			messages: messages.state,
			tasks
		};
		$[49] = composer.state;
		$[50] = messages.state;
		$[51] = runtimeState.capabilities;
		$[52] = runtimeState.extras;
		$[53] = runtimeState.isDisabled;
		$[54] = runtimeState.isLoading;
		$[55] = runtimeState.isRunning;
		$[56] = runtimeState.speech;
		$[57] = runtimeState.state;
		$[58] = runtimeState.suggestions;
		$[59] = runtimeState.voice;
		$[60] = t16;
		$[61] = tasks;
		$[62] = t17;
	} else t17 = $[62];
	const state = t17;
	let t18;
	if ($[63] !== state) {
		t18 = () => state;
		$[63] = state;
		$[64] = t18;
	} else t18 = $[64];
	let t19;
	if ($[65] !== composer.methods) {
		t19 = () => composer.methods;
		$[65] = composer.methods;
		$[66] = t19;
	} else t19 = $[66];
	let t20;
	if ($[67] !== suggestions) {
		t20 = () => suggestions.methods;
		$[67] = suggestions;
		$[68] = t20;
	} else t20 = $[68];
	let t21;
	if ($[69] !== taskClients || $[70] !== tasks) {
		t21 = (selector) => {
			if ("id" in selector) {
				const task_0 = tasks.find((candidate) => candidate.id === selector.id);
				return taskClients.get({ key: task_0 ? getTaskKey(task_0) : selector.id });
			}
			return taskClients.get(selector);
		};
		$[69] = taskClients;
		$[70] = tasks;
		$[71] = t21;
	} else t21 = $[71];
	let t22;
	if ($[72] !== emit || $[73] !== isSuggestion || $[74] !== runtime) {
		t22 = (message) => {
			const appended = typeof message === "string" ? { content: [{
				type: "text",
				text: message
			}] } : message;
			if ((appended.role ?? "user") === "user") {
				const text_0 = appended.content.map(_temp2).join("");
				emit("composer.send", {
					threadId: runtime.getState().threadId,
					chars: text_0.length,
					attachments: appended.attachments?.length ?? 0,
					...isSuggestion(text_0) ? { suggestion: true } : void 0
				});
			}
			runtime.append(message);
		};
		$[72] = emit;
		$[73] = isSuggestion;
		$[74] = runtime;
		$[75] = t22;
	} else t22 = $[75];
	let t23;
	if ($[76] !== emitThreadEvent || $[77] !== runtime || $[78] !== runtimeState.isRunning) {
		t23 = () => {
			if (runtimeState.isRunning) emitThreadEvent("thread.cancelRun");
			runtime.cancelRun();
		};
		$[76] = emitThreadEvent;
		$[77] = runtime;
		$[78] = runtimeState.isRunning;
		$[79] = t23;
	} else t23 = $[79];
	let t24;
	if ($[80] !== emitThreadEvent || $[81] !== runtime) {
		t24 = () => {
			runtime.connectVoice();
			emitThreadEvent("thread.voiceStarted");
		};
		$[80] = emitThreadEvent;
		$[81] = runtime;
		$[82] = t24;
	} else t24 = $[82];
	let t25;
	if ($[83] !== messages) {
		t25 = (selector_0) => {
			if ("id" in selector_0) return messages.get({ key: selector_0.id });
			else return messages.get(selector_0);
		};
		$[83] = messages;
		$[84] = t25;
	} else t25 = $[84];
	let t26;
	if ($[85] !== runtime) {
		t26 = () => runtime;
		$[85] = runtime;
		$[86] = t26;
	} else t26 = $[86];
	let t27;
	if ($[87] !== runtime.deleteMessage || $[88] !== runtime.disconnectVoice || $[89] !== runtime.export || $[90] !== runtime.getModelContext || $[91] !== runtime.getVoiceVolume || $[92] !== runtime.import || $[93] !== runtime.importExternalState || $[94] !== runtime.muteVoice || $[95] !== runtime.reset || $[96] !== runtime.resumeRun || $[97] !== runtime.startRun || $[98] !== runtime.stopSpeaking || $[99] !== runtime.subscribeVoiceVolume || $[100] !== runtime.unmuteVoice || $[101] !== t18 || $[102] !== t19 || $[103] !== t20 || $[104] !== t21 || $[105] !== t22 || $[106] !== t23 || $[107] !== t24 || $[108] !== t25 || $[109] !== t26) {
		t27 = {
			getState: t18,
			composer: t19,
			suggestions: t20,
			task: t21,
			append: t22,
			deleteMessage: runtime.deleteMessage,
			startRun: runtime.startRun,
			resumeRun: runtime.resumeRun,
			importExternalState: runtime.importExternalState,
			cancelRun: t23,
			getModelContext: runtime.getModelContext,
			export: runtime.export,
			import: runtime.import,
			reset: runtime.reset,
			stopSpeaking: runtime.stopSpeaking,
			connectVoice: t24,
			disconnectVoice: runtime.disconnectVoice,
			getVoiceVolume: runtime.getVoiceVolume,
			subscribeVoiceVolume: runtime.subscribeVoiceVolume,
			muteVoice: runtime.muteVoice,
			unmuteVoice: runtime.unmuteVoice,
			message: t25,
			__internal_getRuntime: t26
		};
		$[87] = runtime.deleteMessage;
		$[88] = runtime.disconnectVoice;
		$[89] = runtime.export;
		$[90] = runtime.getModelContext;
		$[91] = runtime.getVoiceVolume;
		$[92] = runtime.import;
		$[93] = runtime.importExternalState;
		$[94] = runtime.muteVoice;
		$[95] = runtime.reset;
		$[96] = runtime.resumeRun;
		$[97] = runtime.startRun;
		$[98] = runtime.stopSpeaking;
		$[99] = runtime.subscribeVoiceVolume;
		$[100] = runtime.unmuteVoice;
		$[101] = t18;
		$[102] = t19;
		$[103] = t20;
		$[104] = t21;
		$[105] = t22;
		$[106] = t23;
		$[107] = t24;
		$[108] = t25;
		$[109] = t26;
		$[110] = t27;
	} else t27 = $[110];
	return t27;
};
const ThreadClient = resource(useThreadClient);
function _temp(task) {
	return withKey(getTaskKey(task), TaskClient({ task }), [task]);
}
function _temp2(part) {
	return part.type === "text" ? part.text : "";
}
//#endregion
export { ThreadClient };
