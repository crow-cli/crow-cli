import type { Cluster as IoRedisCluster, Redis as IoRedis } from "ioredis";
import { type RedisResumableStreamStoreOptions } from "./redis-impl.js";
import type { ResumableStreamStore } from "../types.js";
export type IoRedisLike = IoRedis | IoRedisCluster;
/**
 * Resumable stream store backed by [`ioredis`](https://www.npmjs.com/package/ioredis)
 * v5 or v6. Accepts a `Redis` or `Cluster` instance.
 */
export declare function createIoredisResumableStreamStore(client: IoRedisLike, options?: RedisResumableStreamStoreOptions): ResumableStreamStore;