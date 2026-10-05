type ImperativeRef<T> = ((instance: T | null) => void | (() => void)) | {
    current: T | null;
} | null | undefined;
export declare const useImperativeHandle: <T>(ref: ImperativeRef<T>, create: () => T, deps?: readonly unknown[] | null) => void;
export {};