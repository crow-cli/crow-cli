import { nullProtoRecord } from "../../utils/record.js";
import { getPartialJsonObjectFieldState, getPartialJsonObjectMeta } from "assistant-stream/utils";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
//#region src/react/model-context/useToolArgsStatus.ts
/**
* Reads whether each argument field for the current tool-call message part is
* still streaming or complete.
*
* Use inside a tool-call renderer to avoid showing incomplete argument values
* as final.
*
* @throws If called outside a tool-call message part.
*
* @example
* ```tsx
* function WeatherToolUI({
*   args,
* }: ToolCallMessagePartProps<{ city: string }>) {
*   const { propStatus } = useToolArgsStatus<{ city: string }>();
*
*   return (
*     <span>
*       {propStatus.city === "streaming" ? "Reading city..." : args.city}
*     </span>
*   );
* }
* ```
*/
const useToolArgsStatus = () => {
	const $ = c(9);
	const part = useAuiState(_temp);
	let t0;
	const statusType = part.status.type;
	if (part.type !== "tool-call") throw new Error("useToolArgsStatus can only be used inside tool-call message parts");
	const isStreaming = statusType === "running";
	const args = part.args;
	const t1 = args;
	let t2;
	if ($[0] !== t1) {
		t2 = getPartialJsonObjectMeta(t1);
		$[0] = t1;
		$[1] = t2;
	} else t2 = $[1];
	const meta = t2;
	let propStatus;
	if ($[2] !== args || $[3] !== isStreaming || $[4] !== meta) {
		propStatus = nullProtoRecord();
		for (const key of Object.keys(args)) if (meta) {
			const fieldState = getPartialJsonObjectFieldState(args, [key]);
			propStatus[key] = fieldState === "complete" || !isStreaming ? "complete" : "streaming";
		} else propStatus[key] = isStreaming ? "streaming" : "complete";
		$[2] = args;
		$[3] = isStreaming;
		$[4] = meta;
		$[5] = propStatus;
	} else propStatus = $[5];
	const t3 = propStatus;
	let t4;
	if ($[6] !== statusType || $[7] !== t3) {
		t4 = {
			status: statusType,
			propStatus: t3
		};
		$[6] = statusType;
		$[7] = t3;
		$[8] = t4;
	} else t4 = $[8];
	t0 = t4;
	return t0;
};
function _temp(s) {
	return s.part;
}
//#endregion
export { useToolArgsStatus };
