import { type RedisResumableStreamStoreOptions } from "./redis-impl.js";
import type { ResumableStreamStore } from "../types.js";
type NodeRedisFields = Record<string, string | Buffer>;
interface NodeRedisMultiCommand {
    xAdd(key: string, id: string, fields: NodeRedisFields): NodeRedisMultiCommand;
    expire(key: string, seconds: number): NodeRedisMultiCommand;
    execAsPipeline(): Promise<unknown>;
}
/** Structural subset of node-redis v5 used by the adapter. */
export interface NodeRedisLike {
    set(key: string, value: string, options: {
        NX: true;
        EX: number;
    }): Promise<string | null>;
    get(key: string): Promise<string | null>;
    del(keys: string | string[]): Promise<unknown>;
    sendCommand<T = unknown>(args: ReadonlyArray<string | Buffer>, options?: {
        typeMapping?: Record<number, unknown>;
    }): Promise<T>;
    multi(): NodeRedisMultiCommand;
}
/**
 * Resumable stream store backed by [`redis`](https://www.npmjs.com/package/redis)
 * v5. Expects a connected client; cluster routing relies on the shared
 * `{streamId}` hash tag baked into the key scheme.
 */
export declare function createRedisResumableStreamStore(client: NodeRedisLike, options?: RedisResumableStreamStoreOptions): ResumableStreamStore;
export {};