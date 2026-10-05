export declare const REPLAY_CONTENT_LENGTH_HEADER = "Aui-Replay-Content-Length";
type ReplayBoundaryStreamOptions = {
    setReplaying: (value: boolean) => void;
    waitForRender: () => Promise<void>;
};
export declare const useReplayRenderWait: () => () => Promise<void>;
export declare const createReplayBoundaryStream: (response: Response, { setReplaying, waitForRender: waitForReplayRender, }: ReplayBoundaryStreamOptions) => Promise<ReadableStream<Uint8Array>>;
export {};