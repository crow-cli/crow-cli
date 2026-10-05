/**
 * Marks a tool as **human-in-the-loop**: the agent pauses and the UI (`render`)
 * supplies the result instead of code. Use it as the tool's `execute`:
 *
 * ```tsx
 * confirm: { execute: humanTool(), render: (props) => <Confirm {...props} /> }
 * ```
 *
 * Unlike {@link defineToolkit}, it has **no runtime implementation**: a
 * `"use generative"` compiler (e.g. `@assistant-ui/next` or `@assistant-ui/vite`)
 * detects `execute: humanTool()`, drops it, and stamps the tool `type: "human"`.
 * Reaching it at runtime means the module wasn't compiled (used outside a
 * `"use generative"` file), so it throws.
 */
export declare function humanTool(): never;
/**
 * @deprecated Use {@link humanTool}.
 */
export declare const hitlTool: typeof humanTool;
/**
 * @deprecated Use {@link humanTool}.
 */
export declare const hitl: typeof humanTool;