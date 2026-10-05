import { type ComponentType, type FC } from "react";
import type { GenerativeUISpec } from "../../../types/message.js";
import type { GenerativeUIComponentRegistry, GenerativeUIRenderProps } from "../../types/MessagePartComponentTypes.js";
/**
 * Thrown when a generative-ui spec references a component name that is not
 * present in the consumer-provided allowlist. The allowlist is the security
 * boundary in the same-realm rendering path — there is no fallback by
 * default. Pass `Fallback` to opt into a soft-fail UX.
 */
export declare class GenerativeUIRenderError extends Error {
    readonly componentName: string;
    constructor(componentName: string, message?: string);
}
/**
 * Internal renderer. Resolves a {@link GenerativeUISpec} against the consumer
 * allowlist. Used by `MessagePrimitive.GenerativeUI` and by
 * `MessagePrimitive.Parts` when handling a `generative-ui` part.
 */
export declare const GenerativeUIRender: FC<GenerativeUIRenderProps>;
export declare namespace MessagePrimitiveGenerativeUI {
    type Props = {
        /**
         * The component allowlist. Keys are the names referenced in the spec
         * (e.g. `"Card"`, `"Button"`), values are the React components.
         *
         * This is the security boundary — any name not in the allowlist is
         * rejected with {@link GenerativeUIRenderError}.
         */
        components: GenerativeUIComponentRegistry;
        /**
         * Optional override spec. If omitted, the primitive reads the
         * `generative-ui` part from the surrounding `MessagePartProvider` /
         * `PartByIndexProvider` context.
         */
        spec?: GenerativeUISpec | undefined;
        /** Optional fallback for unknown component names. */
        Fallback?: ComponentType<{
            component: string;
            props?: unknown;
        }> | undefined;
    };
}
/**
 * Renders a generative-ui message part using a consumer-provided allowlist.
 *
 * The agent emits a `generative-ui` message part containing a JSON spec
 * (see {@link GenerativeUISpec}). This primitive walks the spec and resolves
 * each `component` name against the allowlist. Names not in the allowlist
 * throw {@link GenerativeUIRenderError} unless a `Fallback` is provided.
 *
 * Stream-friendly: a partial spec renders progressively as it is filled in.
 *
 * @example
 * ```tsx
 * <MessagePrimitive.GenerativeUI
 *   components={{ Card: MyCard, Button: MyButton }}
 * />
 * ```
 */
export declare const MessagePrimitiveGenerativeUI: FC<MessagePrimitiveGenerativeUI.Props>;