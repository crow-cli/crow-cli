/**
 * Minimal slice of `ThreadViewportStore` that the top-anchor reserve needs.
 * Decoupling from the full store keeps `mountTopAnchorReserve` testable in
 * isolation and re-usable from any consumer that can adapt to this shape.
 */
export type TopAnchorStore = {
    getState(): {
        turnAnchor: "top" | "bottom";
        element: {
            viewport: HTMLElement | null;
            anchor: HTMLElement | null;
            target: HTMLElement | null;
        };
        targetConfig: {
            tallerThan: number;
            visibleHeight: number;
        } | null;
        topAnchorTurn: {
            readonly anchorId: string;
            readonly targetId: string;
        } | null;
    };
    subscribe(fn: () => void): () => void;
};
export declare const mountTopAnchorReserve: (store: TopAnchorStore) => () => void;