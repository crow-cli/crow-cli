"use client";
//#region src/primitives/thread/topAnchor/createReserveObservers.ts
const createReserveObservers = (onChange) => {
	const resizeObserver = new ResizeObserver(onChange);
	const mutationObserver = new MutationObserver(onChange);
	let observedViewport = null;
	let observedAnchor = null;
	let observedTarget = null;
	const disconnect = () => {
		resizeObserver.disconnect();
		mutationObserver.disconnect();
		observedViewport = null;
		observedAnchor = null;
		observedTarget = null;
	};
	return {
		target: (viewport, anchor, target) => {
			if (observedViewport === viewport && observedAnchor === anchor && observedTarget === target) return;
			disconnect();
			resizeObserver.observe(viewport);
			resizeObserver.observe(anchor);
			resizeObserver.observe(target);
			mutationObserver.observe(target, {
				childList: true,
				subtree: true,
				characterData: true
			});
			observedViewport = viewport;
			observedAnchor = anchor;
			observedTarget = target;
		},
		disconnect
	};
};
//#endregion
export { createReserveObservers };
