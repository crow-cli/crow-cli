type PropFieldStatus = "streaming" | "complete";
/**
 * Streaming completion status for the arguments of the current tool call.
 */
export type ToolArgsStatus<TArgs extends Record<string, unknown> = Record<string, unknown>> = {
    /** Overall lifecycle state of the tool-call part. */
    status: "running" | "complete" | "incomplete" | "requires-action";
    /** Per-argument status keyed by argument name. */
    propStatus: Partial<Record<keyof TArgs, PropFieldStatus>>;
};
/**
 * Reads whether each argument field for the current tool-call message part is
 * still streaming or complete.
 *
 * Use inside a tool-call renderer to avoid showing incomplete argument values
 * as final.
 *
 * @throws If called outside a tool-call message part.
 *
 * @example
 * ```tsx
 * function WeatherToolUI({
 *   args,
 * }: ToolCallMessagePartProps<{ city: string }>) {
 *   const { propStatus } = useToolArgsStatus<{ city: string }>();
 *
 *   return (
 *     <span>
 *       {propStatus.city === "streaming" ? "Reading city..." : args.city}
 *     </span>
 *   );
 * }
 * ```
 */
export declare const useToolArgsStatus: <TArgs extends Record<string, unknown> = Record<string, unknown>>() => ToolArgsStatus<TArgs>;
export {};