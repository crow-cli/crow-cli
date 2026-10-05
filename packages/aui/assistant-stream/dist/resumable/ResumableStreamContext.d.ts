import type { ResumableStreamRole, ResumableStreamStatus, ResumableStreamStore } from "./types.js";
export type ResumableStreamContextOptions = {
    readonly store: ResumableStreamStore;
    readonly ttlMs?: number;
    /**
     * Required on serverless runtimes that terminate background work when the
     * request handler returns (Vercel, Cloudflare). Pass `after` from
     * `next/server` so the producer task outlives the response.
     */
    readonly waitUntil?: (promise: Promise<unknown>) => void;
    readonly onAcquire?: (streamId: string, role: ResumableStreamRole) => void;
    readonly onAppend?: (streamId: string, byteLength: number) => void;
    readonly onFinalize?: (streamId: string, status: "done" | "error", error?: string) => void;
    readonly onError?: (streamId: string, error: unknown) => void;
};
export interface ResumableStreamContext {
    /** Producer or consumer entrypoint. Atomically elects the role. */
    run(streamId: string, makeStream: () => ReadableStream<Uint8Array>): Promise<ReadableStream<Uint8Array>>;
    /** Returns `null` when the stream does not exist. */
    resume(streamId: string): Promise<ReadableStream<Uint8Array> | null>;
    /** Throws `ResumableStreamError("missing")` when the stream does not exist. */
    requireResume(streamId: string): Promise<ReadableStream<Uint8Array>>;
    status(streamId: string): Promise<ResumableStreamStatus>;
    delete(streamId: string): Promise<void>;
}
export declare function createResumableStreamContext(options: ResumableStreamContextOptions): ResumableStreamContext;