import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useEffect } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
//#region src/react/model-context/useAssistantInstructions.ts
const getInstructions = (instruction) => {
	if (typeof instruction === "string") return { instruction };
	return instruction;
};
const useAssistantInstructions = (config) => {
	const $ = c(7);
	let t0;
	if ($[0] !== config) {
		t0 = getInstructions(config);
		$[0] = config;
		$[1] = t0;
	} else t0 = $[1];
	const { instruction, disabled: t1 } = t0;
	const disabled = t1 === void 0 ? false : t1;
	const aui = useAui();
	let t2;
	let t3;
	if ($[2] !== aui || $[3] !== disabled || $[4] !== instruction) {
		t2 = () => {
			if (disabled) return;
			const config_0 = { system: instruction };
			return aui.modelContext.register({ getModelContext: () => config_0 });
		};
		t3 = [
			aui,
			instruction,
			disabled
		];
		$[2] = aui;
		$[3] = disabled;
		$[4] = instruction;
		$[5] = t2;
		$[6] = t3;
	} else {
		t2 = $[5];
		t3 = $[6];
	}
	useEffect(t2, t3);
};
//#endregion
export { useAssistantInstructions };
