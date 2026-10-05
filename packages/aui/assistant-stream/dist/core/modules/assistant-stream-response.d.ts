import { type AssistantStreamController } from "./assistant-stream.js";
/**
 * Creates a `Response` whose body is an encoded {@link AssistantStream}.
 *
 * This is the HTTP-route convenience form of {@link createAssistantStream}; it
 * uses {@link DataStreamEncoder} so the response can be consumed by matching
 * assistant-ui data stream decoders.
 */
export declare function createAssistantStreamResponse(callback: (controller: AssistantStreamController) => PromiseLike<void> | void): Response;