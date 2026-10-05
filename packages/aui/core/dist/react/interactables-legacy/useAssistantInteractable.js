import { useJSONSchemaDependency } from "../utils/useJSONSchemaDependency.js";
import { useEffect, useId, useRef } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/react/interactables-legacy/useAssistantInteractable.ts
/**
* @deprecated Since 2026-06-14 — migrate to the Unstable / Experimental API.
* Scheduled for removal on/after 2026-09-14. See
* {@link https://www.assistant-ui.com/docs/tools/interactables#migrating-from-the-previous-api | Interactables migration guide}.
*
* Registers an interactable with the AI assistant.
*
* This hook handles registration only. To read and write the interactable's
* state, use {@link useInteractableState} with the returned id.
*
* @returns The interactable instance id.
*/
const useAssistantInteractable = (name, config) => {
	const aui = useAui();
	const autoId = useId().replace(/[^a-zA-Z0-9]/g, "");
	const id = config.id ?? autoId;
	const stateSchemaRef = useRef(config.stateSchema);
	stateSchemaRef.current = config.stateSchema;
	const normalizedStateSchema = useJSONSchemaDependency(config.stateSchema);
	const initialStateRef = useRef(config.initialState);
	initialStateRef.current = config.initialState;
	useEffect(() => {
		return aui.interactables.register({
			id,
			name,
			description: config.description,
			stateSchema: stateSchemaRef.current,
			initialState: initialStateRef.current,
			selected: config.selected
		});
	}, [
		aui,
		id,
		name,
		config.description,
		normalizedStateSchema,
		config.selected
	]);
	return id;
};
//#endregion
export { useAssistantInteractable };
