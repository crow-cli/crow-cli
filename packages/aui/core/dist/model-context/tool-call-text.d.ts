type ToolCallRunningText<TArgs extends Record<string, unknown>, TValue> = TValue | undefined | null | ((options: {
    args: TArgs;
}) => TValue | undefined | null);
type ToolCallCompleteText<TArgs extends Record<string, unknown>, TResult, TValue> = TValue | undefined | null | ((options: {
    args: TArgs;
    result: TResult | undefined;
}) => TValue | undefined | null);
export type ToolCallText<TArgs extends Record<string, unknown>, TResult, TValue = string> = {
    running: ToolCallRunningText<TArgs, TValue>;
    complete?: ToolCallCompleteText<TArgs, TResult, TValue> | undefined;
} | {
    running?: ToolCallRunningText<TArgs, TValue> | undefined;
    complete: ToolCallCompleteText<TArgs, TResult, TValue>;
};
type ToolCallTextPart<TArgs extends Record<string, unknown>, TResult> = {
    readonly args: TArgs;
    readonly result?: TResult | undefined;
    readonly status?: {
        readonly type?: string | undefined;
    } | undefined;
};
export declare const resolveToolCallText: <TArgs extends Record<string, unknown>, TResult, TValue>(text: ToolCallText<TArgs, TResult, TValue>, part: ToolCallTextPart<TArgs, TResult>) => TValue | undefined | null;
export {};