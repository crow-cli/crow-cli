import { useRef as useTapRef } from "../react-hooks/useRef.js";
export declare const useState: (initialState?: any) => [any, (updater: any) => void];
export declare const useReducer: (reducer: any, initialArg: any, init?: any) => [unknown, () => void];
export declare const useRef: (initialValue?: any) => useTapRef.RefObject<any>;
export declare const useMemo: (factory: any, deps: any) => unknown;
export declare const useCallback: (callback: any, deps: any) => any;
export declare const useEffect: (effect: any, deps?: any) => void;
export declare const useLayoutEffect: (effect: any, deps?: any) => void;
export declare const useInsertionEffect: (effect: any, deps?: any) => void;
export declare const useEffectEvent: (callback: any) => any;
export declare const useSyncExternalStore: (subscribe: any, getSnapshot: any, getServerSnapshot?: any) => unknown;
export declare const useDebugValue: (value: any, format?: any) => void;
export declare const useId: () => string;
export declare const useImperativeHandle: (ref: any, create: any, deps?: any) => void;
export declare const createContext: (defaultValue: any) => any;
export declare const use: (usable: any) => unknown;
export declare const useContext: (context: any) => unknown;
export declare const forwardRef: (render: any) => {
    $$typeof: symbol;
    render: any;
};
export declare const memo: (type: any, compare?: any) => {
    $$typeof: symbol;
    type: any;
    compare: any;
};
export declare const Fragment: unique symbol;
export declare const createElement: () => never;
export declare const cloneElement: () => never;
export declare const isValidElement: (_value: unknown) => boolean;
export declare const lazy: (load: any) => {
    $$typeof: symbol;
    _payload: {
        _status: number;
        _result: any;
    };
    _init: () => never;
};
export declare const Children: {
    map: () => never;
    forEach: () => never;
    count: () => never;
    toArray: () => never;
    only: () => never;
};
export declare const Suspense: unique symbol;
export declare const useDeferredValue: () => never;
declare const StandaloneRuntime: Readonly<{
    useState: (initialState?: any) => [any, (updater: any) => void];
    useReducer: (reducer: any, initialArg: any, init?: any) => [unknown, () => void];
    useRef: (initialValue?: any) => useTapRef.RefObject<any>;
    useMemo: (factory: any, deps: any) => unknown;
    useCallback: (callback: any, deps: any) => any;
    useEffect: (effect: any, deps?: any) => void;
    useLayoutEffect: (effect: any, deps?: any) => void;
    useInsertionEffect: (effect: any, deps?: any) => void;
    useEffectEvent: (callback: any) => any;
    useSyncExternalStore: (subscribe: any, getSnapshot: any, getServerSnapshot?: any) => unknown;
    useDebugValue: (value: any, format?: any) => void;
    useId: () => string;
    useImperativeHandle: (ref: any, create: any, deps?: any) => void;
    createContext: (defaultValue: any) => any;
    use: (usable: any) => unknown;
    useContext: (context: any) => unknown;
    forwardRef: (render: any) => {
        $$typeof: symbol;
        render: any;
    };
    memo: (type: any, compare?: any) => {
        $$typeof: symbol;
        type: any;
        compare: any;
    };
    Fragment: typeof Fragment;
    createElement: () => never;
    cloneElement: () => never;
    isValidElement: (_value: unknown) => boolean;
    lazy: (load: any) => {
        $$typeof: symbol;
        _payload: {
            _status: number;
            _result: any;
        };
        _init: () => never;
    };
    Children: {
        map: () => never;
        forEach: () => never;
        count: () => never;
        toArray: () => never;
        only: () => never;
    };
    Suspense: typeof Suspense;
    useDeferredValue: () => never;
}>;
export default StandaloneRuntime;