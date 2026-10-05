import { overlayPartialPath } from "../../model-context/interactable-composer-metadata.js";
import { getPartialJsonObjectMeta } from "assistant-stream/utils";
//#region src/react/interactables-legacy/interactable-model-context.ts
const withoutRootRequired = ({ required: _required, ...schema }) => schema;
function buildInteractableModelContext(definitions, schemaCache, setDefState) {
	const entries = Object.values(definitions);
	if (entries.length === 0) return void 0;
	const byName = /* @__PURE__ */ new Map();
	for (const def of entries) {
		const list = byName.get(def.name) ?? [];
		list.push(def);
		byName.set(def.name, list);
	}
	const systemParts = [];
	const tools = {};
	for (const [name, instances] of byName) {
		const isMulti = instances.length > 1;
		for (const def of instances) {
			const selectedTag = def.selected ? " (SELECTED)" : "";
			const idTag = isMulti ? ` [id="${def.id}"]` : "";
			systemParts.push(`Interactable component "${name}"${idTag}${selectedTag} (${def.description}). Current state: ${JSON.stringify(def.state)}`);
			const safeName = name.replace(/[^a-zA-Z0-9_-]/g, "_");
			const safeId = def.id.replace(/[^a-zA-Z0-9_-]/g, "_");
			const toolName = isMulti ? `update_${safeName}_${safeId}` : `update_${safeName}`;
			const jsonSchema = schemaCache.get(def.id);
			tools[toolName] = {
				type: "frontend",
				description: `Update the state of interactable component "${name}"${isMulti ? ` (id: ${def.id})` : ""}. Only include the fields you want to change; omitted fields keep their current values. A nested object replaces the existing one, so send it complete. ${def.description}`,
				parameters: jsonSchema ? withoutRootRequired(jsonSchema) : def.stateSchema,
				streamCall: async (reader) => {
					try {
						for await (const partialArgs of reader.args.streamValues()) {
							const partialPath = getPartialJsonObjectMeta(partialArgs)?.partialPath;
							setDefState(def.id, (prev) => overlayPartialPath(prev, partialArgs, partialPath));
						}
					} catch {}
				},
				execute: async (partialState) => {
					setDefState(def.id, (prev) => overlayPartialPath(prev, partialState));
					return { success: true };
				}
			};
		}
	}
	return {
		system: systemParts.join("\n"),
		tools
	};
}
//#endregion
export { buildInteractableModelContext };
