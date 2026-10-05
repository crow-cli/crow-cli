import type { ToolCallArgsReader, ToolCallReader, ToolCallResponseReader } from "./tool-types.js";
import type { DeepPartial, TypeAtPath, TypePath } from "./type-path-utils.js";
import type { ToolResponse } from "./ToolResponse.js";
import type { AsyncIterableStream, ReadonlyJSONObject, ReadonlyJSONValue } from "../../utils.js";
export declare class ToolCallArgsReaderImpl<T extends ReadonlyJSONObject> implements ToolCallArgsReader<T> {
    private argTextDeltas;
    private handles;
    private accumulatedText;
    private parsedTextLength;
    private args;
    private finished;
    private failure;
    constructor(argTextDeltas: ReadableStream<string>);
    private processStream;
    private settleHandle;
    private parseCurrentArgs;
    private updateHandles;
    private activateHandle;
    get<PathT extends TypePath<T>>(...fieldPath: PathT): Promise<TypeAtPath<T, PathT>>;
    streamValues<PathT extends TypePath<T>>(...fieldPath: PathT): AsyncIterableStream<DeepPartial<TypeAtPath<T, PathT>>>;
    streamText<PathT extends TypePath<T>>(...fieldPath: PathT): TypeAtPath<T, PathT> extends string & (infer U) ? AsyncIterableStream<U> : never;
    forEach<PathT extends TypePath<T>>(...fieldPath: PathT): NonNullable<TypeAtPath<T, PathT>> extends Array<infer U> ? AsyncIterableStream<U> : never;
}
export declare class ToolCallResponseReaderImpl<TResult extends ReadonlyJSONValue> implements ToolCallResponseReader<TResult> {
    private readonly promise;
    constructor(promise: Promise<ToolResponse<TResult>>);
    get(): Promise<ToolResponse<TResult>>;
}
export declare class ToolCallReaderImpl<TArgs extends ReadonlyJSONObject, TResult extends ReadonlyJSONValue> implements ToolCallReader<TArgs, TResult> {
    readonly args: ToolCallArgsReaderImpl<TArgs>;
    readonly response: ToolCallResponseReaderImpl<TResult>;
    private readonly writable;
    private readonly resolve;
    argsText: string;
    constructor();
    appendArgsTextDelta(text: string): Promise<void>;
    finishArgsText(): Promise<void>;
    setResponse(value: ToolResponse<TResult>): void;
    result: {
        get: () => Promise<TResult>;
    };
}