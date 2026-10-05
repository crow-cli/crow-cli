import { BaseSubscribable } from "../../subscribable/subscribable.js";
type Transform<TState, TResult> = {
    execute: () => Promise<TResult>;
    /** transform the state after the promise resolves */
    then?: (state: TState, result: TResult) => TState;
    /** transform the state during resolution and afterwards */
    optimistic?: (state: TState) => TState;
    /** transform the state only while loading */
    loading?: (state: TState, task: Promise<TResult>) => TState;
};
export declare class OptimisticState<TState> extends BaseSubscribable {
    private readonly _pendingTransforms;
    /**
     * Completed optimistic callbacks stay applied on top of the base value while
     * any transform is pending, so a state replacement made meanwhile cannot hide
     * them. They are dropped when the last transform settles, so `update()` must
     * be given a state that already contains the completed effects, such as one
     * derived from `baseValue`. While transforms are pending, callbacks apply
     * in invocation order. A transform that settles with `then` has every
     * completed callback replayed over its result, so an earlier-invoked update
     * can win over it.
     *
     * Correctness requirement: `optimistic` callbacks must be idempotent.
     */
    private readonly _completedOptimistics;
    private _nextTransformOrder;
    private _epoch;
    private _baseValue;
    private _cachedValue;
    constructor(initialState: TState);
    private _updateState;
    get baseValue(): TState;
    get value(): TState;
    update(state: TState): void;
    reset(state: TState): void;
    optimisticUpdate<TResult>(transform: Transform<TState, TResult>): Promise<TResult>;
}
export {};