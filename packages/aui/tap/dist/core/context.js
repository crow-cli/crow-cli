import { getCurrentResourceFiber, peekResourceFiber } from "./helpers/execution-context.js";
import { useEffect } from "../react-hooks/useEffect.js";
import { useRef } from "../react-hooks/useRef.js";
//#region src/core/context.ts
const defaultContextValue = Symbol("tap.Context.defaultValue");
const asTap = (context) => context;
let currentContext = /* @__PURE__ */ new Map();
const changedContexts = /* @__PURE__ */ new Set();
const cloneCurrentTapContext = () => new Map(currentContext);
const withTapContextRoot = (context, fn) => {
	const previousContext = currentContext;
	currentContext = context;
	try {
		return fn();
	} finally {
		currentContext = previousContext;
	}
};
const attachDefaultValueToContext = (context, defaultValue) => {
	context[defaultContextValue] = defaultValue;
};
const isTapContext = (context) => typeof context === "object" && context !== null && defaultContextValue in context;
const isReactContext = (context) => typeof context === "object" && context !== null && "$$typeof" in context && context.$$typeof === Symbol.for("react.context");
const isReadableTapContext = (context) => isTapContext(context) || isReactContext(context);
const assertTapContext = (context) => {
	if (isTapContext(context)) return;
	if (isReactContext(context)) {
		attachDefaultValueToContext(context, context._currentValue ?? context._currentValue2);
		return;
	}
	throw new Error("A tap resource's `use()` only accepts a tap context.");
};
const useContextProvider = (context, value, fn) => {
	if (typeof context !== "object" || context === null) throw new Error("useContextProvider only accepts a React context.");
	assertTapContext(context);
	const key = context;
	const currentFiber = getCurrentResourceFiber();
	const committedValueRef = useRef(void 0);
	const didChange = committedValueRef.current === void 0 || !Object.is(committedValueRef.current.value, value);
	useEffect(() => {
		committedValueRef.current = { value };
	}, [value]);
	const previousValue = currentContext.get(key);
	const hadPreviousValue = previousValue !== void 0 || currentContext.has(key);
	currentContext.set(key, {
		value,
		source: currentFiber
	});
	try {
		return withChangedContext(key, didChange, fn);
	} finally {
		if (hadPreviousValue) currentContext.set(key, previousValue);
		else currentContext.delete(key);
	}
};
const withChangedContext = (context, didChange, fn) => {
	const restoreChangedContext = changedContexts.has(context);
	if (didChange) changedContexts.add(context);
	else changedContexts.delete(context);
	try {
		return fn();
	} finally {
		if (restoreChangedContext) changedContexts.add(context);
		else changedContexts.delete(context);
	}
};
const useContext = (context) => {
	assertTapContext(context);
	const key = context;
	const contextValue = getCurrentContextValue(key, context);
	const currentFiber = getCurrentResourceFiber();
	(currentFiber.wipContextDeps ??= /* @__PURE__ */ new Map()).set(key, contextValue.source);
	return contextValue.value;
};
const getCurrentContextValue = (key, context) => currentContext.get(key) ?? {
	value: asTap(context)[defaultContextValue],
	source: null
};
const mergeContextDeps = (targetFiber, sourceFiber, target, source) => {
	if (!source) return target;
	let next = target;
	for (const [context, providerFiber] of source) {
		if (providerFiber === sourceFiber || providerFiber === targetFiber) continue;
		(next ??= /* @__PURE__ */ new Map()).set(context, providerFiber);
	}
	return next;
};
const bubbleContextDeps = (fiber, contextDeps = fiber.wipContextDeps) => {
	const currentFiber = peekResourceFiber();
	if (!currentFiber || !contextDeps) return;
	currentFiber.wipContextDeps = mergeContextDeps(currentFiber, fiber, currentFiber.wipContextDeps, contextDeps);
};
const hasChangedContexts = () => changedContexts.size > 0;
const hasContextDepsChanged = (fiber) => {
	if (!fiber.contextDeps || !hasChangedContexts()) return false;
	for (const context of changedContexts.keys()) if (fiber.contextDeps.has(context)) return true;
	return false;
};
//#endregion
export { attachDefaultValueToContext, bubbleContextDeps, cloneCurrentTapContext, hasChangedContexts, hasContextDepsChanged, isReadableTapContext, useContext, useContextProvider, withTapContextRoot };
