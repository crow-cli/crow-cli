export declare class PipeableTransformStream<I, O> extends TransformStream<I, O> {
    constructor(transform: (readable: ReadableStream<I>) => ReadableStream<O>);
}