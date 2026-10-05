import { __exportAll } from "../_virtual/_rolldown/runtime.js";
import { SuggestionPrimitiveTitle } from "./suggestion/SuggestionTitle.js";
import { SuggestionPrimitiveDescription } from "./suggestion/SuggestionDescription.js";
import { SuggestionPrimitiveTrigger } from "./suggestion/SuggestionTrigger.js";
//#region src/primitives/suggestion.ts
var suggestion_exports = /* @__PURE__ */ __exportAll({
	Description: () => SuggestionPrimitiveDescription,
	Title: () => SuggestionPrimitiveTitle,
	Trigger: () => SuggestionPrimitiveTrigger
});
//#endregion
export { SuggestionPrimitiveDescription as Description, SuggestionPrimitiveTitle as Title, SuggestionPrimitiveTrigger as Trigger, suggestion_exports };
