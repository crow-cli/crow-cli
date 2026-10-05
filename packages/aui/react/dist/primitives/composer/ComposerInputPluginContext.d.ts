import { type ReactNode, type FC } from "react";
/**
 * A plugin that intercepts keyboard events and cursor changes in the composer
 * input. Used by trigger popover declarations to handle popover navigation
 * without ComposerInput knowing about specific triggers.
 */
export type ComposerInputPlugin = {
    /** Handle a key event. Return true if consumed (stops propagation to other plugins and default behavior). */
    handleKeyDown(e: {
        readonly key: string;
        readonly shiftKey: boolean;
        readonly ctrlKey?: boolean;
        readonly metaKey?: boolean;
        readonly nativeEvent?: {
            isComposing?: boolean;
        };
        preventDefault(): void;
    }): boolean;
    /** Called on every cursor position change (selection change / text change). */
    setCursorPosition(pos: number): void;
};
/** Options for registering a plugin. */
export type ComposerInputPluginRegisterOptions = {
    /**
     * Relative priority. Plugins with higher priority receive events first.
     * @default 0
     */
    priority?: number;
};
export type ComposerInputPluginRegistry = {
    register(plugin: ComposerInputPlugin, opts?: ComposerInputPluginRegisterOptions): () => void;
    getPlugins(): readonly ComposerInputPlugin[];
};
export declare const useComposerInputPluginRegistryOptional: () => ComposerInputPluginRegistry | null;
export declare const ComposerInputPluginProvider: FC<{
    children: ReactNode;
}>;