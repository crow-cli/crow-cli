import { getCurrentResourceFiber, peekResourceFiber } from "../../core/helpers/execution-context.js";
import { createResourceFiberRoot, setRootVersion } from "../../core/helpers/root.js";
import { createResourceFiber, unmountResourceFiber, unmountResourceFibers } from "../../core/ResourceFiber.js";
import { useDevStrictMode } from "./useDevStrictMode.js";
import { useHostCell } from "./useHostCell.js";
import { useCallback, useEffect, useInsertionEffect, useMemo, useReducer, useRef, useState } from "@assistant-ui/tap/react-shim";
//#region src/hooks/utils/useResourceFiberHostUtils.ts
const forEachHostedFiber = (target, visit) => {
	if (!(target instanceof Map)) return visit(target);
	for (const { fiber } of target.values()) visit(fiber);
};
const acquire = (fiber) => {
	fiber.isReleased = false;
};
const release = (fiber) => {
	fiber.isReleased = true;
	if (!fiber.isMounted) queueMicrotask(() => {
		if (fiber.isReleased) unmountResourceFiber(fiber, true);
	});
};
const useHostLifecycleReact = (target) => {
	useInsertionEffect(() => {
		forEachHostedFiber(target, acquire);
		return () => forEachHostedFiber(target, release);
	}, [target]);
	useEffect(() => () => {
		unmountResourceFibers(target instanceof Map ? Array.from(target.values(), ({ fiber }) => fiber) : [target]);
	}, [target]);
};
const useHostLifecycle = (target) => {
	if (peekResourceFiber()) return useHostCell(target);
	else {
		useHostLifecycleReact(target);
		return null;
	}
};
const useResourceFiberHostUtilsTap = () => {
	const versionRef = useRef(0);
	const version = versionRef.current;
	const parent = getCurrentResourceFiber();
	return {
		version,
		markDirty: useMemo(() => () => {
			versionRef.current++;
			parent.markDirty?.();
		}, [parent]),
		root: parent.root
	};
};
const useResourceFiberHostUtilsReact = () => {
	const [root] = useState(() => {
		return createResourceFiberRoot((evaluateUpdate, applyUpdate) => {
			let eagerBail = false;
			evaluate((version) => {
				eagerBail = !evaluateUpdate();
				return eagerBail ? version : version + 1;
			});
			if (!eagerBail) apply(() => evaluateUpdate() && applyUpdate());
		});
	});
	const [version, apply] = useReducer((v, applyUpdate) => {
		setRootVersion(root, v);
		return v + (applyUpdate() ? 1 : 0);
	}, 0);
	const [, evaluate] = useState(0);
	setRootVersion(root, version);
	return {
		root,
		version,
		markDirty: void 0
	};
};
const useResourceFiberHost = () => {
	const getDevMode = useDevStrictMode();
	const { root, version, markDirty } = peekResourceFiber() ? useResourceFiberHostUtilsTap() : useResourceFiberHostUtilsReact();
	return {
		version,
		createFiber: useCallback((hook, _key, onDirty) => {
			return createResourceFiber(hook, root, onDirty ? () => {
				onDirty();
				markDirty?.();
			} : markDirty, getDevMode());
		}, [])
	};
};
//#endregion
export { useHostLifecycle, useResourceFiberHost };
