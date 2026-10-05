import type { FC } from "react";
import { type AssistantToolProps } from "./useAssistantTool.js";
/**
 * Component returned by {@link makeAssistantTool}.
 *
 * Rendering the component registers its tool for the lifetime of that render
 * subtree.
 *
 * @deprecated Use a toolkit with `Tools({ toolkit })` and register it via
 * `AuiConfig({ tools: Tools({ toolkit }) })` on the provider's `config` prop instead. See
 * https://assistant-ui.com/docs/migrations/toolkit-tools.
 */
export type AssistantTool = FC & {
    /** Tool definition registered by this component. */
    unstable_tool: AssistantToolProps<any, any>;
};
/**
 * Creates a React component that registers an assistant tool when rendered.
 *
 * Use this when exporting reusable tool modules that can be included in JSX
 * rather than calling {@link useAssistantTool} directly.
 *
 * @param tool - Tool definition and name to register.
 *
 * @deprecated Use a toolkit with `Tools({ toolkit })` and register it via
 * `AuiConfig({ tools: Tools({ toolkit }) })` on the provider's `config` prop instead. See
 * https://assistant-ui.com/docs/migrations/toolkit-tools.
 */
export declare const makeAssistantTool: <TArgs extends Record<string, unknown>, TResult>(tool: AssistantToolProps<TArgs, TResult>) => AssistantTool;