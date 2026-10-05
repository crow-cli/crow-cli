import type { AssistantStream } from "assistant-stream";
import type { RemoteThreadInitializeResponse, RemoteThreadListAdapter, RemoteThreadListResponse, RemoteThreadMetadata } from "../types.js";
export declare class InMemoryThreadListAdapter implements RemoteThreadListAdapter {
    list(): Promise<RemoteThreadListResponse>;
    rename(): Promise<void>;
    updateCustom(): Promise<void>;
    archive(): Promise<void>;
    unarchive(): Promise<void>;
    delete(): Promise<void>;
    initialize(threadId: string): Promise<RemoteThreadInitializeResponse>;
    generateTitle(): Promise<AssistantStream>;
    fetch(threadId: string): Promise<RemoteThreadMetadata>;
}