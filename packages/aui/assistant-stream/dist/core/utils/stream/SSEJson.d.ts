export declare const SSE_HEADERS: {
    "Content-Type": string;
    "Cache-Control": string;
    Connection: string;
};
type SSEJsonDoneOptions<T> = {
    marker: string;
    onDone?: (controller: TransformStreamDefaultController<T>) => void;
    onMissing?: () => void;
};
type SSEJsonDecoderOptions<T> = {
    parse: (data: string, controller: TransformStreamDefaultController<T>) => void;
    done?: SSEJsonDoneOptions<T>;
} & ({
    strict?: true;
} | {
    strict: false;
    onUnknownEvent?: (event: string) => void;
});
export declare const createSSEJsonEncoder: <T>(doneMarker?: string) => (readable: ReadableStream<T>) => ReadableStream<Uint8Array<ArrayBuffer>>;
export declare const createSSEJsonDecoder: <T>(options: SSEJsonDecoderOptions<T>) => (readable: ReadableStream<Uint8Array<ArrayBuffer>>) => ReadableStream<T>;
export {};