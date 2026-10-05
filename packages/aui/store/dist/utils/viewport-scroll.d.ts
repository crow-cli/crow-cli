export type ViewportMetrics = {
    scrollTop: number;
    scrollHeight: number;
    clientHeight: number;
};
/**
 * With a content inset, positions within `contentInset` of the native bottom
 * count as at bottom: content that close is only obscured by the inset
 * element itself, so the viewport is still treated as pinned.
 */
export declare const isViewportAtBottom: (metrics: ViewportMetrics, contentInset?: number) => boolean;
export declare const viewportOverflows: (metrics: ViewportMetrics, contentInset?: number) => boolean;
export declare const isUserScrollUp: (previous: {
    scrollTop: number;
    scrollHeight: number;
}, current: ViewportMetrics) => boolean;
export declare const observeContentResize: (el: HTMLElement, callback: () => void) => (() => void);