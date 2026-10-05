import type { ModelContextProvider, ModelContext } from "../types.js";
import type { Unsubscribe } from "../../types/unsubscribe.js";
export declare class AssistantFrameHost implements ModelContextProvider {
    private _context;
    private _subscribers;
    private _pendingRequests;
    private _iframeWindow;
    private _targetOrigin;
    private _disposed;
    constructor(iframeWindow: Window, targetOrigin?: string);
    private handleMessage;
    private updateContext;
    private callTool;
    private sendRequest;
    private cancelToolCall;
    private requestContext;
    private notifySubscribers;
    getModelContext(): ModelContext;
    subscribe(callback: () => void): Unsubscribe;
    dispose(): void;
}