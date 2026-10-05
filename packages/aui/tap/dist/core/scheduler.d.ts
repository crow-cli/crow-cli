type Task = () => void;
export declare class UpdateScheduler {
    private _isDirty;
    private readonly _task;
    constructor(_task: Task);
    get isDirty(): boolean;
    markDirty(): void;
    runTask(): void;
    settle(): void;
}
export declare const scheduleTask: (task: Task) => void;
export declare const scheduleNotify: (notify: () => void) => void;
export declare const flushTapSync: <T>(callback: () => T) => T;
export {};