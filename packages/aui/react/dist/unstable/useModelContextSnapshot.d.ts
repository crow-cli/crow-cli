import type { AssistantClient } from "@assistant-ui/store";
import type { Unsubscribe } from "@assistant-ui/core";
/**
 * Where a snapshot comes from and what counts as a change to it. Declared once
 * per consumer at module scope: the subscription effect keys on this object, so
 * an inline source without an `isEqual` re-reads itself into a render loop.
 */
export type ModelContextSnapshotSource<T> = {
    /** Seeds the snapshot when it starts disabled. */
    readonly empty: T;
    /** Projects the fields the consumer observes out of the live model context. */
    read(aui: AssistantClient): T;
    subscribe(aui: AssistantClient, onChange: () => void): Unsubscribe;
    /**
     * An equal pair keeps the previous reference. Omitted by a consumer that
     * re-derives on every notification, where a caller republishing an unchanged
     * tool set is how it asks to be re-run.
     */
    isEqual?(previous: T, next: T): boolean;
};
/**
 * `getModelContext()` rebuilds its result on every call, so a projection of the
 * fields a consumer observes is held in state and refreshed on notification
 * rather than read during render. Keeping the previous reference for an equal
 * projection is what stops a notification carrying no observable change from
 * invalidating everything derived from it.
 */
export declare const useModelContextSnapshot: <T>(aui: AssistantClient, enabled: boolean, source: ModelContextSnapshotSource<T>) => T;
/** Shallow own-key comparison, for a projection whose values are records. */
export declare const shallowEqualRecords: (previous: Readonly<Record<string, unknown>>, next: Readonly<Record<string, unknown>>) => boolean;