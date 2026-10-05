"use client";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect, useRef } from "@assistant-ui/tap/react-shim";
//#region src/primitives/reasoning/useScrollLock.ts
const findScrollableAncestor = (element) => {
	let current = element;
	while (current) {
		const { overflowY } = getComputedStyle(current);
		if (overflowY === "scroll" || overflowY === "auto") return current;
		current = current.parentElement;
	}
	return null;
};
/**
* Marker set on the scroll container for as long as a lock holds its position.
*
* An auto-scroller sharing that container reads it to tell the lock's own
* writes from a user's: a locked viewport that moves up is an animation being
* held still, not somebody scrolling away, and misreading it costs the rest of
* the turn's follow-to-bottom.
*/
const SCROLL_LOCK_ATTRIBUTE = "data-aui-scroll-lock";
const SCROLL_KEYS = /* @__PURE__ */ new Set([
	" ",
	"Spacebar",
	"Enter",
	"ArrowUp",
	"ArrowDown",
	"ArrowLeft",
	"ArrowRight",
	"PageUp",
	"PageDown",
	"Home",
	"End"
]);
const TEXT_ENTRY_TAGS = /* @__PURE__ */ new Set([
	"INPUT",
	"TEXTAREA",
	"SELECT"
]);
const GESTURE_EVENTS = [
	"wheel",
	"touchstart",
	"pointerdown",
	"keydown"
];
/**
* Locks scroll position during collapsible/height animations and hides scrollbar.
*
* This utility prevents page jumps when content height changes during animations,
* providing a smooth user experience. It finds the nearest scrollable ancestor and
* temporarily locks its scroll position while the animation completes.
*
* - Prevents forced reflows: mutations scoped to scrollable parent only
* - Reactive: only intercepts scroll events when browser actually adjusts
* - Yields to growing content and to user gestures, so it never fights an
*   auto-scroller that is following a stream
* - Cleans up automatically after animation duration
*
* @param animatedElementRef - Ref to the animated element
* @param animationDuration - Lock duration in milliseconds
* @returns Function to activate the scroll lock
*
* @example
* ```tsx
* const collapsibleRef = useRef<HTMLDivElement>(null);
* const lockScroll = useScrollLock(collapsibleRef, 200);
*
* const handleCollapse = () => {
*   lockScroll(); // Lock scroll before collapsing
*   setIsOpen(false);
* };
* ```
*/
const useScrollLock = (animatedElementRef, animationDuration) => {
	const $ = c(5);
	const cleanupRef = useRef(null);
	let t0;
	let t1;
	if ($[0] === Symbol.for("react.memo_cache_sentinel")) {
		t0 = () => () => {
			cleanupRef.current?.();
		};
		t1 = [];
		$[0] = t0;
		$[1] = t1;
	} else {
		t0 = $[0];
		t1 = $[1];
	}
	useEffect(t0, t1);
	let t2;
	if ($[2] !== animatedElementRef || $[3] !== animationDuration) {
		t2 = () => {
			cleanupRef.current?.();
			const scrollContainer = findScrollableAncestor(animatedElementRef.current);
			if (!scrollContainer) {
				cleanupRef.current = null;
				return;
			}
			let scrollPosition = scrollContainer.scrollTop;
			let lockedScrollHeight = scrollContainer.scrollHeight;
			const scrollbarWidth = scrollContainer.style.scrollbarWidth;
			const computed = getComputedStyle(scrollContainer);
			const paddingSide = computed.direction === "rtl" ? "paddingLeft" : "paddingRight";
			const previousPadding = scrollContainer.style[paddingSide];
			const elementScrollbarSize = scrollContainer.offsetWidth - scrollContainer.clientWidth - parseFloat(computed.borderLeftWidth) - parseFloat(computed.borderRightWidth);
			const ownerDocument = scrollContainer.ownerDocument;
			const scrollbarSize = (scrollContainer === ownerDocument.documentElement || scrollContainer === ownerDocument.body) && elementScrollbarSize <= 0 ? (ownerDocument.defaultView?.innerWidth ?? 0) - ownerDocument.documentElement.clientWidth : elementScrollbarSize;
			scrollContainer.style.scrollbarWidth = "none";
			if (scrollbarSize > 0) scrollContainer.style[paddingSide] = `${parseFloat(computed[paddingSide]) + scrollbarSize}px`;
			const restoreStyles = () => {
				scrollContainer.style.scrollbarWidth = scrollbarWidth;
				scrollContainer.style[paddingSide] = previousPadding;
			};
			const resetPosition = () => {
				const { scrollHeight, scrollTop } = scrollContainer;
				if (scrollHeight > lockedScrollHeight) {
					lockedScrollHeight = scrollHeight;
					scrollPosition = scrollTop;
					return;
				}
				scrollContainer.scrollTop = scrollPosition;
			};
			let timeoutId;
			const release = (gesture) => {
				if (gesture?.type === "keydown") {
					const { key, target } = gesture;
					if (!SCROLL_KEYS.has(key)) return;
					const element = target;
					if (element?.isContentEditable || TEXT_ENTRY_TAGS.has(element?.tagName ?? "")) return;
				}
				clearTimeout(timeoutId);
				scrollContainer.removeEventListener("scroll", resetPosition);
				for (const type of GESTURE_EVENTS) scrollContainer.removeEventListener(type, release);
				scrollContainer.removeAttribute(SCROLL_LOCK_ATTRIBUTE);
				restoreStyles();
				cleanupRef.current = null;
			};
			scrollContainer.addEventListener("scroll", resetPosition);
			for (const type_0 of GESTURE_EVENTS) scrollContainer.addEventListener(type_0, release, { passive: true });
			scrollContainer.setAttribute(SCROLL_LOCK_ATTRIBUTE, "");
			timeoutId = setTimeout(release, animationDuration);
			cleanupRef.current = release;
		};
		$[2] = animatedElementRef;
		$[3] = animationDuration;
		$[4] = t2;
	} else t2 = $[4];
	return t2;
};
//#endregion
export { SCROLL_LOCK_ATTRIBUTE, useScrollLock };
