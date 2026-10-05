import { PipeableTransformStream } from "./PipeableTransformStream.js";
export declare class SSEEncoder<T> extends PipeableTransformStream<T, Uint8Array<ArrayBuffer>> {
    static readonly headers: Headers;
    headers: Headers;
    constructor();
}
export declare class SSEDecoder<T> extends PipeableTransformStream<Uint8Array<ArrayBuffer>, T> {
    constructor(options?: {
        strict?: boolean | undefined;
    });
}