"use client";
import { createReserveElement, getAnchorId, setReserveHeight, snapScrollTop } from "./topAnchorUtils.js";
import { computeTopAnchorReserve, computeTopAnchorTargetScrollTop } from "./computeTopAnchorSlack.js";
import { createReserveObservers } from "./createReserveObservers.js";
//#region src/primitives/thread/topAnchor/mountTopAnchorReserve.ts
const createFrameScheduler = (fn) => {
	let frame = null;
	return {
		schedule: () => {
			if (frame !== null) return;
			frame = requestAnimationFrame(() => {
				frame = null;
				fn();
			});
		},
		cancel: () => {
			if (frame !== null) {
				cancelAnimationFrame(frame);
				frame = null;
			}
		}
	};
};
const mountTopAnchorReserve = (store) => {
	let reserve = null;
	let lastScrolledAnchorId;
	let listenedViewport = null;
	let lastScrollTop = 0;
	let restoreScrollTop = null;
	let restoredThisTurn = false;
	let lastAppliedTarget = null;
	const clearRestore = () => {
		restoreScrollTop = null;
		lastAppliedTarget = null;
	};
	const wasPinnedAtLastScroll = () => lastAppliedTarget !== null && Math.abs(lastScrollTop - lastAppliedTarget) <= 1;
	const handleScroll = () => {
		const viewport = listenedViewport;
		if (!viewport) return;
		const scrollTop = viewport.scrollTop;
		const maxScrollTop = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
		if (scrollTop < lastScrollTop && lastScrollTop > maxScrollTop + 1 && Math.abs(scrollTop - maxScrollTop) <= 1 && wasPinnedAtLastScroll() && !restoredThisTurn) {
			restoreScrollTop ??= lastScrollTop;
			scheduler.schedule();
		}
		lastScrollTop = scrollTop;
	};
	const listenViewport = (viewport) => {
		if (listenedViewport === viewport) return;
		if (listenedViewport) listenedViewport.removeEventListener("scroll", handleScroll);
		listenedViewport = viewport;
		restoredThisTurn = false;
		clearRestore();
		if (viewport) {
			viewport.addEventListener("scroll", handleScroll, { passive: true });
			lastScrollTop = viewport.scrollTop;
		}
	};
	function apply() {
		const state = store.getState();
		const { viewport, anchor, target } = state.element;
		const clamp = state.targetConfig;
		listenViewport(state.turnAnchor === "top" ? viewport : null);
		if (state.turnAnchor !== "top" || !viewport) {
			observers.disconnect();
			clearRestore();
			if (reserve) {
				setReserveHeight(reserve, 0);
				reserve.remove();
			}
			return;
		}
		if (!anchor && !target && !clamp && state.topAnchorTurn) {
			observers.disconnect();
			clearRestore();
			if (reserve?.parentElement && reserve.parentElement.lastElementChild !== reserve) reserve.parentElement.append(reserve);
			return;
		}
		if (!anchor || !target || !clamp) {
			observers.disconnect();
			clearRestore();
			if (reserve) {
				setReserveHeight(reserve, 0);
				reserve.remove();
			}
			return;
		}
		reserve ??= createReserveElement();
		if (reserve.parentElement !== target.parentElement || reserve.previousElementSibling !== target) target.after(reserve);
		observers.target(viewport, anchor, target);
		if (setReserveHeight(reserve, computeTopAnchorReserve({
			viewport,
			anchor,
			reserve,
			...clamp
		}))) {
			scheduler.schedule();
			return;
		}
		const anchorId = getAnchorId(anchor);
		const targetScrollTop = snapScrollTop(computeTopAnchorTargetScrollTop({
			viewport,
			anchor,
			...clamp
		}));
		if (anchorId === void 0 || anchorId !== lastScrolledAnchorId) {
			restoreScrollTop = null;
			restoredThisTurn = false;
			if (Math.abs(viewport.scrollTop - targetScrollTop) > 1) viewport.scrollTo({
				top: targetScrollTop,
				behavior: "smooth"
			});
			if (anchorId !== void 0) lastScrolledAnchorId = anchorId;
		} else if (restoreScrollTop !== null && lastAppliedTarget !== null) {
			const desired = snapScrollTop(restoreScrollTop + (targetScrollTop - lastAppliedTarget));
			restoreScrollTop = null;
			restoredThisTurn = true;
			if (Math.abs(viewport.scrollTop - desired) > 1) viewport.scrollTo({
				top: desired,
				behavior: "instant"
			});
		}
		lastAppliedTarget = targetScrollTop;
	}
	const scheduler = createFrameScheduler(apply);
	const observers = createReserveObservers(scheduler.schedule);
	scheduler.schedule();
	const unsubscribe = store.subscribe(scheduler.schedule);
	return () => {
		scheduler.cancel();
		unsubscribe();
		observers.disconnect();
		listenViewport(null);
		reserve?.remove();
	};
};
//#endregion
export { mountTopAnchorReserve };
