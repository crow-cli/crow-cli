import type { Unsubscribe } from "@assistant-ui/core";
export type SizeHandle = {
    /** Update the height */
    setHeight: (height: number) => void;
    /** Unregister this handle */
    unregister: Unsubscribe;
};
export type ThreadViewportState = {
    readonly isAtBottom: boolean;
    readonly scrollToBottom: (config?: {
        behavior?: ScrollBehavior | undefined;
    }) => void;
    readonly onScrollToBottom: (callback: ({ behavior }: {
        behavior: ScrollBehavior;
    }) => void) => Unsubscribe;
    /** Controls scroll anchoring: "top" anchors user messages at top, "bottom" is classic behavior */
    readonly turnAnchor: "top" | "bottom";
    /** Clamps tall user messages so the assistant response stays in view. */
    readonly topAnchorMessageClamp: {
        readonly tallerThan: string;
        readonly visibleHeight: string;
    };
    /** Raw height values from registered elements */
    readonly height: {
        /** Total viewport height */
        readonly viewport: number;
        /** Total content inset height (footer, anchor message, etc.) */
        readonly inset: number;
    };
    /** Current DOM elements used for geometry-based top anchoring */
    readonly element: {
        readonly viewport: HTMLElement | null;
        readonly anchor: HTMLElement | null;
        readonly target: HTMLElement | null;
    };
    /** Numeric clamp configuration for the active top-anchor target message */
    readonly targetConfig: {
        readonly tallerThan: number;
        readonly visibleHeight: number;
    } | null;
    /**
     * The current top-anchor turn activated in this viewport session.
     * History-loaded messages do not populate this; it is set when a run creates
     * a live user/assistant pair and remains after the run completes.
     */
    readonly topAnchorTurn: {
        readonly anchorId: string;
        readonly targetId: string;
    } | null;
    /** Register a viewport and get a handle to update its height */
    readonly registerViewport: () => SizeHandle;
    /** Register a content inset (footer, anchor message, etc.) and get a handle to update its height */
    readonly registerContentInset: () => SizeHandle;
    /** Register the scroll viewport element */
    readonly registerViewportElement: (element: HTMLElement | null) => Unsubscribe;
    /** Register the current anchor user message element */
    readonly registerAnchorElement: (element: HTMLElement | null) => Unsubscribe;
    /**
     * Register the current top-anchor target (last assistant response) element
     * along with its numeric clamp configuration. When unregistered, both
     * `element.target` and `targetConfig` clear together.
     */
    readonly registerAnchorTargetElement: (element: HTMLElement | null, config?: {
        readonly tallerThan: number;
        readonly visibleHeight: number;
    }) => Unsubscribe;
    readonly setTopAnchorTurn: (turn: {
        readonly anchorId: string;
        readonly targetId: string;
    } | null) => void;
};
export type ThreadViewportStoreOptions = {
    turnAnchor?: "top" | "bottom" | undefined;
    topAnchorMessageClamp?: {
        tallerThan?: string | undefined;
        visibleHeight?: string | undefined;
    } | undefined;
};
export declare const makeThreadViewportStore: (options?: ThreadViewportStoreOptions) => import("zustand").UseBoundStore<import("zustand").StoreApi<ThreadViewportState>>;