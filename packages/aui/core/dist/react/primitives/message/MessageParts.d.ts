import { type ComponentType, type FC, type ReactNode, type PropsWithChildren } from "react";
import type { PartState } from "../../../store/scopes/part.js";
import type { Unstable_AudioMessagePartComponent, DataMessagePartComponent, EmptyMessagePartComponent, TextMessagePartComponent, ImageMessagePartComponent, SourceMessagePartComponent, ToolCallMessagePartComponent, ToolCallMessagePartProps, FileMessagePartComponent, ReasoningMessagePartComponent, ReasoningGroupComponent, QuoteMessagePartComponent, GenerativeUIComponentRegistry } from "../../types/MessagePartComponentTypes.js";
type MessagePartRange = {
    type: "single";
    index: number;
} | {
    type: "toolGroup";
    startIndex: number;
    endIndex: number;
    idKey?: string | undefined;
} | {
    type: "reasoningGroup";
    startIndex: number;
    endIndex: number;
    idKey?: string | undefined;
} | {
    type: "chainOfThoughtGroup";
    startIndex: number;
    endIndex: number;
    idKey?: string | undefined;
};
/**
 * Groups consecutive tool-call and reasoning message parts into ranges.
 * Always groups tool calls and reasoning parts, even if there's only one.
 * When useChainOfThought is true, groups tool-call and reasoning parts together.
 */
export declare const groupMessageParts: (messageTypes: readonly string[], useChainOfThought: boolean, partIds?: readonly (string | undefined)[]) => MessagePartRange[];
export declare namespace MessagePrimitiveParts {
    type DataConfig = {
        /** Map data event names to specific components */
        by_name?: Record<string, DataMessagePartComponent | undefined> | undefined;
        /** Fallback component for unmatched data events */
        Fallback?: DataMessagePartComponent | undefined;
    };
    type BaseComponents = {
        /** Component for rendering empty messages */
        Empty?: EmptyMessagePartComponent | undefined;
        /** Component for rendering text content */
        Text?: TextMessagePartComponent | undefined;
        /** Component for rendering source content */
        Source?: SourceMessagePartComponent | undefined;
        /** Component for rendering image content */
        Image?: ImageMessagePartComponent | undefined;
        /** Component for rendering file content */
        File?: FileMessagePartComponent | undefined;
        /**
         * Component for rendering audio content.
         *
         * @deprecated Render audio through the `File` slot instead, branching on an
         * `audio/*` mime type.
         */
        Unstable_Audio?: Unstable_AudioMessagePartComponent | undefined;
        /** Configuration for data part rendering */
        data?: DataConfig | undefined;
        /** Component for rendering a quoted message reference (from metadata, not parts) */
        Quote?: QuoteMessagePartComponent | undefined;
        /**
         * Configuration for generative-ui part rendering.
         *
         * `components` is the consumer-provided allowlist of React components
         * the agent's JSON spec is permitted to render. Any name not present in
         * the registry is rejected with a typed `GenerativeUIRenderError` —
         * this is the security boundary in the same-realm rendering path.
         */
        generativeUI?: {
            /** The component allowlist (the security boundary). */
            components: GenerativeUIComponentRegistry;
            /** Optional fallback for unknown component names. */
            Fallback?: ComponentType<{
                component: string;
                props?: unknown;
            }> | undefined;
        } | undefined;
    };
    type ToolsConfig = {
        /** Map of tool names to their specific components */
        by_name?: Record<string, ToolCallMessagePartComponent | undefined> | undefined;
        /** Fallback component for unregistered tools */
        Fallback?: ComponentType<ToolCallMessagePartProps> | undefined;
    } | {
        /** Override component that handles all tool calls */
        Override: ComponentType<ToolCallMessagePartProps>;
    };
    /**
     * Standard component configuration for rendering reasoning and tool-call parts
     * individually (with optional grouping).
     *
     * Cannot be combined with `ChainOfThought`.
     */
    type StandardComponents = BaseComponents & {
        /** Component for rendering reasoning content (typically hidden) */
        Reasoning?: ReasoningMessagePartComponent | undefined;
        /** Configuration for tool call rendering */
        tools?: ToolsConfig | undefined;
        /**
         * Component for rendering grouped consecutive tool calls.
         *
         * @param startIndex - Index of the first tool call in the group
         * @param endIndex - Index of the last tool call in the group
         * @param children - Rendered tool call components to display within the group
         *
         * @deprecated Use `<MessagePrimitive.GroupedParts>` with a custom `groupBy` instead.
         */
        ToolGroup?: ComponentType<PropsWithChildren<{
            startIndex: number;
            endIndex: number;
        }>>;
        /**
         * Component for rendering grouped reasoning parts.
         *
         * @param startIndex - Index of the first reasoning part in the group
         * @param endIndex - Index of the last reasoning part in the group
         * @param children - Rendered reasoning part components
         *
         * @deprecated Use `<MessagePrimitive.GroupedParts>` with a custom `groupBy` instead.
         */
        ReasoningGroup?: ReasoningGroupComponent;
        ChainOfThought?: never;
    };
    /**
     * Chain of thought component configuration.
     *
     * When `ChainOfThought` is set, it takes control of rendering ALL reasoning and
     * tool-call parts in the message. The `Reasoning`, `tools`, `ReasoningGroup`, and
     * `ToolGroup` components cannot be used alongside it.
     */
    type ChainOfThoughtComponents = BaseComponents & {
        /**
         * @deprecated Use `<MessagePrimitive.GroupedParts>` with a `groupBy`
         * that returns `["group-thought", ...]` for reasoning and tool-call
         * parts. See `@assistant-ui/ui` for a worked example.
         */
        ChainOfThought: ComponentType;
        Reasoning?: never;
        tools?: never;
        ToolGroup?: never;
        ReasoningGroup?: never;
    };
    export type Props = {
        /**
         * Component configuration for rendering different types of message content.
         *
         * Use either `Reasoning`/`tools`/`ToolGroup`/`ReasoningGroup` for standard rendering,
         * or `ChainOfThought` to group all reasoning and tool-call parts into a single
         * collapsible component. These two modes are mutually exclusive.
         */
        components?: StandardComponents | ChainOfThoughtComponents | undefined;
        /**
         * When enabled, shows the Empty component if the last part in the message
         * is anything other than Text or Reasoning.
         *
         * @experimental This API is experimental and may change in future versions.
         * @default true
         */
        unstable_showEmptyOnNonTextEnd?: boolean | undefined;
        children?: never;
    } | {
        /** Render function called for each part. Receives the enriched part state. */
        children: (value: {
            part: EnrichedPartState;
        }) => ReactNode;
        components?: never;
        unstable_showEmptyOnNonTextEnd?: never;
    };
    export {};
}
/**
 * Platform-agnostic no-op default components.
 * Each platform (web, RN) wraps MessagePrimitiveParts with its own defaults.
 */
export declare const defaultComponents: {
    Text: () => null;
    Reasoning: () => null;
    Source: () => null;
    Image: () => null;
    File: () => null;
    Unstable_Audio: () => null;
    ToolGroup: ({ children }: PropsWithChildren) => ReactNode;
    ReasoningGroup: ({ children }: PropsWithChildren) => ReactNode;
};
type MessagePartComponentProps = {
    components: MessagePrimitiveParts.Props["components"];
};
export declare const MessagePartComponent: FC<MessagePartComponentProps>;
export declare namespace MessagePrimitivePartByIndex {
    type Props = {
        index: number;
        components: MessagePrimitiveParts.Props["components"];
    };
}
/**
 * Renders a single message part at the specified index.
 */
export declare const MessagePrimitivePartByIndex: FC<MessagePrimitivePartByIndex.Props>;
/**
 * Fallback component rendered when the children render function returns null.
 * Renders registered tool/data UIs via context.
 * For all other part types, renders nothing.
 *
 * This allows users to write:
 *   {({ part }) => {
 *     if (part.type === "text") return <MyText />;
 *     return null; // tool UIs and data UIs still render via registry
 *   }}
 *
 * To explicitly render nothing (suppressing registered UIs), return <></>.
 */
export declare const DefaultPartFallback: FC;
export type { PartState };
/**
 * Enriched part state passed to children render functions.
 *
 * For tool-call parts, adds `toolUI`, `addResult`, `resume`, and
 * `unstable_recordInteraction`.
 * For data parts, adds `dataRendererUI`.
 *
 * The render function is also invoked once with a synthetic empty text part
 * (`{ type: "text", text: "", status: { type: "running" } }`) when the
 * assistant message has no parts yet but is in the running state, so a
 * loading indicator can render. Differentiate this from a real empty text
 * via `part.status?.type === "running" && part.text === ""`.
 */
export type EnrichedPartState = (Extract<PartState, {
    type: "tool-call";
}> & {
    /** The registered tool UI element, or null if none registered. */
    readonly toolUI: ReactNode;
    /** Add a tool result to this tool call. */
    addResult: ToolCallMessagePartProps["addResult"];
    /** Resume a tool call waiting for human input. */
    resume: ToolCallMessagePartProps["resume"];
    /** Respond to a server-side tool approval gate. */
    respondToApproval: ToolCallMessagePartProps["respondToApproval"];
    unstable_recordInteraction?: ToolCallMessagePartProps["unstable_recordInteraction"] | undefined;
}) | (Extract<PartState, {
    type: "data";
}> & {
    /** The registered data renderer UI element, or null if none registered. */
    readonly dataRendererUI: ReactNode;
}) | Exclude<PartState, {
    type: "tool-call";
} | {
    type: "data";
}>;
/**
 * Renders a single part by index, calling `children` with the
 * {@link EnrichedPartState} (tool/data UI enrichments + tool methods).
 * Shared between `<MessagePrimitive.Parts>` and
 * `<MessagePrimitive.GroupedParts>`. Returns whatever `children`
 * returns — callers decide how to handle a `null` return.
 */
type MessagePartChildrenProps = {
    index: number;
    children: (value: {
        part: EnrichedPartState;
    }) => ReactNode;
};
export declare const MessagePartChildren: FC<MessagePartChildrenProps>;
/**
 * Renders the parts of a message with support for multiple content types.
 *
 * This is the platform-agnostic base. Each platform wraps this with its own
 * default components (web uses `<p>`, `<span>`; RN would use `<Text>`, etc.).
 */
export declare const MessagePrimitiveParts: FC<MessagePrimitiveParts.Props>;