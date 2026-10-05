/**
 * Emits `threads.selectionChanged` whenever the main thread selection changes.
 * Does not emit for the initially selected thread on mount. Every `threads`
 * client whose selection can change calls this with its current main thread id.
 */
export declare const useThreadSelectionEvents: (mainThreadId: string) => void;
/**
 * Emits `threadListItem.switchedTo` or `threadListItem.switchedAway` from a
 * thread list item's own scope when its thread gains or loses the main
 * selection. Emitting after the commit delivers against the rebound derived
 * scopes; a synchronous notification would reach the pre-switch binding.
 * `wasMain` is whether the thread held the selection before this item
 * mounted, so an item created and selected in one update reports the switch.
 */
export declare const useThreadListItemSelectionEvents: (threadId: string, isMain: boolean, wasMain?: boolean) => void;