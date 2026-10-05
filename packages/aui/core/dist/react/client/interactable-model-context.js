import { generateId } from "../../utils/id.js";
import { nullProtoRecord } from "../../utils/record.js";
import { isRecord } from "../../utils/json/is-json.js";
import { interactableToolName, shallowMergeInteractableState } from "../../model-context/interactable-composer-metadata.js";
import "assistant-stream";
import { getPartialJsonObjectMeta } from "assistant-stream/utils";
//#region src/react/client/interactable-model-context.ts
const ID_PROPERTY = {
	type: "string",
	description: "The id of the instance to update, as shown in its state snapshot in the conversation."
};
const ITEM_ID_PROPERTY = {
	type: "string",
	description: "The id of an item currently in this list."
};
const hasIdProperty = (schema) => {
	const properties = schema.properties;
	return isRecord(properties) && properties.id !== void 0;
};
const withRequiredItemId = (schema) => ({
	...schema,
	required: ["id"]
});
const withoutItemId = (schema) => {
	const { id: _omitted, ...properties } = isRecord(schema.properties) ? schema.properties : {};
	const required = Array.isArray(schema.required) ? schema.required.filter((key) => key !== "id") : schema.required;
	return {
		...schema,
		properties,
		required
	};
};
const toArrayUpdateSchema = (schema, field) => {
	if (!isRecord(schema) || schema.type !== "array") return schema;
	const itemSchema = schema.items;
	if (Array.isArray(itemSchema) || !isRecord(itemSchema)) return schema;
	const idKeyed = hasIdProperty(itemSchema);
	const properties = {
		add: {
			type: "array",
			items: idKeyed ? withoutItemId(itemSchema) : itemSchema
		},
		remove: {
			type: "array",
			items: idKeyed ? ITEM_ID_PROPERTY : itemSchema
		},
		clear: { type: "boolean" }
	};
	if (idKeyed) properties.update = {
		type: "array",
		items: withRequiredItemId(itemSchema)
	};
	return {
		type: "object",
		description: `Operations for array field "${field}". To change one item use update with its id; add new items (their ids are assigned for you), remove items by id, or clear to empty. Change only the items you mean to — never resend the whole array to edit one item.`,
		properties,
		additionalProperties: false
	};
};
const idKeyedArrayFieldNames = (properties) => {
	const names = /* @__PURE__ */ new Set();
	for (const [key, value] of Object.entries(properties)) if (isRecord(value) && value.type === "array" && isRecord(value.items) && hasIdProperty(value.items)) names.add(key);
	return names;
};
const withArrayUpdateSchemas = (properties) => Object.fromEntries(Object.entries(properties).map(([key, value]) => [key, toArrayUpdateSchema(value, key)]));
/**
* Replaces the state schema's root `required` list with the `id` parameter,
* so every top-level field is optional while nested objects keep theirs and
* travel whole through the shallow merge. Falls back to a permissive schema
* when the JSON Schema conversion failed at registration time.
*/
function withRequiredId(schema) {
	if (!schema || typeof schema !== "object" || schema.type !== "object") return {
		type: "object",
		properties: { id: ID_PROPERTY },
		required: ["id"],
		additionalProperties: true
	};
	if (process.env.NODE_ENV !== "production" && schema.properties?.id) console.warn("[Interactables] a top-level \"id\" field in an interactable's stateSchema is reserved for instance addressing by the update tool and cannot be updated by the model. Rename the field to make it model-writable.");
	const { id: _reserved, ...properties } = schema.properties ?? {};
	return {
		...schema,
		properties: {
			id: ID_PROPERTY,
			...withArrayUpdateSchemas(properties)
		},
		required: ["id"]
	};
}
function buildInteractableModelContext(definitions, schemaCache, setDefState, getCurrentDefinitions, streamBaselines = /* @__PURE__ */ new Map()) {
	const entries = Object.values(definitions);
	if (entries.length === 0) return void 0;
	const byName = /* @__PURE__ */ new Map();
	for (const def of entries) {
		const list = byName.get(def.name) ?? [];
		list.push(def);
		byName.set(def.name, list);
	}
	const tools = {};
	for (const [name, instances] of byName) {
		const toolName = interactableToolName(name);
		if (tools[toolName]) {
			if (process.env.NODE_ENV !== "production") console.warn(`[Interactables] interactable names "${name}" and another registered name both sanitize to the tool name "${toolName}". Rename one of them.`);
			continue;
		}
		const first = instances[0];
		const jsonSchema = schemaCache.get(first.id);
		const idKeyedFields = jsonSchema && isRecord(jsonSchema.properties) ? idKeyedArrayFieldNames(jsonSchema.properties) : /* @__PURE__ */ new Set();
		const resolveTarget = (id) => {
			if (typeof id === "string") {
				const def = definitions[id];
				return def?.name === name ? def : void 0;
			}
			return instances.length === 1 ? first : void 0;
		};
		tools[toolName] = {
			type: "frontend",
			description: `Update the state of interactable component "${name}". ${first.description} Pass the id of the instance to update — instance ids and current state appear in the conversation as state snapshots. Only include the fields you want to change; omitted fields keep their current values. A nested object replaces the existing one, so send it complete.`,
			parameters: withRequiredId(jsonSchema),
			streamCall: async (reader, { toolCallId }) => {
				try {
					for await (const partialArgs of reader.args.streamValues()) {
						if (!partialArgs || typeof partialArgs !== "object") continue;
						const args = partialArgs;
						const keys = Object.keys(args);
						if (keys.indexOf("id") === keys.length - 1) continue;
						const { id, ...partial } = args;
						if (Object.keys(partial).length === 0) continue;
						const target = resolveTarget(id);
						if (!target) continue;
						const currentTarget = getCurrentDefinitions()[target.id];
						if (currentTarget?.name !== name) continue;
						const baseline = streamBaselines.get(toolCallId);
						const arrayBaseline = baseline?.targetId === target.id ? baseline.state : currentTarget.state;
						if (!baseline || baseline.targetId !== target.id) streamBaselines.set(toolCallId, {
							targetId: target.id,
							state: currentTarget.state
						});
						const partialPath = getPartialJsonObjectMeta(args)?.partialPath;
						setDefState(target.id, (prev) => shallowMergeInteractableState(prev, partial, {
							arrayBaseline,
							partialPath
						}));
					}
				} catch {}
			},
			execute: async (args, { toolCallId }) => {
				const { id, ...partial } = args ?? {};
				const target = resolveTarget(id);
				const currentDefinitions = getCurrentDefinitions();
				const currentTarget = target ? currentDefinitions[target.id] : void 0;
				if (!currentTarget || currentTarget.name !== name) {
					const validIds = Object.values(currentDefinitions).filter((def) => def.name === name).map((def) => def.id);
					return {
						success: false,
						error: `Unknown id ${JSON.stringify(id)} for interactable "${name}". Valid ids: ${validIds.join(", ")}`
					};
				}
				const baseline = streamBaselines.get(toolCallId);
				streamBaselines.delete(toolCallId);
				const addedItemIds = nullProtoRecord();
				setDefState(currentTarget.id, (prev) => shallowMergeInteractableState(prev, partial, {
					arrayBaseline: baseline?.targetId === currentTarget.id ? baseline.state : void 0,
					idFactory: (field) => {
						const itemId = generateId();
						(addedItemIds[field] ??= []).push(itemId);
						return itemId;
					},
					idKeyedFields
				}));
				const result = {
					success: true,
					id: currentTarget.id
				};
				if (Object.keys(addedItemIds).length > 0) result.addedItemIds = { ...addedItemIds };
				return result;
			}
		};
	}
	return {
		tools,
		unstable_composerMetadata: { interactables: entries.map((def) => ({
			id: def.id,
			name: def.name,
			state: def.state
		})) }
	};
}
//#endregion
export { buildInteractableModelContext };
