"use client";
//#region src/primitives/thread/topAnchor/topAnchorUtils.ts
/**
* Convert a supported CSS length string (`px`, `em`, `rem`) into pixels,
* resolving font-relative units against the supplied element's computed style.
* Unsupported or malformed values disable the tall-message clamp.
*
* Part of the top-anchor package's public input contract: consumers may pass
* clamp configuration as supported CSS-length strings, and this function is the
* single place that converts them into the pixel values the package operates on.
*/
const parseCssLength = (value, element) => {
	const match = value.trim().match(/^(\d+(?:\.\d+)?|\.\d+)(em|px|rem)$/);
	if (!match) return Number.POSITIVE_INFINITY;
	const num = Number(match[1]);
	const unit = match[2];
	if (unit === "px") return num;
	if (unit === "em") return num * (parseFloat(getComputedStyle(element).fontSize) || 16);
	if (unit === "rem") return num * (parseFloat(getComputedStyle(document.documentElement).fontSize) || 16);
	return Number.POSITIVE_INFINITY;
};
const getAnchorId = (anchor) => anchor.dataset.messageId;
const createReserveElement = () => {
	const reserve = document.createElement("div");
	reserve.dataset.auiTopAnchorReserve = "";
	reserve.style.height = "0px";
	reserve.style.flexShrink = "0";
	reserve.style.pointerEvents = "none";
	reserve.setAttribute("aria-hidden", "true");
	return reserve;
};
const setReserveHeight = (reserve, height) => {
	const nextHeight = `${height}px`;
	if (reserve.style.height !== nextHeight) {
		reserve.style.height = nextHeight;
		return true;
	}
	return false;
};
const snapScrollTop = (top) => {
	const pixelRatio = window.devicePixelRatio || 1;
	return Math.round(top * pixelRatio) / pixelRatio;
};
//#endregion
export { createReserveElement, getAnchorId, parseCssLength, setReserveHeight, snapScrollTop };
