import { type RefObject } from "react";
/**
 * Marker set on the scroll container for as long as a lock holds its position.
 *
 * An auto-scroller sharing that container reads it to tell the lock's own
 * writes from a user's: a locked viewport that moves up is an animation being
 * held still, not somebody scrolling away, and misreading it costs the rest of
 * the turn's follow-to-bottom.
 */
export declare const SCROLL_LOCK_ATTRIBUTE = "data-aui-scroll-lock";
/**
 * Locks scroll position during collapsible/height animations and hides scrollbar.
 *
 * This utility prevents page jumps when content height changes during animations,
 * providing a smooth user experience. It finds the nearest scrollable ancestor and
 * temporarily locks its scroll position while the animation completes.
 *
 * - Prevents forced reflows: mutations scoped to scrollable parent only
 * - Reactive: only intercepts scroll events when browser actually adjusts
 * - Yields to growing content and to user gestures, so it never fights an
 *   auto-scroller that is following a stream
 * - Cleans up automatically after animation duration
 *
 * @param animatedElementRef - Ref to the animated element
 * @param animationDuration - Lock duration in milliseconds
 * @returns Function to activate the scroll lock
 *
 * @example
 * ```tsx
 * const collapsibleRef = useRef<HTMLDivElement>(null);
 * const lockScroll = useScrollLock(collapsibleRef, 200);
 *
 * const handleCollapse = () => {
 *   lockScroll(); // Lock scroll before collapsing
 *   setIsOpen(false);
 * };
 * ```
 */
export declare const useScrollLock: <T extends HTMLElement = HTMLElement>(animatedElementRef: RefObject<T | null>, animationDuration: number) => () => void;