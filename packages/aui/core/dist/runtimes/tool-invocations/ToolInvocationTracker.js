import { isJSONValueEqual } from "../../utils/json/is-json-equal.js";
import { walkToolCallTree } from "../../runtime/utils/tool-call-tree.js";
import { ToolResponse, createAssistantStreamController, unstable_toolResultStream } from "assistant-stream";
import { AssistantMetaTransformStream } from "assistant-stream/utils";
//#region src/runtimes/tool-invocations/ToolInvocationTracker.ts
const TOOL_EXECUTION_ID = Symbol.for("assistant-stream.tool-execution-id");
const isArgsTextComplete = (argsText) => {
	try {
		JSON.parse(argsText);
		return true;
	} catch {
		return false;
	}
};
const parseArgsText = (argsText) => {
	try {
		return JSON.parse(argsText);
	} catch {
		return;
	}
};
const isEquivalentCompleteArgsText = (previous, next) => {
	const previousValue = parseArgsText(previous);
	const nextValue = parseArgsText(next);
	if (previousValue === void 0 || nextValue === void 0) return false;
	return isJSONValueEqual(previousValue, nextValue);
};
const hasFinalResult = (part) => part.result !== void 0 && part.isPreliminary !== true;
const getToolExecutionId = (value) => value[TOOL_EXECUTION_ID];
/**
* Plain-class port of the former `useToolInvocations` React hook. Owns the
* assistant-stream pipeline that drives client-side `streamCall` / `execute`
* for tool-call parts surfaced by a thread runtime, plus the per-tool-call
* status map that consumers render against.
*
* **Contract**: `streamCall` (and `execute`) fires exactly once per logical
* `toolCallId`. Args mutations after first completion, result replacement,
* and result clearing are *not* surfaced through additional `streamCall`
* invocations — by design — so hosts cannot observe spurious re-fires of
* side effects. The follow-up `reader.events()` API will expose those
* post-completion transitions to consumers that opt in.
*
* State-transition safety: every public method that observes runtime state
* (`setState`, `reset`, `abort`, `resume`) wraps its work in try/catch and
* logs to `console.error` rather than throwing. The tracker is built into
* the hot message-processing path, so a malformed snapshot must never crash
* the host runtime. See ./EDGE_CASES.md for the known non-trivial state
* transitions and what each does today.
*
* @deprecated Internal — for framework bindings; not a public API. May change without notice.
*/
var ToolInvocationTracker = class {
	_getTools;
	_callbacks;
	_isClientToolCall;
	_entries = /* @__PURE__ */ new Map();
	_humanInput = /* @__PURE__ */ new Map();
	_executing = /* @__PURE__ */ new Set();
	/**
	* Tool calls whose turn ended before they reached the executor. Held here
	* rather than on the entry because an entry is rebuilt whenever a snapshot
	* re-creates the call, and this is the one reason to skip that no later
	* snapshot carries.
	*/
	_discardedToolCallIds = /* @__PURE__ */ new Set();
	_settledResolvers = [];
	_statuses = /* @__PURE__ */ new Map();
	_ac = new AbortController();
	_pendingRestore = true;
	/** Cached last snapshot, used to skip processing on identical re-renders. */
	_lastSnapshot = null;
	_isRunning = false;
	_controller;
	/**
	* Set when the assistant-stream pipeline has died (errored out via
	* `.pipeTo(...).catch(...)`). The next `setState` re-initializes the
	* pipeline and demotes each active entry that reached the executor to
	* restored, so it survives the restart without re-firing `streamCall`.
	* A restart is an execution boundary like `reset()`: an entry that had
	* not reached it starts over and fires once there (F.4). Capped at a
	* single auto-restart per session — repeated failures keep the tracker
	* dead with a more visible error.
	*/
	_pipelineDead = false;
	_pipelineRestartUsed = false;
	constructor(getTools, callbacks, isClientToolCall) {
		this._getTools = getTools;
		this._callbacks = callbacks;
		this._isClientToolCall = isClientToolCall;
		this._initPipeline();
	}
	/**
	* Build the assistant-stream pipeline. Called once from the constructor
	* and at most once again if `_pipelineDead` is set (see F.4 in
	* EDGE_CASES.md).
	*/
	_initPipeline() {
		const [stream, controller] = createAssistantStreamController();
		this._controller = controller;
		const human = (toolCallId, payload, executionId) => this._onHumanInput(toolCallId, payload, executionId);
		const transform = unstable_toolResultStream(() => this._getWrappedTools(), () => this._ac.signal, human, {
			onExecutionStart: (id, _name, executionId) => this._onExecutionStart(id, executionId),
			onExecutionEnd: (id, _name, executionId) => this._onExecutionEnd(id, executionId)
		});
		stream.pipeThrough(transform).pipeThrough(new AssistantMetaTransformStream()).pipeTo(new WritableStream({ write: (chunk) => {
			try {
				if (chunk.type !== "result") return;
				this._handleResultChunk(chunk);
			} catch (err) {
				console.error("[ToolInvocationTracker] result chunk handling failed", err);
			}
		} })).catch((err) => {
			console.error("[ToolInvocationTracker] stream pipeline failed; will attempt single restart on next setState", err);
			this._pipelineDead = true;
		});
	}
	/**
	* Feed the next observed snapshot into the tracker. Called from the host
	* runtime whenever its message list / running state changes.
	*/
	setState(snapshot) {
		try {
			if (this._pipelineDead) {
				if (this._pipelineRestartUsed) return;
				this._pipelineRestartUsed = true;
				this._pipelineDead = false;
				this._demoteEntriesToRestored();
				this._executing.clear();
				this._ac = new AbortController();
				this._initPipeline();
			}
			if (this._lastSnapshot && this._lastSnapshot.messages === snapshot.messages && this._lastSnapshot.isRunning === snapshot.isRunning && this._lastSnapshot.isLoading === snapshot.isLoading) return;
			if (snapshot.isLoading === true) this._pendingRestore = true;
			const previousIsRunning = this._isRunning;
			this._isRunning = snapshot.isRunning;
			try {
				this._processMessages(snapshot.messages);
			} catch (err) {
				this._isRunning = previousIsRunning;
				throw err;
			}
			this._lastSnapshot = snapshot;
			this._pendingRestore = false;
		} catch (err) {
			console.error("[ToolInvocationTracker] setState failed; snapshot dropped", err);
		}
	}
	/**
	* Reset the tracker so the next observed snapshot is treated as historical.
	* Clears entries and aborts any in-flight executions. Used by callers like
	* `importExternalState` to mark a freshly loaded state as restored.
	*/
	reset() {
		try {
			this._pendingRestore = true;
			this._entries.clear();
			this._discardedToolCallIds.clear();
			this._lastSnapshot = null;
			this.abort();
			if (this._statuses.size > 0) {
				this._statuses = /* @__PURE__ */ new Map();
				this._invokeOnStatusesChange();
			}
		} catch (err) {
			console.error("[ToolInvocationTracker] reset failed", err);
		}
	}
	/**
	* Abort any in-flight `execute()` invocations. Resolves once all of them
	* have settled (or immediately if none are running).
	*
	* `discardPending` additionally kills the calls that never reached the
	* executor, for a caller ending the turn rather than interrupting it. The
	* signal cannot reach those: they are waiting on the run to settle (A.10),
	* and the settled snapshot arrives after this installs a fresh controller.
	*/
	abort(options) {
		try {
			this._humanInput.forEach(({ executionId, reject }, toolCallId) => {
				try {
					reject(/* @__PURE__ */ new Error("Tool execution aborted"));
				} catch {}
				this._endHumanRequest(toolCallId, executionId);
			});
			this._humanInput.clear();
			if (options?.discardPending) for (const [toolCallId, entry] of this._entries) {
				if (!entry.controller) continue;
				if (entry.argsComplete || entry.hasResult) continue;
				this._discardedToolCallIds.add(toolCallId);
				entry.skipExecute = true;
			}
			this._ac.abort();
			this._ac = new AbortController();
			if (this._executing.size === 0) return Promise.resolve();
			const executionIds = new Set(this._executing);
			return new Promise((resolve) => {
				this._settledResolvers.push({
					executionIds,
					resolve
				});
			});
		} catch (err) {
			console.error("[ToolInvocationTracker] abort failed", err);
			return Promise.resolve();
		}
	}
	_endHumanRequest(toolCallId, executionId) {
		if (this._executing.has(executionId)) {
			this._setStatus(toolCallId, { type: "executing" });
			return;
		}
		const owner = this._entries.get(toolCallId)?.executionId;
		if (owner === void 0 || owner === executionId) this._deleteStatus(toolCallId);
	}
	/**
	* Resolve a pending human-input request for the given tool call. Returns
	* `true` if a pending request was resumed, `false` if the tracker has no
	* outstanding request for that id (the caller should fall back to its own
	* dispatch path).
	*/
	resume(toolCallId, payload) {
		try {
			const handlers = this._humanInput.get(toolCallId);
			if (!handlers) return false;
			this._humanInput.delete(toolCallId);
			this._endHumanRequest(toolCallId, handlers.executionId);
			handlers.resolve(payload);
			return true;
		} catch (err) {
			console.error("[ToolInvocationTracker] resume failed", err);
			return false;
		}
	}
	/**
	* Returns the current tool execution status map. The returned `Map` is
	* the tracker's internal store — do not mutate it. Treat the reference
	* as a snapshot that may be replaced wholesale on the next status
	* transition.
	*/
	getStatuses() {
		return this._statuses;
	}
	_getWrappedTools() {
		const tools = this._getTools();
		if (!tools) return void 0;
		return Object.fromEntries(Object.entries(tools).map(([name, tool]) => {
			const execute = tool.execute;
			const streamCall = tool.streamCall;
			if (execute === void 0 && streamCall === void 0) return [name, tool];
			return [name, {
				...tool,
				...execute !== void 0 && { execute: (...[args, context]) => {
					const executionId = getToolExecutionId(context);
					const entry = this._captureExecution(context.toolCallId, executionId);
					if (!entry || entry.skipExecute) return new Promise(() => {});
					return execute(args, context);
				} },
				...streamCall !== void 0 && { streamCall: (...[reader, context]) => {
					const executionId = getToolExecutionId(context);
					if (!this._captureExecution(context.toolCallId, executionId)) return;
					return streamCall(reader, context);
				} }
			}];
		}));
	}
	_captureExecution(toolCallId, executionId) {
		if (executionId === void 0) return void 0;
		const entry = this._entries.get(toolCallId);
		if (!entry?.controller) return void 0;
		if (entry.executionId === void 0) entry.executionId = executionId;
		return entry.executionId === executionId ? entry : void 0;
	}
	_onHumanInput(toolCallId, payload, executionId) {
		return new Promise((resolve, reject) => {
			const entry = this._entries.get(toolCallId);
			if (!entry?.controller || entry.executionId !== executionId) {
				reject(/* @__PURE__ */ new Error("Tool execution aborted"));
				return;
			}
			const previous = this._humanInput.get(toolCallId);
			if (previous) try {
				previous.reject(/* @__PURE__ */ new Error("Human input request was superseded by a new request"));
			} catch {}
			this._humanInput.set(toolCallId, {
				executionId,
				resolve,
				reject
			});
			this._setStatus(toolCallId, {
				type: "interrupt",
				payload: {
					type: "human",
					payload
				}
			});
		});
	}
	_onExecutionStart(toolCallId, executionId) {
		if (!this._captureExecution(toolCallId, executionId)) return;
		if (this._entries.get(toolCallId).skipExecute) return;
		this._executing.add(executionId);
		if (this._humanInput.get(toolCallId)?.executionId === executionId) return;
		this._setStatus(toolCallId, { type: "executing" });
	}
	_onExecutionEnd(toolCallId, executionId) {
		if (executionId === void 0 || !this._executing.delete(executionId)) return;
		if (this._entries.get(toolCallId)?.executionId === executionId) this._deleteStatus(toolCallId);
		const pending = [];
		this._settledResolvers.forEach(({ executionIds, resolve }) => {
			if ([...executionIds].some((id) => this._executing.has(id))) {
				pending.push({
					executionIds,
					resolve
				});
				return;
			}
			try {
				resolve();
			} catch {}
		});
		this._settledResolvers.length = 0;
		this._settledResolvers.push(...pending);
	}
	_handleResultChunk(chunk) {
		const toolCallId = chunk.meta.toolCallId;
		const executionId = getToolExecutionId(chunk);
		const entry = this._entries.get(toolCallId);
		if (!entry || entry.executionId !== executionId) return;
		if (entry?.hasResult) return;
		if (entry.skipExecute) return;
		this._invokeOnResult({
			type: "add-tool-result",
			toolCallId,
			toolName: chunk.meta.toolName,
			result: chunk.result,
			isError: chunk.isError,
			...chunk.artifact !== void 0 && { artifact: chunk.artifact },
			...chunk.modelContent !== void 0 && { modelContent: chunk.modelContent }
		});
	}
	_invokeOnResult(command) {
		try {
			this._callbacks.onResult(command);
		} catch (err) {
			console.error("[ToolInvocationTracker] onResult callback threw; result dropped", err);
		}
	}
	_invokeOnStatusesChange() {
		try {
			this._callbacks.onStatusesChange(this._statuses);
		} catch (err) {
			console.error("[ToolInvocationTracker] onStatusesChange callback threw; status change not propagated", err);
		}
	}
	_setStatus(toolCallId, status) {
		const next = new Map(this._statuses);
		next.set(toolCallId, status);
		this._statuses = next;
		this._invokeOnStatusesChange();
	}
	_deleteStatus(toolCallId) {
		if (!this._statuses.has(toolCallId)) return;
		const next = new Map(this._statuses);
		next.delete(toolCallId);
		this._statuses = next;
		this._invokeOnStatusesChange();
	}
	_warnProviderOwnedSkip(toolName, toolCallId) {
		if (process.env.NODE_ENV === "production") return;
		if (this._getTools()?.[toolName]?.execute === void 0) return;
		console.warn("[ToolInvocationTracker] the runtime reports this tool call as provider-owned, so the registered execute is skipped; the provider has to hand the call to the client for it to run (see EDGE_CASES.md A.9)", {
			toolCallId,
			toolName
		});
	}
	/**
	* Closing the args stream hands the call to the client executor, so it may
	* only happen once the provider can no longer speak about that call. The run
	* ending is the only universal signal for that; an adapter that reports the
	* call as client-owned has said it earlier, per call.
	*/
	_shouldCloseArgsStream({ argsText, hasResult, clientOwned }) {
		if (hasResult) return true;
		if (!isArgsTextComplete(argsText)) return false;
		return clientOwned || !this._isRunning;
	}
	_startActiveEntry(toolCallId, toolName, skipExecute, clientOwned) {
		const entry = {
			toolName,
			controller: this._controller.addToolCallPart({
				toolName,
				toolCallId
			}),
			argsText: "",
			hasResult: false,
			skipExecute,
			argsComplete: false,
			clientOwned
		};
		this._entries.set(toolCallId, entry);
		return entry;
	}
	/**
	* Demote every active entry back to the restored phase. Used by the
	* pipeline-restart path so that, after a fresh pipeline is built, the
	* next observed snapshot does not re-fire `streamCall` for tool calls
	* that already fired pre-death. Args / hasResult tracking is preserved
	* so signature comparisons still work.
	*/
	_demoteEntriesToRestored() {
		for (const [toolCallId, entry] of this._entries) {
			if (!entry.controller) continue;
			if (!entry.argsComplete && !entry.hasResult) {
				this._entries.delete(toolCallId);
				continue;
			}
			this._entries.set(toolCallId, {
				toolName: entry.toolName,
				argsText: entry.argsText,
				hasResult: entry.hasResult
			});
		}
	}
	_processArgsText(entry, content) {
		if (!entry.controller) return;
		const hasResult = content.result !== void 0;
		if (content.argsText !== entry.argsText) {
			let shouldWriteArgsText = true;
			if (entry.argsComplete) {
				if (isEquivalentCompleteArgsText(entry.argsText, content.argsText)) {
					entry.argsText = content.argsText;
					shouldWriteArgsText = false;
				} else {
					if (process.env.NODE_ENV !== "production") console.warn("[ToolInvocationTracker] argsText changed after first completion; not re-firing streamCall (see EDGE_CASES.md A.4)", {
						previous: entry.argsText,
						next: content.argsText,
						toolCallId: content.toolCallId
					});
					entry.argsText = content.argsText;
					shouldWriteArgsText = false;
				}
			} else if (!content.argsText.startsWith(entry.argsText)) {
				if (isArgsTextComplete(entry.argsText) && isArgsTextComplete(content.argsText) && isEquivalentCompleteArgsText(entry.argsText, content.argsText)) {
					const shouldClose = this._shouldCloseArgsStream({
						argsText: content.argsText,
						hasResult,
						clientOwned: entry.clientOwned
					});
					if (shouldClose) entry.controller.argsText.close();
					entry.argsText = content.argsText;
					entry.argsComplete = shouldClose;
					shouldWriteArgsText = false;
				} else {
					if (process.env.NODE_ENV !== "production") console.warn("[ToolInvocationTracker] argsText regressed mid-stream; not restarting (see EDGE_CASES.md A.2)", {
						previous: entry.argsText,
						next: content.argsText,
						toolCallId: content.toolCallId
					});
					shouldWriteArgsText = false;
				}
			}
			if (shouldWriteArgsText && entry.controller) {
				const delta = content.argsText.slice(entry.argsText.length);
				entry.controller.argsText.append(delta);
				const shouldClose = this._shouldCloseArgsStream({
					argsText: content.argsText,
					hasResult,
					clientOwned: entry.clientOwned
				});
				if (shouldClose) entry.controller.argsText.close();
				entry.argsText = content.argsText;
				entry.argsComplete = shouldClose;
			}
		}
		if (!entry.argsComplete && entry.controller) {
			if (this._shouldCloseArgsStream({
				argsText: entry.argsText,
				hasResult,
				clientOwned: entry.clientOwned
			})) {
				entry.controller.argsText.close();
				entry.argsComplete = true;
			}
		}
	}
	_processMessages(messages) {
		const isRestore = this._pendingRestore;
		for (const { part: content } of walkToolCallTree(messages)) {
			const existing = this._entries.get(content.toolCallId);
			if (isRestore) {
				if (!existing?.controller) this._entries.set(content.toolCallId, {
					toolName: content.toolName,
					argsText: content.argsText,
					hasResult: hasFinalResult(content)
				});
				continue;
			}
			let entry = existing;
			if (hasFinalResult(content)) this._discardedToolCallIds.delete(content.toolCallId);
			if (entry && !entry.controller) {
				if (entry.hasResult) continue;
				if (!(content.argsText !== entry.argsText && !(isArgsTextComplete(entry.argsText) && isArgsTextComplete(content.argsText) && isEquivalentCompleteArgsText(entry.argsText, content.argsText))) && !hasFinalResult(content)) continue;
				this._entries.delete(content.toolCallId);
				entry = void 0;
			}
			if (!entry) {
				const ownership = this._isClientToolCall?.(content);
				const providerOwned = content.result === void 0 && ownership === false;
				if (providerOwned) this._warnProviderOwnedSkip(content.toolName, content.toolCallId);
				entry = this._startActiveEntry(content.toolCallId, content.toolName, content.result !== void 0 || providerOwned || this._discardedToolCallIds.has(content.toolCallId), ownership === true);
			}
			if (content.result !== void 0) entry.skipExecute = true;
			if (content.approval !== void 0) entry.skipExecute = true;
			this._processArgsText(entry, content);
			if (content.result !== void 0 && !entry.hasResult) {
				const { controller: activeController } = entry;
				if (!activeController) continue;
				entry.argsComplete = true;
				activeController.setResponse(new ToolResponse({
					result: content.result,
					artifact: content.artifact,
					isError: content.isError,
					isPreliminary: content.isPreliminary,
					...content.modelContent !== void 0 ? { modelContent: content.modelContent } : {}
				}));
				if (hasFinalResult(content)) {
					entry.hasResult = true;
					activeController.close();
				}
			}
		}
	}
};
//#endregion
export { ToolInvocationTracker };
