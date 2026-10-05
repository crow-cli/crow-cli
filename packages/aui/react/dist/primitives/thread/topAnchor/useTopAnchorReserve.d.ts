/**
 * Mounts the top-turn-anchor reserve element against the active
 * `ThreadViewport` store. Call this from inside the scrollable viewport so
 * the reserve `<div>` is appended next to the streaming assistant message.
 */
export declare const useTopAnchorReserve: (enabled: boolean) => void;