export declare const isThenable: (value: unknown) => value is PromiseLike<unknown>;
export declare const trackThenable: <T>(thenable: PromiseLike<T>) => T;