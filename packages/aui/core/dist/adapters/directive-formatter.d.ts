import type { Unstable_DirectiveFormatter } from "../types/directive.js";
/**
 * Default directive formatter using the `:type[label]{name=id}` syntax.
 *
 * When `id` equals `label`, the `{name=…}` attribute is omitted for brevity.
 */
export declare const unstable_defaultDirectiveFormatter: Unstable_DirectiveFormatter;