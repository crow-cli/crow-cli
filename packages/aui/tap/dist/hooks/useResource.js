import { peekResourceFiber } from "../core/helpers/execution-context.js";
import { hasContextDepsChanged } from "../core/context.js";
import { depsShallowEqual } from "./utils/depsShallowEqual.js";
import { commitResourceFiber, renderResourceFiber, unmountResourceFiber } from "../core/ResourceFiber.js";
import { useHostLifecycle, useResourceFiberHost } from "./utils/useResourceFiberHostUtils.js";
import { useEffect, useMemo, useRef } from "@assistant-ui/tap/react-shim";
//#region src/hooks/useResource.ts
const createHostState = (fiber, key) => ({
	fiber,
	key,
	currentDeps: null,
	current: null,
	wipDeps: null,
	wip: null
});
function useResource(element) {
	const { version, createFiber } = useResourceFiberHost();
	const stateRef = useRef(null);
	const state = stateRef.current ??= createHostState(createFiber(element.hook, element.key), element.key);
	const fiber = useMemo(() => state.fiber.hook === element.hook && state.key === element.key && !state.fiber.isReleased ? state.fiber : createFiber(element.hook, element.key), [
		state,
		element.hook,
		element.key,
		createFiber
	]);
	state.wipDeps = state.currentDeps;
	state.wip = state.current;
	const deps = [
		fiber,
		version,
		element.args
	];
	if (peekResourceFiber()?.isRefreshing || hasContextDepsChanged(fiber) || state.currentDeps === null || !depsShallowEqual(state.currentDeps, deps)) {
		state.wipDeps = deps;
		state.wip = { value: renderResourceFiber(fiber, element.args) };
	}
	const result = state.wip;
	const cell = useHostLifecycle(fiber);
	useEffect(() => {
		state.currentDeps = state.wipDeps;
		state.current = state.wip;
		state.fiber = fiber;
		state.key = element.key;
		commitResourceFiber(fiber);
		if (cell !== null) return () => {
			if (cell.fiber !== fiber) unmountResourceFiber(fiber, true);
		};
	}, [
		state,
		cell,
		fiber,
		element.key,
		result
	]);
	return result.value;
}
//#endregion
export { useResource };
