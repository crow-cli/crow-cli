"use client";
import { interactableToolName, unstable_getInteractableVersions } from "../../model-context/interactable-composer-metadata.js";
import { useJSONEqual } from "../utils/useJSONEqual.js";
import { useJSONSchemaDependency } from "../utils/useJSONSchemaDependency.js";
import { unstable_useInteractableState } from "./useInteractableState.js";
import { useEffect, useId, useMemo, useRef } from "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/react/model-context/useInteractable.ts
const useInteractable = (name, config) => {
	const aui = useAui();
	const autoId = useId().replace(/[^a-zA-Z0-9]/g, "");
	const updateToolName = interactableToolName(name);
	const part = useAuiState((s) => {
		const p = s.optional.part;
		return p?.type === "tool-call" ? p : void 0;
	});
	let inferredId;
	if (part?.toolName === updateToolName) {
		const result = part.result;
		const args = part.args;
		if (result?.success !== false) {
			if (typeof result?.id === "string") inferredId = result.id;
			else if (typeof args?.id === "string") inferredId = args.id;
		}
	}
	const id = config.id ?? inferredId ?? autoId;
	const internalScope = part?.toolName === name || part?.toolName === updateToolName ? "thread" : void 0;
	const stateSchemaRef = useRef(config.stateSchema);
	stateSchemaRef.current = config.stateSchema;
	const normalizedStateSchema = useJSONSchemaDependency(config.stateSchema);
	const initialStateRef = useRef(config.initialState);
	initialStateRef.current = config.initialState;
	const interactables = useAuiState(() => aui.unstable_interactables);
	useEffect(() => {
		return interactables.register({
			id,
			name,
			description: config.description,
			stateSchema: stateSchemaRef.current,
			initialState: initialStateRef.current,
			updateRender: config.updateRender,
			...internalScope ? { scope: internalScope } : {}
		});
	}, [
		interactables,
		id,
		name,
		config.description,
		normalizedStateSchema,
		internalScope,
		config.updateRender
	]);
	const myToolCallId = part?.toolCallId;
	const [registeredState, methods] = unstable_useInteractableState(id);
	const { setState } = methods;
	const versionValue = useAuiState(useJSONEqual((s_0) => {
		if (!internalScope || !myToolCallId) return void 0;
		const versions = unstable_getInteractableVersions(s_0.thread.messages, id, name);
		if (!versions.some((v) => v.origin === "create" && v.toolCallId === id)) return;
		const mine = versions.find((v_0) => v_0.toolCallId === myToolCallId);
		if (!mine) return void 0;
		const latestToolCallId = versions.findLast((v_1) => v_1.toolCallId !== void 0)?.toolCallId;
		return {
			state: mine.state,
			isLatest: latestToolCallId === myToolCallId
		};
	}));
	const version = useMemo(() => versionValue && {
		state: versionValue.state,
		isLatest: versionValue.isLatest,
		restore: () => setState(versionValue.state)
	}, [versionValue, setState]);
	return [registeredState === void 0 ? config.initialState : registeredState, {
		id,
		version,
		...methods
	}];
};
/**
* Registers an interactable with the AI assistant and returns its live state,
* like `useState` that the model can also read and update.
*
* Call this once per place that shows the interactable. Other components can
* read and write the same instance by passing its `id` to
* `unstable_useInteractableState`.
*
* For tool-created interactables rendered inside tool-call message parts,
* `version` carries this message's version of the instance — its state as of
* that point in the conversation, whether it is the most recent tool-driven
* version, and a `restore()` back to it. Whether older messages render frozen history or stay
* live-editable is the component's choice. Inside an `update_{name}` part the
* instance `id` is inferred from the call, so the same component works at the
* creating call and at update calls.
*
* @deprecated Unstable / Experimental (not actually removed).
*/
const unstable_useInteractable = useInteractable;
//#endregion
export { unstable_useInteractable };
