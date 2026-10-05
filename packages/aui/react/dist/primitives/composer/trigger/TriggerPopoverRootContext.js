"use client";
import { ComposerInputPluginProvider, useComposerInputPluginRegistryOptional } from "../ComposerInputPluginContext.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { createContext, useContext, useRef, useSyncExternalStore } from "@assistant-ui/tap/react-shim";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/composer/trigger/TriggerPopoverRootContext.tsx
const TriggerPopoverRootContext = createContext(null);
const TriggerPopoverAriaPublishContext = createContext(null);
const useTriggerPopoverRootContext = () => {
	const ctx = useContext(TriggerPopoverRootContext);
	if (!ctx) throw new Error("useTriggerPopoverRootContext must be used within ComposerPrimitive.TriggerPopoverRoot");
	return ctx;
};
const useTriggerPopoverRootContextOptional = () => {
	return useContext(TriggerPopoverRootContext);
};
/**
* Internal hook used by `TriggerPopover` children to publish their open and
* highlight state. Not exported from the trigger module.
*/
const useTriggerPopoverAriaPublish = () => {
	const ctx = useContext(TriggerPopoverAriaPublishContext);
	if (!ctx) throw new Error("useTriggerPopoverAriaPublish must be used within ComposerPrimitive.TriggerPopoverRoot");
	return ctx;
};
/**
* Live map of registered triggers, re-rendering on change. Prefer
* `subscribeLifecycle` for incremental add/remove handling.
*/
const useTriggerPopoverTriggers = () => {
	const ctx = useTriggerPopoverRootContext();
	return useSyncExternalStore(ctx.subscribe, ctx.getTriggers, ctx.getTriggers);
};
const EMPTY_TRIGGERS = /* @__PURE__ */ new Map();
const noopSubscribe = () => () => {};
const getEmptyTriggers = () => EMPTY_TRIGGERS;
/** Like `useTriggerPopoverTriggers` but returns an empty map outside a root. */
const useTriggerPopoverTriggersOptional = () => {
	const ctx = useTriggerPopoverRootContextOptional();
	return useSyncExternalStore(ctx ? ctx.subscribe : noopSubscribe, ctx ? ctx.getTriggers : getEmptyTriggers, ctx ? ctx.getTriggers : getEmptyTriggers);
};
const getNullAria = () => null;
/**
* Returns the ARIA descriptor of the currently open trigger popover, or
* `null` if none is open or the consumer is rendered outside a
* `TriggerPopoverRoot`.
*/
const useTriggerPopoverActiveAriaOptional = () => {
	const ctx = useTriggerPopoverRootContextOptional();
	return useSyncExternalStore(ctx ? ctx.subscribeAria : noopSubscribe, ctx ? ctx.getActiveAria : getNullAria, ctx ? ctx.getActiveAria : getNullAria);
};
/**
* Local helper for the simple "notify-all listeners" subscribable pattern.
* Used twice in this file (trigger registry, active ARIA); kept inline to
* avoid pulling a single-use abstraction into the wider tree.
*/
function useSimpleSubscribable() {
	const $ = c(4);
	let t0;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t0 = /* @__PURE__ */ new Set();
		$[0] = t0;
	} else t0 = $[0];
	const listenersRef = useRef(t0);
	let t1;
	if ($[1] === Symbol.for("react.memo_cache_sentinel")) {
		t1 = () => {
			for (const listener of listenersRef.current) listener();
		};
		$[1] = t1;
	} else t1 = $[1];
	const notify = t1;
	let t2;
	if ($[2] === Symbol.for("react.memo_cache_sentinel")) {
		t2 = (listener_0) => {
			listenersRef.current.add(listener_0);
			return () => {
				listenersRef.current.delete(listener_0);
			};
		};
		$[2] = t2;
	} else t2 = $[2];
	const subscribe = t2;
	let t3;
	if ($[3] === Symbol.for("react.memo_cache_sentinel")) {
		t3 = {
			notify,
			subscribe
		};
		$[3] = t3;
	} else t3 = $[3];
	return t3;
}
const TriggerPopoverRootInner = (t0) => {
	const $ = c(21);
	const { children } = t0;
	let t1;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t1 = /* @__PURE__ */ new Map();
		$[0] = t1;
	} else t1 = $[0];
	const triggersRef = useRef(t1);
	let t2;
	if ($[1] === Symbol.for("react.memo_cache_sentinel")) {
		t2 = /* @__PURE__ */ new Set();
		$[1] = t2;
	} else t2 = $[1];
	const lifecycleListenersRef = useRef(t2);
	const { notify, subscribe } = useSimpleSubscribable();
	let t3;
	if ($[2] !== notify) {
		t3 = (trigger) => {
			const { char } = trigger;
			if (triggersRef.current.has(char)) {
				if (process.env.NODE_ENV !== "production") console.warn(`[assistant-ui] Duplicate TriggerPopover for char "${char}". Ignoring the second registration.`);
				return _temp;
			}
			if (process.env.NODE_ENV !== "production") {
				for (const existing of triggersRef.current.values()) if (char.startsWith(existing.char) || existing.char.startsWith(char)) console.warn(`[assistant-ui] Trigger prefix collision between "${existing.char}" and "${char}". One char is a prefix of the other; only one will match reliably.`);
			}
			const next = new Map(triggersRef.current);
			next.set(char, trigger);
			triggersRef.current = next;
			notify();
			for (const l of lifecycleListenersRef.current) l.added(trigger);
			return () => {
				const after = new Map(triggersRef.current);
				after.delete(char);
				triggersRef.current = after;
				notify();
				for (const l_0 of lifecycleListenersRef.current) l_0.removed(char);
			};
		};
		$[2] = notify;
		$[3] = t3;
	} else t3 = $[3];
	const register = t3;
	let t4;
	if ($[4] === Symbol.for("react.memo_cache_sentinel")) {
		t4 = () => triggersRef.current;
		$[4] = t4;
	} else t4 = $[4];
	const getTriggers = t4;
	let t5;
	if ($[5] === Symbol.for("react.memo_cache_sentinel")) {
		t5 = (listener) => {
			lifecycleListenersRef.current.add(listener);
			return () => {
				lifecycleListenersRef.current.delete(listener);
			};
		};
		$[5] = t5;
	} else t5 = $[5];
	const subscribeLifecycle = t5;
	const activeAriaRef = useRef(null);
	const activeAriaCharRef = useRef(null);
	const { notify: notifyAria, subscribe: subscribeAria } = useSimpleSubscribable();
	let t6;
	if ($[6] !== notifyAria) {
		t6 = (char_0, aria) => {
			if (aria === null) {
				if (activeAriaCharRef.current !== char_0) return;
				activeAriaRef.current = null;
				activeAriaCharRef.current = null;
				notifyAria();
				return;
			}
			const prev = activeAriaRef.current;
			if (activeAriaCharRef.current === char_0 && prev !== null && prev.popoverId === aria.popoverId && prev.highlightedItemId === aria.highlightedItemId) return;
			activeAriaRef.current = aria;
			activeAriaCharRef.current = char_0;
			notifyAria();
		};
		$[6] = notifyAria;
		$[7] = t6;
	} else t6 = $[7];
	const setActiveAria = t6;
	let t7;
	if ($[8] === Symbol.for("react.memo_cache_sentinel")) {
		t7 = () => activeAriaRef.current;
		$[8] = t7;
	} else t7 = $[8];
	const getActiveAria = t7;
	let t8;
	if ($[9] !== register || $[10] !== subscribe || $[11] !== subscribeAria) {
		t8 = {
			register,
			getTriggers,
			subscribe,
			subscribeLifecycle,
			getActiveAria,
			subscribeAria
		};
		$[9] = register;
		$[10] = subscribe;
		$[11] = subscribeAria;
		$[12] = t8;
	} else t8 = $[12];
	const value = t8;
	let t9;
	if ($[13] !== setActiveAria) {
		t9 = { setActiveAria };
		$[13] = setActiveAria;
		$[14] = t9;
	} else t9 = $[14];
	const ariaPublishValue = t9;
	let t10;
	if ($[15] !== ariaPublishValue || $[16] !== children) {
		t10 = /* @__PURE__ */ jsx(TriggerPopoverAriaPublishContext.Provider, {
			value: ariaPublishValue,
			children
		});
		$[15] = ariaPublishValue;
		$[16] = children;
		$[17] = t10;
	} else t10 = $[17];
	let t11;
	if ($[18] !== t10 || $[19] !== value) {
		t11 = /* @__PURE__ */ jsx(TriggerPopoverRootContext.Provider, {
			value,
			children: t10
		});
		$[18] = t10;
		$[19] = value;
		$[20] = t11;
	} else t11 = $[20];
	return t11;
};
/**
* Provider that groups one or more `TriggerPopover` declarations. Each trigger
* is identified by its `char` (unique within the root). Behavior is contributed
* by a child `TriggerPopover.Directive` or `TriggerPopover.Action`.
*
* @example
* ```tsx
* <ComposerPrimitive.Unstable_TriggerPopoverRoot>
*   <ComposerPrimitive.Unstable_TriggerPopover char="@" adapter={mentionAdapter}>
*     <ComposerPrimitive.Unstable_TriggerPopover.Directive formatter={formatter} />
*     ...
*   </ComposerPrimitive.Unstable_TriggerPopover>
*
*   <ComposerPrimitive.Unstable_TriggerPopover char="/" adapter={slashAdapter}>
*     <ComposerPrimitive.Unstable_TriggerPopover.Action onExecute={handler} />
*     ...
*   </ComposerPrimitive.Unstable_TriggerPopover>
*
*   <ComposerPrimitive.Root>
*     <ComposerPrimitive.Input />
*   </ComposerPrimitive.Root>
* </ComposerPrimitive.Unstable_TriggerPopoverRoot>
* ```
*/
const ComposerPrimitiveTriggerPopoverRoot = (t0) => {
	const $ = c(4);
	const { children } = t0;
	if (useComposerInputPluginRegistryOptional()) {
		let t1;
		if ($[0] !== children) {
			t1 = /* @__PURE__ */ jsx(TriggerPopoverRootInner, { children });
			$[0] = children;
			$[1] = t1;
		} else t1 = $[1];
		return t1;
	}
	let t1;
	if ($[2] !== children) {
		t1 = /* @__PURE__ */ jsx(ComposerInputPluginProvider, { children: /* @__PURE__ */ jsx(TriggerPopoverRootInner, { children }) });
		$[2] = children;
		$[3] = t1;
	} else t1 = $[3];
	return t1;
};
ComposerPrimitiveTriggerPopoverRoot.displayName = "ComposerPrimitive.TriggerPopoverRoot";
function _temp() {}
//#endregion
export { ComposerPrimitiveTriggerPopoverRoot, useTriggerPopoverActiveAriaOptional, useTriggerPopoverAriaPublish, useTriggerPopoverRootContext, useTriggerPopoverRootContextOptional, useTriggerPopoverTriggers, useTriggerPopoverTriggersOptional };
