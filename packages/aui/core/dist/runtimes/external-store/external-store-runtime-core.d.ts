import { BaseAssistantRuntimeCore } from "../../runtime/base/base-assistant-runtime-core.js";
import { ExternalStoreThreadListRuntimeCore } from "./external-store-thread-list-runtime-core.js";
import type { ExternalStoreAdapter } from "./external-store-adapter.js";
export declare class ExternalStoreRuntimeCore extends BaseAssistantRuntimeCore {
    readonly threads: ExternalStoreThreadListRuntimeCore;
    private _adapter;
    constructor(adapter: ExternalStoreAdapter<any>);
    setAdapter(adapter: ExternalStoreAdapter<any>): void;
}