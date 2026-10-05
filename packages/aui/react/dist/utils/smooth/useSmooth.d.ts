import type { ReasoningMessagePart, TextMessagePart, MessagePartState } from "@assistant-ui/core";
/**
 * Tuning options for the smooth text streaming animation.
 */
export type SmoothOptions = {
    /**
     * Target time in milliseconds to drain the backlog of unrevealed
     * characters. Larger values reveal long backlogs more gradually.
     * @default 250
     */
    drainMs?: number | undefined;
    /**
     * Maximum time in milliseconds between revealed characters, i.e. the
     * slowest reveal rate when the backlog is short.
     * @default 5
     */
    maxCharIntervalMs?: number | undefined;
    /**
     * Maximum number of characters revealed per animation frame.
     * @default Infinity
     */
    maxCharsPerFrame?: number | undefined;
    /**
     * Minimum time in milliseconds between committed updates. The reveal keeps
     * advancing every frame, but the visible text (and the downstream re-render
     * and markdown re-parse it triggers) is committed at most once per interval.
     * The final frame always commits. `0` commits every frame.
     * @default 0
     */
    minCommitMs?: number | undefined;
};
/**
 * Animates streamed message part text with a typewriter-style reveal.
 *
 * Takes the current part state and a `smooth` argument: `false` disables,
 * `true` uses the default rate, and a {@link SmoothOptions} object tunes
 * the reveal. Returns the part state with `text` replaced by the revealed
 * prefix and `status` reporting `running` until the reveal catches up.
 * If the source settles before any character has been revealed, the text
 * is committed immediately so a missed animation frame cannot leave an
 * empty bubble.
 *
 * The reveal auto-disables under `prefers-reduced-motion: reduce`,
 * committing the full text immediately; this takes precedence over an
 * explicit `smooth={true}`.
 *
 * @example
 * ```tsx
 * const { text, status } = useSmooth(useMessagePartText(), {
 *   drainMs: 500,
 *   maxCharsPerFrame: 30,
 * });
 * ```
 */
export declare const useSmooth: (state: MessagePartState & (TextMessagePart | ReasoningMessagePart), smooth?: boolean | SmoothOptions) => MessagePartState & (TextMessagePart | ReasoningMessagePart);