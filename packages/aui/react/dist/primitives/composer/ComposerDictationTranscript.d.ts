import { Primitive } from "../../utils/Primitive.js";
import { type ComponentRef, type ComponentPropsWithoutRef } from "react";
export declare namespace ComposerPrimitiveDictationTranscript {
    type Element = ComponentRef<typeof Primitive.span>;
    type Props = ComponentPropsWithoutRef<typeof Primitive.span>;
}
/**
 * Renders the current interim (partial) transcript while dictation is active.
 *
 * This component displays real-time feedback of what the user is saying before
 * the transcription is finalized and committed to the composer input.
 *
 * @example
 * ```tsx
 * <AuiIf condition={(s) => s.composer.dictation != null}>
 *   <div className="dictation-preview">
 *     <ComposerPrimitive.DictationTranscript />
 *   </div>
 * </AuiIf>
 * ```
 */
export declare const ComposerPrimitiveDictationTranscript: import("react").ForwardRefExoticComponent<Omit<Omit<import("react").ClassAttributes<HTMLSpanElement> & import("react").HTMLAttributes<HTMLSpanElement> & {
    asChild?: boolean;
}, "ref"> & {
    render?: import("react").ReactElement | undefined;
} & import("react").RefAttributes<HTMLSpanElement>, "ref"> & import("react").RefAttributes<HTMLSpanElement>>;