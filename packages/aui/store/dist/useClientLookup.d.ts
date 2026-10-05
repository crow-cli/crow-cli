import { type ResourceElement } from "@assistant-ui/tap";
import type { ClientMethods, InferClientState } from "./types/client.js";
export declare function useClientLookup<TMethods extends ClientMethods>(elements: readonly ResourceElement<TMethods>[]): {
    state: InferClientState<TMethods>[];
    get: (lookup: {
        index: number;
    } | {
        key: string;
    }) => TMethods;
};