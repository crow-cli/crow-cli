"use client";
import { writableStore } from "../../context/ReadonlyStore.js";
import { useMediaQuery } from "../hooks/useMediaQuery.js";
import { useSmoothStatusStore } from "./SmoothContext.js";
import { useEffect, useMemo, useRef, useState } from "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
import { useCallbackRef } from "radix-ui/internal";
//#region src/utils/smooth/useSmooth.ts
const DEFAULT_DRAIN_MS = 250;
const DEFAULT_MAX_CHAR_INTERVAL_MS = 5;
var TextStreamAnimator = class {
	animationFrameId = null;
	lastUpdateTime = Date.now();
	lastCommitTime = 0;
	targetText = "";
	drainMs = DEFAULT_DRAIN_MS;
	maxCharIntervalMs = DEFAULT_MAX_CHAR_INTERVAL_MS;
	maxCharsPerFrame = Infinity;
	minCommitMs = 0;
	currentText;
	setText;
	constructor(currentText, setText) {
		this.currentText = currentText;
		this.setText = setText;
	}
	start() {
		if (this.animationFrameId !== null) return;
		this.lastUpdateTime = Date.now();
		this.animate();
	}
	stop() {
		if (this.animationFrameId !== null) {
			cancelAnimationFrame(this.animationFrameId);
			this.animationFrameId = null;
		}
	}
	animate = () => {
		const currentTime = Date.now();
		let timeToConsume = currentTime - this.lastUpdateTime;
		const remainingChars = this.targetText.length - this.currentText.length;
		const baseTimePerChar = Math.min(this.maxCharIntervalMs, this.drainMs / remainingChars);
		const frameLimit = Math.min(remainingChars, this.maxCharsPerFrame);
		let charsToAdd = 0;
		while (timeToConsume >= baseTimePerChar && charsToAdd < frameLimit) {
			charsToAdd++;
			timeToConsume -= baseTimePerChar;
		}
		if (charsToAdd === frameLimit && frameLimit === this.maxCharsPerFrame) timeToConsume = 0;
		if (charsToAdd !== remainingChars) this.animationFrameId = requestAnimationFrame(this.animate);
		else this.animationFrameId = null;
		if (charsToAdd === 0) return;
		this.currentText = this.targetText.slice(0, this.currentText.length + charsToAdd);
		this.lastUpdateTime = currentTime - timeToConsume;
		if (charsToAdd === remainingChars || currentTime - this.lastCommitTime >= this.minCommitMs) {
			this.lastCommitTime = currentTime;
			this.setText(this.currentText);
		}
	};
};
const SMOOTH_STATUS = Object.freeze({ type: "running" });
const positiveOr = (value, fallback) => value !== void 0 && value > 0 ? value : fallback;
/**
* Animates streamed message part text with a typewriter-style reveal.
*
* Takes the current part state and a `smooth` argument: `false` disables,
* `true` uses the default rate, and a {@link SmoothOptions} object tunes
* the reveal. Returns the part state with `text` replaced by the revealed
* prefix and `status` reporting `running` until the reveal catches up.
* If the source settles before any character has been revealed, the text
* is committed immediately so a missed animation frame cannot leave an
* empty bubble.
*
* The reveal auto-disables under `prefers-reduced-motion: reduce`,
* committing the full text immediately; this takes precedence over an
* explicit `smooth={true}`.
*
* @example
* ```tsx
* const { text, status } = useSmooth(useMessagePartText(), {
*   drainMs: 500,
*   maxCharsPerFrame: 30,
* });
* ```
*/
const useSmooth = (state, smooth = false) => {
	const { text } = state;
	const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
	const options = typeof smooth === "object" && smooth !== null ? smooth : void 0;
	const enabled = smooth !== false && smooth !== null && !reduceMotion;
	const drainMs = positiveOr(options?.drainMs, DEFAULT_DRAIN_MS);
	const maxCharIntervalMs = positiveOr(options?.maxCharIntervalMs, DEFAULT_MAX_CHAR_INTERVAL_MS);
	const maxCharsPerFrame = positiveOr(options?.maxCharsPerFrame, Infinity);
	const minCommitMs = positiveOr(options?.minCommitMs, 0);
	const [displayedText, setDisplayedText] = useState(state.status.type === "running" ? "" : text);
	const aui = useAui();
	const part = useAuiState(() => aui.part);
	const [prevPart, setPrevPart] = useState(part);
	if (part !== prevPart || !text.startsWith(displayedText)) {
		setPrevPart(part);
		setDisplayedText(state.status.type === "running" ? "" : text);
	}
	const smoothStatusStore = useSmoothStatusStore({ optional: true });
	const setText = useCallbackRef((text_0) => {
		setDisplayedText(text_0);
		if (smoothStatusStore) {
			const target = displayedText !== text_0 || state.status.type === "running" ? SMOOTH_STATUS : state.status;
			writableStore(smoothStatusStore).setState(target, true);
		}
	});
	useEffect(() => {
		if (smoothStatusStore) {
			const target_0 = enabled && (displayedText !== text || state.status.type === "running") ? SMOOTH_STATUS : state.status;
			writableStore(smoothStatusStore).setState(target_0, true);
		}
	}, [
		smoothStatusStore,
		enabled,
		text,
		displayedText,
		state.status
	]);
	const [animatorRef] = useState(new TextStreamAnimator(displayedText, setText));
	useEffect(() => {
		animatorRef.drainMs = drainMs;
		animatorRef.maxCharIntervalMs = maxCharIntervalMs;
		animatorRef.maxCharsPerFrame = maxCharsPerFrame;
		animatorRef.minCommitMs = minCommitMs;
	}, [
		animatorRef,
		drainMs,
		maxCharIntervalMs,
		maxCharsPerFrame,
		minCommitMs
	]);
	const animatorPartRef = useRef(part);
	useEffect(() => {
		if (!enabled) {
			animatorRef.stop();
			return;
		}
		const partChanged = animatorPartRef.current !== part;
		animatorPartRef.current = part;
		if (partChanged || !text.startsWith(animatorRef.targetText)) {
			if (state.status.type === "running") {
				animatorRef.currentText = "";
				animatorRef.targetText = text;
				animatorRef.lastCommitTime = 0;
				animatorRef.start();
			} else {
				animatorRef.currentText = text;
				animatorRef.targetText = text;
				animatorRef.stop();
				setText(text);
			}
			return;
		}
		animatorRef.targetText = text;
		if (state.status.type !== "running") {
			if (animatorRef.currentText === "") {
				animatorRef.currentText = text;
				animatorRef.stop();
				setText(text);
				return;
			}
			animatorRef.start();
			return;
		}
		animatorRef.start();
	}, [
		animatorRef,
		enabled,
		text,
		state.status.type,
		part,
		setText
	]);
	useEffect(() => {
		return () => {
			animatorRef.stop();
		};
	}, [animatorRef]);
	return useMemo(() => enabled ? {
		...state,
		text: displayedText,
		status: text === displayedText ? state.status : SMOOTH_STATUS
	} : state, [
		enabled,
		displayedText,
		state,
		text
	]);
};
//#endregion
export { useSmooth };
