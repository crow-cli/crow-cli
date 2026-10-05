import type { Tool } from "assistant-stream";
type AuiToolOverride<TArgs extends Record<string, unknown> = Record<string, unknown>, TResult = unknown> = Partial<Tool<TArgs, TResult>>;
type AuiToolOverrides = Record<string, AuiToolOverride<any, any>>;
/**
 * Overrides toolkit entries for the current assistant scope.
 *
 * This is intended for dynamic local-state tools whose model-facing contract is
 * declared in a `"use generative"` toolkit file with `execute: stubTool()`, but
 * whose actual executor must close over React state in the mounted component.
 * Keep the override keys stable after mount; dynamic key addition/removal is not
 * currently observed.
 * Overrides are registered at priority 1000, above toolkit defaults. Only one
 * mounted override provider may define a given tool name at a time.
 *
 * @deprecated Experimental, API may change.
 */
export declare function useAuiToolOverrides(overrides: AuiToolOverrides): void;
export {};