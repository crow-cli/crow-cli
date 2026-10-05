"use client";
import { Primitive } from "../../../utils/Primitive.js";
import { useComposerInputPluginRegistryOptional } from "../ComposerInputPluginContext.js";
import { useTriggerPopoverAriaPublish, useTriggerPopoverRootContext } from "./TriggerPopoverRootContext.js";
import { TriggerPopoverResource } from "./TriggerPopoverResource.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { createContext, forwardRef, useContext, useEffect, useEffectEvent, useId, useRef, useState } from "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
import { useResource } from "@assistant-ui/tap";
import { jsx } from "react/jsx-runtime";
//#region src/primitives/composer/trigger/TriggerPopover.tsx
const TriggerPopoverScopeContext = createContext(null);
const useTriggerPopoverScopeContext = () => {
	const ctx = useContext(TriggerPopoverScopeContext);
	if (!ctx) throw new Error("useTriggerPopoverScopeContext must be used within ComposerPrimitive.TriggerPopover");
	return ctx;
};
const useTriggerPopoverScopeContextOptional = () => {
	return useContext(TriggerPopoverScopeContext);
};
const TriggerBehaviorRegistrationContext = createContext(null);
/** Obtain the registration handle from the parent `<TriggerPopover>`. */
const useTriggerBehaviorRegistration = () => {
	const ctx = useContext(TriggerBehaviorRegistrationContext);
	if (!ctx) throw new Error("TriggerPopover.Directive / TriggerPopover.Action must be rendered inside ComposerPrimitive.TriggerPopover");
	return ctx;
};
/**
* Declares a trigger and renders its popover container. The popover only
* renders its DOM (and children) when the trigger character is active in the
* composer input and a behavior sub-primitive has been registered.
*
* A behavior is contributed by rendering exactly one of
* `<TriggerPopover.Directive>` or `<TriggerPopover.Action>` as a child. Without
* a behavior the trigger stays closed.
*
* Must be placed inside `ComposerPrimitive.Unstable_TriggerPopoverRoot`.
*
* @example
* ```tsx
* <ComposerPrimitive.Unstable_TriggerPopover
*   char="@"
*   adapter={mentionAdapter}
* >
*   <ComposerPrimitive.Unstable_TriggerPopover.Directive formatter={formatter} />
*   <ComposerPrimitive.Unstable_TriggerPopoverCategories>
*     {(cats) => cats.map(...)}
*   </ComposerPrimitive.Unstable_TriggerPopoverCategories>
*   <ComposerPrimitive.Unstable_TriggerPopoverItems>
*     {(items) => items.map(...)}
*   </ComposerPrimitive.Unstable_TriggerPopoverItems>
* </ComposerPrimitive.Unstable_TriggerPopover>
* ```
*/
const ComposerPrimitiveTriggerPopover = forwardRef((t0, forwardedRef) => {
	const $ = c(69);
	let adapter;
	let ariaLabel;
	let char;
	let children;
	let matcher;
	let props;
	let t1;
	if ($[0] !== t0) {
		({char, matcher, adapter, isLoading: t1, "aria-label": ariaLabel, children, ...props} = t0);
		$[0] = t0;
		$[1] = adapter;
		$[2] = ariaLabel;
		$[3] = char;
		$[4] = children;
		$[5] = matcher;
		$[6] = props;
		$[7] = t1;
	} else {
		adapter = $[1];
		ariaLabel = $[2];
		char = $[3];
		children = $[4];
		matcher = $[5];
		props = $[6];
		t1 = $[7];
	}
	const isLoading = t1 === void 0 ? false : t1;
	const aui = useAui();
	const text = useAuiState(_temp);
	const popoverId = useId();
	const matcherRef = useRef(matcher);
	let t2;
	if ($[8] !== matcher) {
		t2 = () => {
			matcherRef.current = matcher;
		};
		$[8] = matcher;
		$[9] = t2;
	} else t2 = $[9];
	useEffect(t2);
	let t3;
	if ($[10] === Symbol.for("react.memo_cache_sentinel")) {
		t3 = () => (nextText, triggerChar, cursorPosition) => matcherRef.current(nextText, triggerChar, cursorPosition);
		$[10] = t3;
	} else t3 = $[10];
	const [registeredMatcher] = useState(t3);
	const hasMatcher = matcher !== void 0;
	const behaviorRef = useRef(null);
	const [behavior, setBehavior] = useState(null);
	const registrationCountRef = useRef(0);
	let t4;
	if ($[11] !== char) {
		t4 = (next) => {
			registrationCountRef.current = registrationCountRef.current + 1;
			if (process.env.NODE_ENV !== "production" && registrationCountRef.current > 1) console.warn(`[assistant-ui] TriggerPopover "${char}" received more than one behavior child. Exactly one <TriggerPopover.Directive> or <TriggerPopover.Action> is allowed per TriggerPopover; the last registration wins.`);
			behaviorRef.current = next;
			setBehavior(next);
			return () => {
				registrationCountRef.current = Math.max(0, registrationCountRef.current - 1);
				if (behaviorRef.current === next) {
					behaviorRef.current = null;
					setBehavior(null);
				}
			};
		};
		$[11] = char;
		$[12] = t4;
	} else t4 = $[12];
	const register = t4;
	let t5;
	if ($[13] !== register) {
		t5 = { register };
		$[13] = register;
		$[14] = t5;
	} else t5 = $[14];
	const registration = t5;
	const t6 = behavior ?? void 0;
	let t7;
	if ($[15] !== adapter || $[16] !== aui || $[17] !== char || $[18] !== isLoading || $[19] !== matcher || $[20] !== popoverId || $[21] !== t6 || $[22] !== text) {
		t7 = TriggerPopoverResource({
			adapter,
			text,
			triggerChar: char,
			matcher,
			behavior: t6,
			aui,
			popoverId,
			isLoading
		});
		$[15] = adapter;
		$[16] = aui;
		$[17] = char;
		$[18] = isLoading;
		$[19] = matcher;
		$[20] = popoverId;
		$[21] = t6;
		$[22] = text;
		$[23] = t7;
	} else t7 = $[23];
	const resource = useResource(t7);
	let t8;
	if ($[24] !== resource) {
		t8 = () => resource;
		$[24] = resource;
		$[25] = t8;
	} else t8 = $[25];
	const getResource = useEffectEvent(t8);
	const root = useTriggerPopoverRootContext();
	let t9;
	if ($[26] !== behavior || $[27] !== char || $[28] !== getResource || $[29] !== hasMatcher || $[30] !== registeredMatcher || $[31] !== root) {
		t9 = () => root.register({
			char,
			...hasMatcher ? { matcher: registeredMatcher } : {},
			...behavior ? { behavior } : {},
			resource: getResource()
		});
		$[26] = behavior;
		$[27] = char;
		$[28] = getResource;
		$[29] = hasMatcher;
		$[30] = registeredMatcher;
		$[31] = root;
		$[32] = t9;
	} else t9 = $[32];
	let t10;
	if ($[33] !== behavior || $[34] !== char || $[35] !== hasMatcher || $[36] !== root) {
		t10 = [
			root,
			char,
			hasMatcher,
			behavior
		];
		$[33] = behavior;
		$[34] = char;
		$[35] = hasMatcher;
		$[36] = root;
		$[37] = t10;
	} else t10 = $[37];
	useEffect(t9, t10);
	const pluginRegistry = useComposerInputPluginRegistryOptional();
	let t11;
	if ($[38] !== getResource || $[39] !== pluginRegistry) {
		t11 = () => {
			if (!pluginRegistry) return;
			return pluginRegistry.register(getResource());
		};
		$[38] = getResource;
		$[39] = pluginRegistry;
		$[40] = t11;
	} else t11 = $[40];
	let t12;
	if ($[41] !== pluginRegistry) {
		t12 = [pluginRegistry];
		$[41] = pluginRegistry;
		$[42] = t12;
	} else t12 = $[42];
	useEffect(t11, t12);
	const open = behavior !== null && resource.open;
	const aria = useTriggerPopoverAriaPublish();
	let t13;
	let t14;
	if ($[43] !== aria || $[44] !== char || $[45] !== open) {
		t13 = () => {
			if (!open) return;
			return () => {
				aria.setActiveAria(char, null);
			};
		};
		t14 = [
			aria,
			char,
			open
		];
		$[43] = aria;
		$[44] = char;
		$[45] = open;
		$[46] = t13;
		$[47] = t14;
	} else {
		t13 = $[46];
		t14 = $[47];
	}
	useEffect(t13, t14);
	let t15;
	let t16;
	if ($[48] !== aria || $[49] !== char || $[50] !== open || $[51] !== popoverId || $[52] !== resource.highlightedItemId) {
		t15 = () => {
			if (!open) return;
			aria.setActiveAria(char, {
				popoverId,
				highlightedItemId: resource.highlightedItemId
			});
		};
		t16 = [
			aria,
			char,
			popoverId,
			open,
			resource.highlightedItemId
		];
		$[48] = aria;
		$[49] = char;
		$[50] = open;
		$[51] = popoverId;
		$[52] = resource.highlightedItemId;
		$[53] = t15;
		$[54] = t16;
	} else {
		t15 = $[53];
		t16 = $[54];
	}
	useEffect(t15, t16);
	let t17;
	if ($[55] !== ariaLabel || $[56] !== children || $[57] !== forwardedRef || $[58] !== open || $[59] !== popoverId || $[60] !== props || $[61] !== resource.highlightedItemId) {
		t17 = open ? /* @__PURE__ */ jsx(Primitive.div, {
			role: "listbox",
			id: popoverId,
			"aria-label": ariaLabel ?? "Suggestions",
			"aria-activedescendant": resource.highlightedItemId,
			"data-state": "open",
			...props,
			ref: forwardedRef,
			children
		}) : children;
		$[55] = ariaLabel;
		$[56] = children;
		$[57] = forwardedRef;
		$[58] = open;
		$[59] = popoverId;
		$[60] = props;
		$[61] = resource.highlightedItemId;
		$[62] = t17;
	} else t17 = $[62];
	let t18;
	if ($[63] !== resource || $[64] !== t17) {
		t18 = /* @__PURE__ */ jsx(TriggerPopoverScopeContext.Provider, {
			value: resource,
			children: t17
		});
		$[63] = resource;
		$[64] = t17;
		$[65] = t18;
	} else t18 = $[65];
	let t19;
	if ($[66] !== registration || $[67] !== t18) {
		t19 = /* @__PURE__ */ jsx(TriggerBehaviorRegistrationContext.Provider, {
			value: registration,
			children: t18
		});
		$[66] = registration;
		$[67] = t18;
		$[68] = t19;
	} else t19 = $[68];
	return t19;
});
ComposerPrimitiveTriggerPopover.displayName = "ComposerPrimitive.TriggerPopover";
function _temp(s) {
	return s.composer.text;
}
//#endregion
export { ComposerPrimitiveTriggerPopover, useTriggerBehaviorRegistration, useTriggerPopoverScopeContext, useTriggerPopoverScopeContextOptional };
