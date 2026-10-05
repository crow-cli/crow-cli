export type ComputeTopAnchorTargetOptions = {
    viewport: HTMLElement;
    anchor: HTMLElement;
    tallerThan: number;
    visibleHeight: number;
};
export type ComputeTopAnchorReserveOptions = ComputeTopAnchorTargetOptions & {
    reserve: HTMLElement;
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
export declare const computeTopAnchorTargetScrollTop: ({ viewport, anchor, tallerThan, visibleHeight, }: ComputeTopAnchorTargetOptions) => number;
export declare const computeTopAnchorReserve: ({ viewport, reserve, ...targetOptions }: ComputeTopAnchorReserveOptions) => number;