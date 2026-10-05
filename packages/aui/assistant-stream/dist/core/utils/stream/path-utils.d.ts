import type { AssistantStreamChunk } from "../../AssistantStreamChunk.js";
import { Counter } from "../Counter.js";
export declare class PathAppendEncoder extends TransformStream<AssistantStreamChunk, AssistantStreamChunk> {
    constructor(idx: number);
}
export declare class PathAppendDecoder extends TransformStream<AssistantStreamChunk, AssistantStreamChunk> {
    constructor(idx: number);
}
export declare class PathMergeEncoder extends TransformStream<AssistantStreamChunk, AssistantStreamChunk> {
    constructor(counter: Counter);
}