/**
 * Returns the ids of the messages in the current thread, in order.
 *
 * The returned array keeps a stable identity across content-only updates (e.g.
 * streaming), changing reference only when the id sequence itself changes. Pair
 * with `ThreadPrimitive.Unstable_MessageById` to drive a virtualized or custom
 * message list.
 *
 * @deprecated Unstable / Experimental - may change in any release.
 */
export declare const unstable_useThreadMessageIds: () => readonly string[];