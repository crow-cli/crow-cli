"use client";
import { useThreadViewportStore } from "../../context/react/ThreadViewportContext.js";
import { writableStore } from "../../context/ReadonlyStore.js";
import { useOnScrollToBottom } from "../../utils/hooks/useOnScrollToBottom.js";
import { useManagedRef } from "../../utils/hooks/useManagedRef.js";
import { useOnResizeContent } from "../../utils/hooks/useOnResizeContent.js";
import "../reasoning/useScrollLock.js";
import { useCallback, useLayoutEffect, useRef } from "@assistant-ui/tap/react-shim";
import { useAuiEvent, useAuiState } from "@assistant-ui/store";
import { useComposedRefs } from "radix-ui/internal";
import { isUserScrollUp, isViewportAtBottom, viewportOverflows } from "@assistant-ui/store/client";
//#region src/primitives/thread/useThreadViewportAutoScroll.ts
const ACTIVATION_KEYS = /* @__PURE__ */ new Set(["Enter", " "]);
const TEXT_ENTRY_SELECTOR = [
	"textarea",
	"select",
	"[contenteditable]:not([contenteditable='false'])",
	"input:not([type='checkbox']):not([type='radio']):not([type='button']):not([type='submit']):not([type='reset']):not([type='image']):not([type='range']):not([type='file']):not([type='color'])"
].join(", ");
const useThreadViewportAutoScroll = ({ autoScroll, scrollToBottomOnRunStart = true, scrollToBottomOnInitialize = true, scrollToBottomOnThreadSwitch = true }) => {
	const divRef = useRef(null);
	const hasMessages = useAuiState((s) => s.thread.messages.length > 0);
	const isRunning = useAuiState((s_0) => s_0.thread.isRunning);
	const initializeScrollRequestedRef = useRef(false);
	const scheduledFrameRef = useRef(null);
	const threadViewportStore = useThreadViewportStore();
	if (autoScroll === void 0) autoScroll = threadViewportStore.getState().turnAnchor !== "top";
	const lastScrollTop = useRef(0);
	const lastScrollHeight = useRef(0);
	const lastObservedScrollHeight = useRef(0);
	const lastObservedClientHeight = useRef(0);
	const scrollingToBottomBehaviorRef = useRef(null);
	const followBottomRef = useRef(autoScroll);
	const previousAutoScrollRef = useRef(autoScroll);
	useLayoutEffect(() => {
		const previousAutoScroll = previousAutoScrollRef.current;
		previousAutoScrollRef.current = autoScroll;
		if (previousAutoScroll || !autoScroll) return;
		const div = divRef.current;
		followBottomRef.current = div !== null && isViewportAtBottom(div);
	}, [autoScroll]);
	const scrollToBottom = useCallback((behavior) => {
		const div_0 = divRef.current;
		if (!div_0) return;
		followBottomRef.current = true;
		scrollingToBottomBehaviorRef.current = behavior;
		div_0.scrollTo({
			top: div_0.scrollHeight,
			behavior
		});
	}, []);
	const cancelScheduledFrame = useCallback(() => {
		if (scheduledFrameRef.current === null) return;
		cancelAnimationFrame(scheduledFrameRef.current);
		scheduledFrameRef.current = null;
	}, []);
	const scheduleScrollToBottom = useCallback((behavior_0) => {
		scrollingToBottomBehaviorRef.current = behavior_0;
		cancelScheduledFrame();
		scheduledFrameRef.current = requestAnimationFrame(() => {
			scheduledFrameRef.current = null;
			scrollToBottom(behavior_0);
		});
	}, [cancelScheduledFrame, scrollToBottom]);
	useLayoutEffect(() => () => cancelScheduledFrame(), [cancelScheduledFrame]);
	const hasActiveTopAnchor = useCallback(() => {
		const state = threadViewportStore.getState();
		return state.turnAnchor === "top" && state.element.viewport === divRef.current && state.element.anchor !== null;
	}, [threadViewportStore]);
	const handleScroll = () => {
		const div_1 = divRef.current;
		if (!div_1) return;
		const isAtBottom = threadViewportStore.getState().isAtBottom;
		const newIsAtBottom = isViewportAtBottom(div_1);
		if (!newIsAtBottom && lastScrollTop.current < div_1.scrollTop) {} else {
			const userScrolledUp = !div_1.hasAttribute("data-aui-scroll-lock") && isUserScrollUp({
				scrollTop: lastScrollTop.current,
				scrollHeight: lastScrollHeight.current
			}, div_1);
			if (newIsAtBottom) {
				if (viewportOverflows(div_1)) scrollingToBottomBehaviorRef.current = null;
				if (autoScroll) followBottomRef.current = true;
			} else if (userScrolledUp) {
				cancelScheduledFrame();
				scrollingToBottomBehaviorRef.current = null;
				followBottomRef.current = false;
			}
			if ((newIsAtBottom || scrollingToBottomBehaviorRef.current === null) && newIsAtBottom !== isAtBottom) writableStore(threadViewportStore).setState({ isAtBottom: newIsAtBottom });
		}
		lastScrollTop.current = div_1.scrollTop;
		lastScrollHeight.current = div_1.scrollHeight;
	};
	const resizeRef = useOnResizeContent(() => {
		const div_2 = divRef.current;
		if (!div_2) return;
		const { scrollHeight, clientHeight } = div_2;
		if (scrollHeight === lastObservedScrollHeight.current && clientHeight === lastObservedClientHeight.current) return;
		lastObservedScrollHeight.current = scrollHeight;
		lastObservedClientHeight.current = clientHeight;
		const scrollBehavior = scrollingToBottomBehaviorRef.current;
		if (scrollBehavior && hasActiveTopAnchor()) scrollingToBottomBehaviorRef.current = null;
		else if (scrollBehavior) scrollToBottom(scrollBehavior);
		else if (autoScroll && !(isRunning && hasActiveTopAnchor()) && followBottomRef.current) scrollToBottom("instant");
		handleScroll();
	});
	const scrollRef = useManagedRef((el) => {
		const cancelPendingScrollToBottom = () => {
			cancelScheduledFrame();
			scrollingToBottomBehaviorRef.current = null;
		};
		const cancelOnKeyDown = (event) => {
			if (!ACTIVATION_KEYS.has(event.key)) return;
			if (event.target?.closest?.(TEXT_ENTRY_SELECTOR)) return;
			cancelPendingScrollToBottom();
		};
		el.addEventListener("scroll", handleScroll);
		el.addEventListener("pointerdown", cancelPendingScrollToBottom);
		el.addEventListener("keydown", cancelOnKeyDown);
		return () => {
			el.removeEventListener("scroll", handleScroll);
			el.removeEventListener("pointerdown", cancelPendingScrollToBottom);
			el.removeEventListener("keydown", cancelOnKeyDown);
		};
	});
	useLayoutEffect(() => {
		if (!scrollToBottomOnInitialize) return;
		if (!hasMessages) {
			initializeScrollRequestedRef.current = false;
			return;
		}
		if (initializeScrollRequestedRef.current) return;
		initializeScrollRequestedRef.current = true;
		if (scrollingToBottomBehaviorRef.current !== null) return;
		scheduleScrollToBottom("instant");
	}, [
		hasMessages,
		scheduleScrollToBottom,
		scrollToBottomOnInitialize
	]);
	useOnScrollToBottom(({ behavior: behavior_1 }) => {
		scrollToBottom(behavior_1);
	});
	useAuiEvent("thread.runStart", () => {
		if (!scrollToBottomOnRunStart) return;
		if (threadViewportStore.getState().turnAnchor === "top") return;
		scheduleScrollToBottom("auto");
	});
	useAuiEvent("threads.selectionChanged", () => {
		if (!scrollToBottomOnThreadSwitch) return;
		scheduleScrollToBottom("instant");
	});
	return useComposedRefs(resizeRef, scrollRef, divRef);
};
//#endregion
export { useThreadViewportAutoScroll };
