import { SILENT_RUNTIME_ACTION } from "../../utils/silent-runtime-action.js";
export declare class ThreadListAdapterChangedError extends Error {
    readonly [SILENT_RUNTIME_ACTION] = true;
    constructor();
}