export type SSEEvent = {
    event?: string;
    data: string;
    id?: string;
    retry?: number;
};
export declare class SSEEventDecoder {
    private lineChunks;
    private dataLines;
    private eventName;
    private lastEventId;
    private retry;
    private pendingLF;
    private started;
    private readonly trailing;
    constructor(options?: {
        trailing?: "drop" | "dispatch";
    });
    push(text: string): SSEEvent[];
    flush(): SSEEvent | null;
    private processLine;
    private dispatchEvent;
    private resetFrame;
}