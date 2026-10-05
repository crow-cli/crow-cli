import type { ClientOutput } from "@assistant-ui/store";
import type { AttachmentRuntime } from "../../runtime/api/attachment-runtime.js";
export declare const AttachmentRuntimeClient: import("@assistant-ui/tap").Resource<ClientOutput<"attachment">, [{
    runtime: AttachmentRuntime;
}]>;