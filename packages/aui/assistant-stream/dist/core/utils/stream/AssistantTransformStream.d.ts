import type { AssistantStreamChunk } from "../../AssistantStreamChunk.js";
import { type AssistantStreamController } from "../../modules/assistant-stream.js";
type AssistantTransformerFlushCallback = (controller: AssistantStreamController) => void | PromiseLike<void>;
type AssistantTransformerStartCallback = (controller: AssistantStreamController) => void | PromiseLike<void>;
type AssistantTransformerTransformCallback<I> = (chunk: I, controller: AssistantStreamController) => void | PromiseLike<void>;
type AssistantTransformer<I> = {
    strict?: boolean | undefined;
    flush?: AssistantTransformerFlushCallback;
    start?: AssistantTransformerStartCallback;
    transform?: AssistantTransformerTransformCallback<I>;
};
export declare class AssistantTransformStream<I> extends TransformStream<I, AssistantStreamChunk> {
    constructor(transformer: AssistantTransformer<I>, writableStrategy?: QueuingStrategy<I>, readableStrategy?: QueuingStrategy<AssistantStreamChunk>);
}
export {};