"use client";
//#region src/primitives/thread/topAnchor/computeTopAnchorSlack.ts
const getDocumentOffsetTop = (element) => {
	let top = 0;
	let current = element;
	while (current) {
		top += current.offsetTop;
		current = current.offsetParent;
	}
	return top;
};
const getLayoutOffsetTop = (element, ancestor) => {
	let top = 0;
	let current = element;
	while (current && current !== ancestor) {
		top += current.offsetTop;
		current = current.offsetParent;
	}
	if (current === ancestor) return top;
	return getDocumentOffsetTop(element) - getDocumentOffsetTop(ancestor);
};
/**
* Compute the scroll position that pins the anchor (last user message) to the
* top of the viewport. For tall user messages the anchor is intentionally
* over-scrolled so only `visibleHeight` of it remains visible, leaving room
* for the assistant message below.
*
* Depends only on the anchor's offset within the scroll content; never reads
* `viewport.scrollHeight` (which is volatile while the assistant message
* streams in).
*/
const computeTopAnchorTargetScrollTop = ({ viewport, anchor, tallerThan, visibleHeight }) => {
	const anchorTop = getLayoutOffsetTop(anchor, viewport);
	const anchorHeight = anchor.offsetHeight;
	return anchorTop + Math.max(0, anchorHeight - (anchorHeight <= tallerThan ? anchorHeight : visibleHeight));
};
const computeTopAnchorSlack = ({ scrollHeight, ...targetOptions }) => {
	const { viewport } = targetOptions;
	const targetScrollHeight = computeTopAnchorTargetScrollTop(targetOptions) + viewport.clientHeight;
	return Math.max(0, targetScrollHeight - scrollHeight);
};
const computeTopAnchorReserve = ({ viewport, reserve, ...targetOptions }) => {
	return computeTopAnchorSlack({
		viewport,
		...targetOptions,
		scrollHeight: viewport.scrollHeight - reserve.offsetHeight
	});
};
//#endregion
export { computeTopAnchorReserve, computeTopAnchorTargetScrollTop };
