import { peekResourceFiber } from "../core/helpers/execution-context.js";
import { bubbleContextDeps, hasChangedContexts, hasContextDepsChanged } from "../core/context.js";
import { depsShallowEqual } from "./utils/depsShallowEqual.js";
import { commitResourceFiber, discardWipRender, renderResourceFiber, unmountResourceFibers } from "../core/ResourceFiber.js";
import { useHostLifecycle, useResourceFiberHost } from "./utils/useResourceFiberHostUtils.js";
import { useRenderMemo } from "./utils/useRenderMemo.js";
import { useEffect, useState } from "@assistant-ui/tap/react-shim";
//#region src/hooks/useResources.ts
const markChildDirty = (fibers, key) => {
	const state = fibers.get(key);
	if (state) state.isDirty = true;
};
const canReuse = (state, deps) => !state.isDirty && !hasContextDepsChanged(state.fiber) && deps !== void 0 && state.committedDeps !== void 0 && depsShallowEqual(state.committedDeps, deps);
const hasAnyChildContextDepsChanged = (fibers) => {
	if (!hasChangedContexts()) return false;
	for (const { fiber } of fibers.values()) if (hasContextDepsChanged(fiber)) return true;
	return false;
};
function useResources(elements) {
	const [fibers] = useState(() => /* @__PURE__ */ new Map());
	const { version, createFiber } = useResourceFiberHost();
	const isRefreshing = peekResourceFiber()?.isRefreshing ?? false;
	const hasAnyContextDepsChanged = hasAnyChildContextDepsChanged(fibers);
	let releases = false;
	const val = useRenderMemo(() => {
		const seenKeys = /* @__PURE__ */ new Set();
		const values = [];
		let newCount = 0;
		for (let i = 0; i < elements.length; i++) {
			const element = elements[i];
			const elementKey = element.key;
			if (elementKey === void 0) throw new Error(`useResources did not provide a key for array at index ${i}`);
			if (seenKeys.has(elementKey)) throw new Error(`Duplicate key ${elementKey} in useResources`);
			seenKeys.add(elementKey);
			let state = fibers.get(elementKey);
			if (!state) {
				const fiber = createFiber(element.hook, element.key, () => markChildDirty(fibers, elementKey));
				state = {
					fiber,
					next: {
						value: renderResourceFiber(fiber, element.args),
						deps: element.deps
					},
					isDirty: false,
					committedDeps: void 0,
					committedValue: void 0
				};
				newCount++;
				fibers.set(elementKey, state);
			} else if (state.fiber.hook !== element.hook) {
				const fiber = createFiber(element.hook, element.key, () => markChildDirty(fibers, elementKey));
				const value = renderResourceFiber(fiber, element.args);
				state.next = {
					value,
					deps: element.deps,
					remount: fiber
				};
				releases = true;
			} else if (!isRefreshing && canReuse(state, element.deps)) {
				if (typeof state.next === "object") discardWipRender(state.fiber);
				if (state.fiber.contextDeps) bubbleContextDeps(state.fiber, state.fiber.contextDeps);
				state.next = "skip";
			} else {
				const value = renderResourceFiber(state.fiber, element.args);
				state.next = {
					value,
					deps: element.deps
				};
			}
			values.push(typeof state.next === "object" ? state.next.value : state.committedValue);
		}
		if (fibers.size > values.length - newCount) {
			for (const key of fibers.keys()) if (!seenKeys.has(key)) {
				fibers.get(key).next = "delete";
				releases = true;
			}
		}
		return values;
	}, [
		elements,
		fibers,
		createFiber,
		version
	], isRefreshing || hasAnyContextDepsChanged);
	useHostLifecycle(fibers);
	useEffect(() => {
		if (releases) {
			const released = [];
			for (const [key, state] of fibers.entries()) {
				const next = state.next;
				if (next === "delete") {
					released.push(state.fiber);
					fibers.delete(key);
				} else if (next !== "skip" && next.remount) {
					released.push(state.fiber);
					state.fiber = next.remount;
				}
			}
			for (const fiber of released) fiber.isReleased = true;
			unmountResourceFibers(released);
		}
		for (const state of fibers.values()) {
			const next = state.next;
			if (next === "skip") {
				if (!state.fiber.isNeverMounted && !state.fiber.isMounted) commitResourceFiber(state.fiber);
			} else if (next !== "delete") {
				commitResourceFiber(state.fiber);
				state.committedDeps = next.deps;
				state.committedValue = next.value;
				state.isDirty = false;
				state.next = "skip";
			}
		}
	}, [
		val,
		fibers,
		releases
	]);
	return isRefreshing ? val.slice() : val;
}
//#endregion
export { useResources };
