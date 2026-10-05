import type { ThreadMessage } from "../../types/message.js";
export type ConverterCallback<TIn> = (cache: ThreadMessage | undefined, message: TIn, idx: number) => ThreadMessage;
export declare class ThreadMessageConverter {
    private readonly cache;
    convertMessages<TIn extends WeakKey>(messages: readonly TIn[], converter: ConverterCallback<TIn>): ThreadMessage[];
}