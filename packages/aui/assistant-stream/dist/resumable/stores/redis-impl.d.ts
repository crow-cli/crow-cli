import type { ResumableStreamAcquireOptions, ResumableStreamAcquisition, ResumableStreamLease, ResumableStreamEntry, ResumableStreamRole, ResumableStreamStatus, ResumableStreamStore } from "../types.js";
export type PipelineCommand = {
    readonly type: "xAdd";
    readonly key: string;
    readonly fields: Record<string, string | Uint8Array>;
} | {
    readonly type: "expire";
    readonly key: string;
    readonly ttlSec: number;
};
export type RedisFinalizeOptions = {
    readonly metaKey: string;
    readonly expectedMeta: string;
    readonly nextMeta: string;
    readonly dataKey: string;
    readonly fields: Record<string, string>;
    readonly ttlSec: number;
};
export type RedisAppendOptions = {
    readonly metaKey: string;
    readonly expectedMeta: string;
    readonly dataKey: string;
    readonly fields: Record<string, string | Uint8Array>;
    readonly ttlSec: number;
};
export type RedisDeleteOptions = {
    readonly metaKey: string;
    readonly expectedMeta: string;
    readonly dataKeys: readonly string[];
};
export declare const FINALIZE_IF_UNCHANGED_SCRIPT = "\nredis.replicate_commands()\nif redis.call(\"GET\", KEYS[1]) ~= ARGV[1] then\n  return 0\nend\nlocal xadd = { \"XADD\", KEYS[2], \"*\" }\nfor i = 4, #ARGV do\n  table.insert(xadd, ARGV[i])\nend\nredis.call(unpack(xadd))\nredis.call(\"EXPIRE\", KEYS[2], ARGV[3])\nredis.call(\"SET\", KEYS[1], ARGV[2], \"EX\", ARGV[3])\nreturn 1\n";
export declare const FINALIZE_IF_UNCHANGED_KEY_COUNT = 2;
export declare const APPEND_IF_UNCHANGED_SCRIPT = "\nredis.replicate_commands()\nif redis.call(\"GET\", KEYS[1]) ~= ARGV[1] then\n  return 0\nend\nlocal xadd = { \"XADD\", KEYS[2], \"*\" }\nfor i = 3, #ARGV do\n  table.insert(xadd, ARGV[i])\nend\nredis.call(unpack(xadd))\nredis.call(\"EXPIRE\", KEYS[2], ARGV[2])\nredis.call(\"EXPIRE\", KEYS[1], ARGV[2])\nreturn 1\n";
export declare const APPEND_IF_UNCHANGED_KEY_COUNT = 2;
export declare const DELETE_IF_UNCHANGED_SCRIPT = "\nif redis.call(\"GET\", KEYS[1]) ~= ARGV[1] then\n  return 0\nend\nredis.call(\"DEL\", unpack(KEYS))\nreturn 1\n";
export declare function finalizeIfUnchangedArgs(options: RedisFinalizeOptions): string[];
export declare function appendIfUnchangedArgs(options: RedisAppendOptions): Array<string | Uint8Array>;
export declare function deleteIfUnchangedArgs(options: RedisDeleteOptions): string[];
/**
 * Structural Redis-client interface. The bundled `redis` and `ioredis`
 * adapters wrap their respective clients to satisfy it.
 */
export interface RedisLikeClient {
    setNX(key: string, value: string, ttlSec: number): Promise<boolean>;
    get(key: string): Promise<string | null>;
    del(keys: string[]): Promise<void>;
    xRange(key: string, start: string, end: string): Promise<Array<{
        id: string;
        fields: Record<string, string | Uint8Array>;
    }>>;
    /** Executes the commands as a single pipeline batch (one round trip). */
    pipeline(commands: readonly PipelineCommand[]): Promise<void>;
    /** Omitting this capability keeps the legacy unfenced append behavior. */
    appendIfUnchanged?(options: RedisAppendOptions): Promise<boolean>;
    /**
     * Atomically finalizes a stream only while its metadata is unchanged, so a
     * producer superseded by a newer acquisition cannot finalize the replacement.
     */
    finalizeIfUnchanged(options: RedisFinalizeOptions): Promise<boolean>;
    /** Omitting this capability keeps the legacy unfenced delete behavior. */
    deleteIfUnchanged?(options: RedisDeleteOptions): Promise<boolean>;
}
export type RedisResumableStreamStoreOptions = {
    readonly keyPrefix?: string;
    readonly defaultTtlMs?: number;
    /** Defaults to 100ms. Lower values reduce read latency, raise traffic. */
    readonly pollIntervalMs?: number;
    readonly maxChunkBytes?: number;
};
export declare class RedisResumableStreamStore implements ResumableStreamStore {
    private readonly client;
    private readonly keyPrefix;
    private readonly defaultTtlMs;
    private readonly pollIntervalMs;
    private readonly maxChunkBytes;
    constructor(client: RedisLikeClient, options?: RedisResumableStreamStoreOptions);
    private readonly acquiredGenerations;
    acquire(streamId: string, options?: ResumableStreamAcquireOptions): Promise<ResumableStreamRole>;
    acquireLease(streamId: string, options?: ResumableStreamAcquireOptions): Promise<ResumableStreamAcquisition>;
    private isSupersededGeneration;
    private assertOwnedGeneration;
    append(streamId: string, chunk: Uint8Array, lease?: ResumableStreamLease): Promise<void>;
    finalize(streamId: string, status: "done" | "error", error?: string, lease?: ResumableStreamLease): Promise<boolean>;
    read(streamId: string, cursor: string, signal: AbortSignal): AsyncIterable<ResumableStreamEntry>;
    status(streamId: string): Promise<ResumableStreamStatus>;
    delete(streamId: string): Promise<void>;
    private clearAcquiredGeneration;
    private readMeta;
    private metaKey;
    private dataKey;
}