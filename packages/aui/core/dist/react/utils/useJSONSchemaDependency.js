import { isJSONValue } from "../../utils/json/is-json.js";
import { useJSONEqualValue } from "./useJSONEqual.js";
import { toJSONSchema } from "assistant-stream";
import { useMemo } from "@assistant-ui/tap/react-shim";
//#region src/react/utils/useJSONSchemaDependency.ts
function useJSONSchemaDependency(schema) {
	const normalizedSchema = useMemo(() => {
		try {
			const jsonSchema = toJSONSchema(schema);
			return isJSONValue(jsonSchema) ? jsonSchema : null;
		} catch {
			return null;
		}
	}, [schema]);
	return useJSONEqualValue(normalizedSchema);
}
//#endregion
export { useJSONSchemaDependency };
