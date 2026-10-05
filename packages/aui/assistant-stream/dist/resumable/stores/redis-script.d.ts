export declare function redisScriptSha(script: string): string;
export declare function runCachedRedisScript<T>(runSha: () => Promise<T>, runSource: () => Promise<T>): Promise<T>;