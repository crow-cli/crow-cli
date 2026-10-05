//#region src/utils/viewport-scroll.ts
/**
* With a content inset, positions within `contentInset` of the native bottom
* count as at bottom: content that close is only obscured by the inset
* element itself, so the viewport is still treated as pinned.
*/
const isViewportAtBottom = (metrics, contentInset = 0) => {
	if (contentInset === 0) return Math.abs(metrics.scrollHeight - metrics.scrollTop - metrics.clientHeight) <= 1 || metrics.scrollHeight <= metrics.clientHeight;
	return metrics.scrollHeight - contentInset - metrics.scrollTop - metrics.clientHeight <= 1 || metrics.scrollHeight - contentInset <= metrics.clientHeight;
};
const viewportOverflows = (metrics, contentInset = 0) => {
	if (contentInset === 0) return metrics.scrollHeight > metrics.clientHeight + 1;
	return metrics.scrollHeight - contentInset > metrics.clientHeight + 1;
};
const isUserScrollUp = (previous, current) => previous.scrollTop > current.scrollTop && previous.scrollHeight === current.scrollHeight;
const observeContentResize = (el, callback) => {
	const disposers = [];
	if (typeof ResizeObserver !== "undefined") {
		const resizeObserver = new ResizeObserver(() => callback());
		resizeObserver.observe(el);
		disposers.push(() => resizeObserver.disconnect());
	}
	if (typeof MutationObserver !== "undefined") {
		const mutationObserver = new MutationObserver((mutations) => {
			if (mutations.some((mutation) => mutation.type !== "attributes" || mutation.attributeName !== "style")) callback();
		});
		mutationObserver.observe(el, {
			childList: true,
			subtree: true,
			attributes: true,
			characterData: true
		});
		disposers.push(() => mutationObserver.disconnect());
	}
	return () => {
		for (const dispose of disposers) dispose();
	};
};
//#endregion
export { isUserScrollUp, isViewportAtBottom, observeContentResize, viewportOverflows };
