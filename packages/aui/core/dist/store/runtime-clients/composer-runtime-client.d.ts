import type { ClientOutput } from "@assistant-ui/store";
import type { ComposerRuntime } from "../../runtime/api/composer-runtime.js";
export declare const ComposerClient: import("@assistant-ui/tap").Resource<ClientOutput<"composer">, [{
    threadIdRef: {
        current: string;
    };
    messageIdRef?: {
        current: string;
    };
    runtime: ComposerRuntime;
    isSuggestion?: ((text: string) => boolean) | undefined;
}]>;