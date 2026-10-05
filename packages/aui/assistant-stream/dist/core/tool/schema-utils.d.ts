import type { JSONSchema7 } from "json-schema";
import type { StandardSchemaV1 } from "@standard-schema/spec";
import type { ProviderOptions, Tool } from "./tool-types.js";
/**
 * Type for a tool definition with JSON Schema parameters.
 */
export type ToolJSONSchema = {
    description?: string;
    parameters: JSONSchema7;
    providerOptions?: ProviderOptions;
};
export type ToToolsJSONSchemaOptions = {
    /**
     * Filter to determine which tools to include.
     * Defaults to excluding disabled tools and backend tools.
     *
     * Tools with backend-default parameters are always excluded.
     */
    filter?: (name: string, tool: Tool) => boolean;
};
/**
 * Converts a schema to JSONSchema7.
 * Supports:
 * - StandardSchemaV1 with ~standard.jsonSchema.input() (e.g., Zod v4)
 * - Objects with toJSONSchema() method
 * - Objects with toJSON() method
 * - Plain JSONSchema7 objects
 *
 * Every path that takes options is asked for draft-07. Only `~standard.jsonSchema`
 * declares the option type it accepts, so only its answer is held to it; the
 * duck-typed paths pass through in whatever dialect they return.
 */
export declare function toJSONSchema(schema: StandardSchemaV1 | JSONSchema7): JSONSchema7;
/**
 * Returns a copy of the JSON Schema with `required` removed recursively,
 * making every property optional. Array item schemas are left unchanged.
 */
export declare function toPartialJSONSchema(schema: JSONSchema7): JSONSchema7;
/**
 * Converts a record of tools to a record of tool definitions with JSON Schema parameters.
 * By default, filters out disabled tools and backend tools.
 *
 * Entries are emitted in alphabetical order so the resulting request body is
 * byte-identical regardless of the order in which tools were registered. This
 * keeps provider prompt caches stable across renders that mount tools in
 * different orders.
 */
export declare function toToolsJSONSchema(tools: Record<string, Tool> | undefined, options?: ToToolsJSONSchemaOptions): Record<string, ToolJSONSchema>;