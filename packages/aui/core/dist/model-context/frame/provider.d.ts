import type { ModelContextProvider } from "../types.js";
import type { Unsubscribe } from "../../types/unsubscribe.js";
export declare class AssistantFrameProvider {
    private static _instance;
    private _providers;
    private _providerUnsubscribes;
    private _activeToolCalls;
    private _targetOrigin;
    private _strictRegistrations;
    private _wildcardRegistrations;
    private _startupTimer;
    private _disposed;
    private constructor();
    private static getInstance;
    private reconcileTargetOrigin;
    private handleMessage;
    private handleToolCall;
    private cancelToolCall;
    private cancelToolCallsForProvider;
    private sendMessage;
    private getProviders;
    private getTool;
    private getModelContext;
    private broadcastUpdate;
    private postModelContext;
    private removeProvider;
    static addModelContextProvider(provider: ModelContextProvider, targetOrigin?: string): Unsubscribe;
    static dispose(): void;
}