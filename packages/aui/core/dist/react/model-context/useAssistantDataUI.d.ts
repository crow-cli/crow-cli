import type { DataMessagePartComponent } from "../types/MessagePartComponentTypes.js";
/** Props used to register a renderer for `data` message parts. */
export type AssistantDataUIProps<T = any> = {
    /** Data part name this renderer handles. */
    name: string;
    /** Component rendered for matching data message parts. */
    render: DataMessagePartComponent<T>;
};
/**
 * Registers a renderer for named `data` message parts while the component is
 * mounted.
 *
 * @param dataUI - Data renderer registration, or `null` to skip registration.
 */
export declare const useAssistantDataUI: (dataUI: AssistantDataUIProps | null) => void;