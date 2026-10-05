export declare class LineDecoderStream extends TransformStream<string, string> {
    private buffer;
    private skipNextLineFeed;
    constructor();
}