type Dispatch<A> = (action: A) => void;
export declare function useReducerImpl<S, A, I>(reducer: (state: S, action: A) => S, initialArg: S | I, initFn: ((arg: I) => S) | undefined, eagerBailout: boolean): [S, Dispatch<A>];
export declare function useReducer<S>(reducer: (state: S) => S, initialState: S): [S, () => void];
export declare function useReducer<S, I>(reducer: (state: S) => S, initialArg: I, init: (arg: I) => S): [S, () => void];
export declare function useReducer<S, A>(reducer: (state: S, action: A) => S, initialState: S): [S, Dispatch<A>];
export declare function useReducer<S, A, I>(reducer: (state: S, action: A) => S, initialArg: I, init: (arg: I) => S): [S, Dispatch<A>];
export {};