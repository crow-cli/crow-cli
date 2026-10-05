import { isDevelopment } from "../core/helpers/env.js";
import { commitRoot, createResourceFiberRoot, setRootVersion } from "../core/helpers/root.js";
import { cloneCurrentTapContext, withTapContextRoot } from "../core/context.js";
import { throwAggregated } from "../core/helpers/throwAggregated.js";
import { isThenable } from "../core/helpers/thenable.js";
import { commitResourceFiber, createResourceFiber, renderResourceFiber } from "../core/ResourceFiber.js";
import { UpdateScheduler, scheduleNotify } from "../core/scheduler.js";
import { useDevStrictMode } from "./utils/useDevStrictMode.js";
import { useHostLifecycle } from "./utils/useResourceFiberHostUtils.js";
import { useEffect, useMemo, useRef, useState } from "@assistant-ui/tap/react-shim";
//#region src/hooks/useTapRoot.ts
const useHostRoot = (render) => render();
const notifySubscribers = (subscribers) => {
	const errors = [];
	for (const listener of subscribers) try {
		listener();
	} catch (error) {
		errors.push(error);
	}
	throwAggregated(errors, "Errors occurred while notifying Tap root subscribers");
};
const createInstance = (render, devStrictMode, forceHostRender) => {
	const scheduler = new UpdateScheduler(() => inst.handleUpdate());
	const queue = [];
	const root = createResourceFiberRoot((evaluate, apply) => {
		if (queue.length === 0 && !evaluate()) return;
		queue.push(apply);
		scheduler.markDirty();
	});
	const fiber = createResourceFiber(useHostRoot, root, void 0, devStrictMode);
	const inst = {
		scheduler,
		queue,
		fiber,
		subscribers: /* @__PURE__ */ new Set(),
		pendingHostRender: false,
		isMounted: false,
		hasRendered: false,
		committedRender: render,
		context: /* @__PURE__ */ new Map(),
		value: void 0,
		applyQueue: () => {
			setRootVersion(root, root.committedVersion);
			for (const apply of queue) {
				if (isDevelopment && fiber.devStrictMode) apply();
				apply();
			}
			setRootVersion(root, root.committedVersion + root.changelog.length);
			return queue.length;
		},
		publish: (output, version) => {
			if (scheduler.isDirty || root.committedVersion !== version || inst.value === output) return;
			inst.value = output;
			scheduleNotify(() => notifySubscribers(inst.subscribers));
		},
		finishFlush: (output, version, drained) => {
			commitRoot(root);
			queue.splice(0, drained);
			inst.pendingHostRender = false;
			if (queue.length === 0) scheduler.settle();
			if (inst.isMounted) commitResourceFiber(fiber);
			inst.publish(output, version);
		},
		handleUpdate: () => {
			const drained = inst.applyQueue();
			let output;
			try {
				if (isDevelopment && fiber.devStrictMode) withTapContextRoot(inst.context, () => {
					return renderResourceFiber(fiber, [inst.committedRender]);
				});
				output = withTapContextRoot(inst.context, () => {
					return renderResourceFiber(fiber, [inst.committedRender]);
				});
			} catch (error) {
				setRootVersion(root, root.committedVersion);
				if (isThenable(error)) {
					const retry = () => {
						if (inst.isMounted) scheduler.markDirty();
					};
					error.then(retry, retry);
					return;
				}
				if (inst.isMounted) {
					inst.pendingHostRender = true;
					forceHostRender((c) => c + 1);
					return;
				}
				throw error;
			}
			if (scheduler.isDirty) throw new Error("Scheduler is dirty, this should never happen");
			inst.finishFlush(output, root.version, drained);
		}
	};
	return inst;
};
const useTapRoot = (render) => {
	const [, forceHostRender] = useState(0);
	const getDevStrictMode = useDevStrictMode();
	const instRef = useRef(null);
	const inst = instRef.current ??= createInstance(render, getDevStrictMode(), forceHostRender);
	const context = cloneCurrentTapContext();
	const drained = inst.scheduler.isDirty || inst.pendingHostRender ? inst.applyQueue() : 0;
	const value = withTapContextRoot(context, () => {
		return renderResourceFiber(inst.fiber, [render]);
	});
	const renderState = {
		render,
		context,
		value,
		drained,
		wip: inst.fiber.wipCommitCallbacks,
		version: inst.fiber.root.version,
		processed: false
	};
	if (!inst.hasRendered) {
		inst.hasRendered = true;
		inst.committedRender = render;
		inst.context = context;
		inst.value = value;
	}
	useEffect(() => {
		inst.isMounted = true;
		return () => {
			inst.isMounted = false;
		};
	}, [inst]);
	useHostLifecycle(inst.fiber);
	useEffect(() => {
		if (renderState.processed) {
			if (!inst.fiber.isMounted) {
				commitResourceFiber(inst.fiber);
				if (inst.queue.length && !inst.scheduler.isDirty) inst.scheduler.markDirty();
			}
			return;
		}
		renderState.processed = true;
		inst.committedRender = renderState.render;
		inst.context = renderState.context;
		if (inst.fiber.wipCommitCallbacks !== renderState.wip) {
			if (!inst.scheduler.isDirty) inst.handleUpdate();
			return;
		}
		if (renderState.drained > 0 && inst.fiber.root.version === renderState.version) {
			inst.finishFlush(renderState.value, renderState.version, renderState.drained);
			return;
		}
		commitResourceFiber(inst.fiber);
		inst.publish(renderState.value, renderState.version);
	});
	return useMemo(() => ({
		getValue: () => inst.value,
		subscribe: (listener) => {
			inst.subscribers.add(listener);
			return () => inst.subscribers.delete(listener);
		}
	}), [inst]);
};
//#endregion
export { useTapRoot };
