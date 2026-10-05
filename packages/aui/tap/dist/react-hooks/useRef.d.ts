export declare namespace useRef {
    interface RefObject<T> {
        current: T;
    }
}
export declare function useRef<T>(initialValue: T): useRef.RefObject<T>;
export declare function useRef<T = undefined>(): useRef.RefObject<T | undefined>;