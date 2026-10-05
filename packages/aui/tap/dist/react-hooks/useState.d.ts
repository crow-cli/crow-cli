export declare namespace useState {
    type StateUpdater<S> = S | ((prev: S) => S);
}
export declare function useState<S = undefined>(): [
    S | undefined,
    (updater: useState.StateUpdater<S>) => void
];
export declare function useState<S>(initial: S | (() => S)): [S, (updater: useState.StateUpdater<S>) => void];