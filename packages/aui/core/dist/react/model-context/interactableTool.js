import { unstable_useInteractableState } from "./useInteractableState.js";
import { unstable_useInteractable } from "./useInteractable.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { Fragment, jsx } from "react/jsx-runtime";
//#region src/react/model-context/interactableTool.tsx
const noop = () => {};
/**
* Defines a tool that creates a thread-scoped interactable from its arguments,
* for assignment to a toolkit entry — the entry key is the interactable name:
*
* ```tsx
* notepad: unstable_interactableTool({
*   description: "A notepad the user can read and edit.",
*   stateSchema: notepadSchema,
*   render: (props) => <Notepad {...props} />,
* }),
* ```
*
* `render` shows at the creating call and — installed automatically — at every
* `update_{name}` call, with streaming previews, instance-id wiring, and
* registration handled. It receives the live `state`/`setState` plus this
* message's `version`; whether older messages render frozen history or stay
* live-editable is the render function's choice.
*
* @deprecated Unstable / Experimental (not actually removed).
*/
const unstable_interactableTool = (config) => {
	const Anchor = (t0) => {
		const $ = c(10);
		const { name, id, initial } = t0;
		let t1;
		if ($[0] !== id || $[1] !== initial) {
			t1 = {
				id,
				description: config.description,
				stateSchema: config.stateSchema,
				initialState: initial,
				updateRender: UpdateToolUI
			};
			$[0] = id;
			$[1] = initial;
			$[2] = t1;
		} else t1 = $[2];
		const [state, t2] = unstable_useInteractable(name, t1);
		const { id: resolvedId, setState, version } = t2;
		let t3;
		if ($[3] !== resolvedId || $[4] !== setState || $[5] !== state || $[6] !== version) {
			t3 = config.render({
				state,
				setState,
				version,
				id: resolvedId,
				streaming: false
			});
			$[3] = resolvedId;
			$[4] = setState;
			$[5] = state;
			$[6] = version;
			$[7] = t3;
		} else t3 = $[7];
		let t4;
		if ($[8] !== t3) {
			t4 = /* @__PURE__ */ jsx(Fragment, { children: t3 });
			$[8] = t3;
			$[9] = t4;
		} else t4 = $[9];
		return t4;
	};
	const StreamingUpdate = (t0) => {
		const $ = c(6);
		const { id } = t0;
		const [state, t1] = unstable_useInteractableState(id);
		const { setState } = t1;
		if (state === void 0) return null;
		let t2;
		if ($[0] !== id || $[1] !== setState || $[2] !== state) {
			t2 = config.render({
				state,
				setState,
				version: void 0,
				id,
				streaming: true
			});
			$[0] = id;
			$[1] = setState;
			$[2] = state;
			$[3] = t2;
		} else t2 = $[3];
		let t3;
		if ($[4] !== t2) {
			t3 = /* @__PURE__ */ jsx(Fragment, { children: t2 });
			$[4] = t2;
			$[5] = t3;
		} else t3 = $[5];
		return t3;
	};
	const UpdateToolUI = (t0) => {
		const $ = c(9);
		const { toolName, args, result } = t0;
		if (!result) {
			let t1;
			if ($[0] !== args.id) {
				t1 = typeof args.id === "string" ? /* @__PURE__ */ jsx(StreamingUpdate, { id: args.id }) : null;
				$[0] = args.id;
				$[1] = t1;
			} else t1 = $[1];
			return t1;
		}
		if (!result.success) return null;
		let partial;
		if ($[2] !== args) {
			const { id: _id, ...t1 } = args;
			partial = t1;
			$[2] = args;
			$[3] = partial;
		} else partial = $[3];
		let t1;
		if ($[4] !== toolName) {
			t1 = toolName.slice(7);
			$[4] = toolName;
			$[5] = t1;
		} else t1 = $[5];
		const t2 = partial;
		let t3;
		if ($[6] !== t1 || $[7] !== t2) {
			t3 = /* @__PURE__ */ jsx(Anchor, {
				name: t1,
				initial: t2
			});
			$[6] = t1;
			$[7] = t2;
			$[8] = t3;
		} else t3 = $[8];
		return t3;
	};
	const InteractableToolUI = (t0) => {
		const $ = c(9);
		const { toolName, toolCallId, args, result } = t0;
		const state = args;
		if (!result) {
			let t1;
			if ($[0] !== state || $[1] !== toolCallId) {
				t1 = config.render({
					state,
					setState: noop,
					version: void 0,
					id: toolCallId,
					streaming: true
				});
				$[0] = state;
				$[1] = toolCallId;
				$[2] = t1;
			} else t1 = $[2];
			let t2;
			if ($[3] !== t1) {
				t2 = /* @__PURE__ */ jsx(Fragment, { children: t1 });
				$[3] = t1;
				$[4] = t2;
			} else t2 = $[4];
			return t2;
		}
		let t1;
		if ($[5] !== state || $[6] !== toolCallId || $[7] !== toolName) {
			t1 = /* @__PURE__ */ jsx(Anchor, {
				name: toolName,
				id: toolCallId,
				initial: state
			});
			$[5] = state;
			$[6] = toolCallId;
			$[7] = toolName;
			$[8] = t1;
		} else t1 = $[8];
		return t1;
	};
	return {
		type: "frontend",
		description: config.description,
		parameters: config.stateSchema,
		display: "standalone",
		execute: async () => ({ success: true }),
		render: InteractableToolUI
	};
};
//#endregion
export { unstable_interactableTool };
