import type { ReadonlyJSONObject } from "assistant-stream/utils";
export declare class CloudResponseError extends Error {
    constructor(message: string);
}
export declare const readCloudRecord: (value: unknown, field: string) => Record<string, unknown>;
export declare const readCloudArray: (value: unknown, field: string) => unknown[];
export declare const readCloudString: (value: unknown, field: string) => string;
export declare const readCloudNumber: (value: unknown, field: string) => number;
export declare const readCloudNullableNumber: (value: unknown, field: string) => number | null;
export declare const readCloudEnum: <const T extends readonly string[]>(value: unknown, field: string, allowed: T) => T[number];
export declare const readCloudNullableString: (value: unknown, field: string) => string | null;
export declare const readCloudBoolean: (value: unknown, field: string) => boolean;
export declare const readCloudInteger: (value: unknown, field: string) => number;
export declare const readCloudTimestamp: (value: unknown, field: string) => Date;
export declare const readCloudJSONObject: (value: unknown, field: string) => ReadonlyJSONObject;