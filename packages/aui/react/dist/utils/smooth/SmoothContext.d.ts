import { type ComponentType, type FC, type PropsWithChildren } from "react";
import type { ReadonlyStore } from "../../context/ReadonlyStore.js";
export declare const SmoothContextProvider: FC<PropsWithChildren>;
export declare const withSmoothContextProvider: <C extends ComponentType<any>>(Component: C) => C;
export declare const useSmoothStatus: {
    (): {
        readonly type: "running";
    } | {
        readonly type: "complete";
    } | {
        readonly type: "incomplete";
        readonly reason: "cancelled" | "length" | "content-filter" | "other" | "error";
        readonly error?: unknown;
    } | {
        readonly type: "requires-action";
        readonly reason: "tool-calls" | "interrupt";
    } | {
        readonly type: "incomplete";
        readonly reason: "tool-calls";
        readonly error?: import("assistant-stream/utils").ReadonlyJSONValue;
    };
    <TSelected>(selector: (state: {
        readonly type: "running";
    } | {
        readonly type: "complete";
    } | {
        readonly type: "incomplete";
        readonly reason: "cancelled" | "length" | "content-filter" | "other" | "error";
        readonly error?: unknown;
    } | {
        readonly type: "requires-action";
        readonly reason: "tool-calls" | "interrupt";
    } | {
        readonly type: "incomplete";
        readonly reason: "tool-calls";
        readonly error?: import("assistant-stream/utils").ReadonlyJSONValue;
    }) => TSelected): TSelected;
    (options: {
        optional: true;
    }): {
        readonly type: "running";
    } | {
        readonly type: "complete";
    } | {
        readonly type: "incomplete";
        readonly reason: "cancelled" | "length" | "content-filter" | "other" | "error";
        readonly error?: unknown;
    } | {
        readonly type: "requires-action";
        readonly reason: "tool-calls" | "interrupt";
    } | {
        readonly type: "incomplete";
        readonly reason: "tool-calls";
        readonly error?: import("assistant-stream/utils").ReadonlyJSONValue;
    } | null;
    <TSelected>(options: {
        optional: true;
        selector?: (state: {
            readonly type: "running";
        } | {
            readonly type: "complete";
        } | {
            readonly type: "incomplete";
            readonly reason: "cancelled" | "length" | "content-filter" | "other" | "error";
            readonly error?: unknown;
        } | {
            readonly type: "requires-action";
            readonly reason: "tool-calls" | "interrupt";
        } | {
            readonly type: "incomplete";
            readonly reason: "tool-calls";
            readonly error?: import("assistant-stream/utils").ReadonlyJSONValue;
        }) => TSelected;
    }): TSelected | null;
}, useSmoothStatusStore: {
    (): ReadonlyStore<{
        readonly type: "running";
    } | {
        readonly type: "complete";
    } | {
        readonly type: "incomplete";
        readonly reason: "cancelled" | "length" | "content-filter" | "other" | "error";
        readonly error?: unknown;
    } | {
        readonly type: "requires-action";
        readonly reason: "tool-calls" | "interrupt";
    } | {
        readonly type: "incomplete";
        readonly reason: "tool-calls";
        readonly error?: import("assistant-stream/utils").ReadonlyJSONValue;
    }>;
    (options: {
        optional: true;
    }): ReadonlyStore<{
        readonly type: "running";
    } | {
        readonly type: "complete";
    } | {
        readonly type: "incomplete";
        readonly reason: "cancelled" | "length" | "content-filter" | "other" | "error";
        readonly error?: unknown;
    } | {
        readonly type: "requires-action";
        readonly reason: "tool-calls" | "interrupt";
    } | {
        readonly type: "incomplete";
        readonly reason: "tool-calls";
        readonly error?: import("assistant-stream/utils").ReadonlyJSONValue;
    }> | null;
};