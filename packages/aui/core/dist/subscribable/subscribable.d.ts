import type { Unsubscribe } from "../types/unsubscribe.js";
export declare const SKIP_UPDATE: unique symbol;
export type SKIP_UPDATE = typeof SKIP_UPDATE;
export type Subscribable = {
    subscribe: (callback: () => void) => Unsubscribe;
};
export type SubscribableWithState<TState, TPath> = Subscribable & {
    path: TPath;
    getState: () => TState;
};
export type NestedSubscribable<TState extends Subscribable | undefined, TPath> = SubscribableWithState<TState, TPath>;
export type EventSubscribable<TEvent extends string> = {
    event: TEvent;
    binding: SubscribableWithState<{
        unstable_on: (event: TEvent, callback: (payload?: unknown) => void) => Unsubscribe;
    } | undefined, unknown>;
    /**
     * Notifies subscribers with an empty payload when the binding swaps to a
     * different source. For an event that reports a change to a value read off
     * the source rather than an occurrence in time, the swap is itself such a
     * change, and the previous source never announces it.
     */
    notifyOnRebind?: boolean;
};
export declare const notifySubscribers: <TArgs extends unknown[]>(subscribers: Iterable<(...args: TArgs) => void>, ...args: TArgs) => void;
export declare const runCleanups: (cleanups: Iterable<Unsubscribe>) => void;
export declare class BaseSubscribable {
    private _subscribers;
    subscribe(callback: () => void): Unsubscribe;
    waitForUpdate(): Promise<void>;
    protected _notifySubscribers(): void;
}
export declare class WritableSubscribable<TState> extends BaseSubscribable {
    private _state;
    constructor(state: TState);
    getState(): TState;
    getServerSnapshot: () => TState;
    setState(state: TState): void;
}
export declare abstract class BaseSubject {
    private _subscriptions;
    private _connection;
    protected get isConnected(): boolean;
    protected abstract _connect(): Unsubscribe;
    protected notifySubscribers(payload?: unknown, errorContext?: string): void;
    private _updateConnection;
    subscribe(callback: (payload?: unknown) => void): () => void;
}
export declare class ShallowMemoizeSubject<TState extends object, TPath> extends BaseSubject implements SubscribableWithState<TState, TPath> {
    get path(): TPath;
    private binding;
    constructor(binding: SubscribableWithState<TState | SKIP_UPDATE, TPath>);
    private _previousState;
    getState: () => TState;
    private _syncState;
    protected _connect(): Unsubscribe;
}
export declare class LazyMemoizeSubject<TState extends object, TPath> extends BaseSubject implements SubscribableWithState<TState, TPath> {
    get path(): TPath;
    private binding;
    constructor(binding: SubscribableWithState<TState | SKIP_UPDATE, TPath>);
    private _previousStateDirty;
    private _previousState;
    getState: () => TState;
    protected _connect(): Unsubscribe;
}
export declare class NestedSubscriptionSubject<TState extends Subscribable | undefined, TPath> extends BaseSubject implements SubscribableWithState<TState, TPath>, NestedSubscribable<TState, TPath> {
    get path(): TPath;
    private binding;
    constructor(binding: NestedSubscribable<TState, TPath>);
    getState(): TState;
    outerSubscribe(callback: () => void): Unsubscribe;
    protected _connect(): Unsubscribe;
}
export declare class EventSubscriptionSubject<TEvent extends string> extends BaseSubject {
    private config;
    constructor(config: EventSubscribable<TEvent>);
    getState(): {
        unstable_on: (event: TEvent, callback: (payload?: unknown) => void) => Unsubscribe;
    } | undefined;
    outerSubscribe(callback: () => void): Unsubscribe;
    protected _connect(): Unsubscribe;
}