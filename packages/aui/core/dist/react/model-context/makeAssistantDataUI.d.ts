import type { FC } from "react";
import { type AssistantDataUIProps } from "./useAssistantDataUI.js";
/**
 * Component returned by {@link makeAssistantDataUI}.
 *
 * Rendering the component registers a renderer for matching `data` message
 * parts.
 */
export type AssistantDataUI = FC & {
    /** Data renderer registered by this component. */
    unstable_data: AssistantDataUIProps;
};
/**
 * Creates a React component that registers a named data-part renderer when
 * rendered.
 *
 * @param dataUI - Data renderer registration.
 */
export declare const makeAssistantDataUI: <T = any>(dataUI: AssistantDataUIProps<T>) => AssistantDataUI;