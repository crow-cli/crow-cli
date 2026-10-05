import type { SizeHandle } from "../../context/stores/ThreadViewport.js";
/**
 * Hook that creates a ref for tracking element size via a SizeHandle.
 * Automatically sets up ResizeObserver and reports height changes.
 *
 * @param register - Function that returns a SizeHandle (e.g., registerContentInset)
 * @param getHeight - Optional function to compute height (defaults to el.offsetHeight)
 * @returns A ref callback to attach to the element
 */
export declare const useSizeHandle: (register: (() => SizeHandle) | null | undefined, getHeight?: (el: HTMLElement) => number) => (el: HTMLElement | null) => void;