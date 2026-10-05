import { type ComponentType, type FC, type PropsWithChildren, type ReactNode } from "react";
import type { PartState } from "../../../store/scopes/part.js";
import type { ReasoningMessagePartComponent, ToolCallMessagePartComponent } from "../../types/MessagePartComponentTypes.js";
type ChainOfThoughtPartsComponentConfig = {
    /** Component for rendering reasoning parts */
    Reasoning?: ReasoningMessagePartComponent | undefined;
    /** Fallback component for tool-call parts */
    tools?: {
        Fallback?: ToolCallMessagePartComponent | undefined;
    };
    /** Layout component to wrap the rendered parts when expanded */
    Layout?: ComponentType<PropsWithChildren> | undefined;
};
export declare namespace ChainOfThoughtPrimitiveParts {
    type Props = {
        /**
         * @deprecated Use the children render function instead.
         */
        components?: ChainOfThoughtPartsComponentConfig;
        children?: never;
    } | {
        /** Render function called for each part. Receives the part. */
        children: (value: {
            part: PartState;
        }) => ReactNode;
        components?: never;
    };
}
/**
 * Renders the parts within a chain of thought, with support for collapsed/expanded states.
 *
 * When collapsed, no parts are shown. When expanded, all parts are rendered
 * using the provided component configuration through the part scope mechanism.
 */
export declare const ChainOfThoughtPrimitiveParts: FC<ChainOfThoughtPrimitiveParts.Props>;
export {};