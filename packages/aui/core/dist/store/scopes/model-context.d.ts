import type { Unsubscribe } from "../../types/unsubscribe.js";
import type { ModelContextProvider } from "../../model-context/types.js";
export type ModelContextState = {
    readonly modelName?: string | undefined;
    readonly toolNames: readonly string[];
};
export type ModelContextMethods = ModelContextProvider & {
    getState(): ModelContextState;
    register: (provider: ModelContextProvider) => Unsubscribe;
};
export type ModelContextClientSchema = {
    methods: ModelContextMethods;
};