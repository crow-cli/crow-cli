export type WebMcpContent = {
    type: "text";
    text: string;
} | {
    type: "image";
    data: string;
    mimeType: string;
};
export type WebMcpCallToolResult = {
    content: WebMcpContent[];
    isError?: boolean;
};
export type WebMcpToolDescriptor = {
    name: string;
    description: string;
    inputSchema: unknown;
    execute: (args: unknown, context?: {
        signal?: AbortSignal;
    }) => Promise<WebMcpCallToolResult>;
};
export type WebMcpModelContext = {
    /**
     * Aborting `options.signal` is what unregisters the tool. The explainer
     * defines no other removal method, and a name-keyed one could not be used
     * safely: a later registration may already hold the name.
     */
    registerTool(tool: WebMcpToolDescriptor, options?: {
        signal?: AbortSignal;
    }): Promise<void> | void;
};
export type WebMcpHost = {
    available: boolean;
    registerTool(def: WebMcpToolDescriptor, onError?: (error: unknown) => void): () => void;
};
export declare const getDefaultWebMcpHost: () => WebMcpHost;