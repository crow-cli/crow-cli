export type AbortableThreadLoadPurpose = "initial" | "reload";
type AbortableThreadLoadOptions = {
    purpose?: AbortableThreadLoadPurpose;
    load: (signal: AbortSignal) => Promise<void>;
    onSettled: () => void;
    onInitialError: (error: unknown) => void;
};
export declare const createAbortableThreadLoad: () => {
    abort(purpose?: AbortableThreadLoadPurpose): void;
    run({ purpose, load, onSettled, onInitialError, }: AbortableThreadLoadOptions): Promise<void>;
};
export {};