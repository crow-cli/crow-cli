import type { ClientOutput } from "@assistant-ui/store";
export declare const NoOpComposerClient: import("@assistant-ui/tap").Resource<ClientOutput<"composer">, [{
    type: "edit" | "thread";
}]>;