import { isDevelopment } from "./helpers/env.js";
import { createResourceFiberRoot } from "./helpers/root.js";
import { isThenable } from "./helpers/thenable.js";
import { commitResourceFiber, createResourceFiber, renderResourceFiber, unmountResourceFiber } from "./ResourceFiber.js";
import { flushTapSync, scheduleTask } from "./scheduler.js";
import { useTapRoot } from "../hooks/useTapRoot.js";
//#region src/core/createTapRoot.ts
const createTapRoot = (render, options) => {
	let isUnmounted = false;
	const fiber = createResourceFiber(useTapRoot, createResourceFiberRoot((evaluate, apply) => {
		if (!evaluate()) return;
		apply();
		scheduleTask(() => {
			if (isUnmounted || !fiber.isMounted) return;
			if (isDevelopment && fiber.devStrictMode) renderResourceFiber(fiber, [render]);
			renderResourceFiber(fiber, [render]);
			commitResourceFiber(fiber);
		});
	}), void 0, isDevelopment ? "root" : null);
	const renderFiber = () => {
		try {
			if (isDevelopment && fiber.devStrictMode) renderResourceFiber(fiber, [render]);
			return renderResourceFiber(fiber, [render]);
		} catch (error) {
			if (isThenable(error)) throw new Error("createTapRoot suspended during its initial render; resolve the data first or use useTapRoot under a Suspense boundary.");
			throw error;
		}
	};
	const commitFiber = () => flushTapSync(() => scheduleTask(() => {
		if (!isUnmounted) commitResourceFiber(fiber);
	}));
	const unmount = () => {
		if (isUnmounted) return;
		isUnmounted = true;
		unmountResourceFiber(fiber);
	};
	let root;
	const ensureRoot = () => root ??= renderFiber();
	if (!options?.mountOnSubscribe) {
		const root = ensureRoot();
		commitFiber();
		return {
			...root,
			unmount
		};
	}
	let subscriberCount = 0;
	const scheduleUnmount = () => scheduleTask(() => {
		if (subscriberCount === 0 && fiber.isMounted) unmountResourceFiber(fiber, false);
	});
	return {
		getValue: () => ensureRoot().getValue(),
		subscribe: (listener) => {
			const unsubscribe = ensureRoot().subscribe(listener);
			if (subscriberCount++ === 0 && !fiber.isMounted && !isUnmounted) try {
				commitFiber();
			} catch (error) {
				try {
					unmountResourceFiber(fiber, false);
				} finally {
					subscriberCount--;
					unsubscribe();
				}
				throw error;
			}
			let isSubscribed = true;
			return () => {
				if (!isSubscribed) return;
				isSubscribed = false;
				unsubscribe();
				if (--subscriberCount === 0) scheduleUnmount();
			};
		},
		unmount
	};
};
//#endregion
export { createTapRoot };
