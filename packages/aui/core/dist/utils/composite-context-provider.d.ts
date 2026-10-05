import { type ModelContextProvider } from "../model-context/types.js";
export declare class CompositeContextProvider implements ModelContextProvider {
    private _providers;
    private _providerUnsubscribes;
    getModelContext(): import("../index.js").ModelContext;
    registerModelContextProvider(provider: ModelContextProvider): () => void;
    private _subscribers;
    notifySubscribers(): void;
    subscribe(callback: () => void): () => void;
}