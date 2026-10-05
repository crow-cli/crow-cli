export type RunManager = Readonly<{
    isRunning: boolean;
    schedule: () => void;
    cancel: () => void;
}>;
export declare function useRunManager(config: {
    onRun: (signal: AbortSignal) => Promise<void>;
    onFinish?: (() => void) | undefined;
    onCancel?: (() => void) | undefined;
    onError?: ((error: Error) => void | Promise<void>) | undefined;
}): RunManager;