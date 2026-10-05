import { BaseAssistantRuntimeCore } from "../../runtime/base/base-assistant-runtime-core.js";
import type { LocalRuntimeOptionsBase } from "./local-runtime-options.js";
import { LocalThreadListRuntimeCore } from "./local-thread-list-runtime-core.js";
import type { ThreadMessageLike } from "../../runtime/utils/thread-message-like.js";
export declare class LocalRuntimeCore extends BaseAssistantRuntimeCore {
    readonly threads: LocalThreadListRuntimeCore;
    readonly Provider: undefined;
    private _options;
    constructor(options: LocalRuntimeOptionsBase, initialMessages: readonly ThreadMessageLike[] | undefined);
}