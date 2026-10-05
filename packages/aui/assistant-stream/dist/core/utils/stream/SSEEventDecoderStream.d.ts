export type PipelineSSEEvent = {
    event: string;
    data: string;
    id?: string;
    retry?: number;
};
export declare class SSEEventDecoderStream extends TransformStream<string, PipelineSSEEvent> {
    constructor();
}