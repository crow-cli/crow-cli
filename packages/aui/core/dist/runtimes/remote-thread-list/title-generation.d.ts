export type ThreadTitleClaim = {
    readonly title: string;
    readonly order: number;
    readonly settled: Promise<boolean>;
    readonly settle: (renamed: boolean) => void;
};
type ThreadTitleGeneration = {
    readonly automatic: boolean;
    readonly order: number;
    claim: ThreadTitleClaim | null;
    beforeGenerationClaims: readonly ThreadTitleClaim[];
    superseded: boolean;
    readonly persisted: Promise<string | undefined>;
    readonly settlePersisted: (title: string | undefined) => void;
};
export type ThreadTitleState = {
    generations: Set<ThreadTitleGeneration>;
    pendingClaim: ThreadTitleClaim | null;
    inFlightClaims: Set<ThreadTitleClaim>;
    manualTitle: string | undefined;
    latestExplicit: ThreadTitleGeneration | null;
    nextOrder: number;
};
export type ThreadTitleGenerationRun = {
    states: Map<string, ThreadTitleState>;
    threadId: string;
    automatic: boolean;
    generate: (onTitle: (title: string | undefined) => Promise<void>) => Promise<void>;
    rename: (title: string) => Promise<void>;
    applyTitle: (title: string | undefined) => Promise<void>;
};
export declare function startThreadTitleRename(states: Map<string, ThreadTitleState>, threadId: string, title: string): ThreadTitleClaim;
export declare function finishThreadTitleRename(states: Map<string, ThreadTitleState>, threadId: string, claim: ThreadTitleClaim, renamed: boolean): void;
export declare function clearThreadTitleState(states: Map<string, ThreadTitleState>, threadId: string): void;
/**
 * Runs one title generation under the per-thread rename claims and generation
 * ordering, so the title that wins locally is also the title left on the
 * server.
 *
 * A generated run persists the title itself, and the adapter exposes no
 * compare-and-set, so the run that loses reasserts the winner through `rename`
 * only after `generate` has resolved. Reasserting mid-stream would race the
 * run's own write and lose the winning title on the server.
 */
export declare function runThreadTitleGeneration({ states, threadId, automatic, generate, rename, applyTitle, }: ThreadTitleGenerationRun): Promise<void>;
export {};