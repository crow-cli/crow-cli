"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import "@assistant-ui/tap/react-shim";
import { useAui, useAuiState } from "@assistant-ui/store";
//#region src/primitives/chainOfThought/ChainOfThoughtAccordionTrigger.ts
const useChainOfThoughtAccordionTrigger = () => {
	const $ = c(3);
	const aui = useAui();
	const collapsed = useAuiState(_temp);
	let t0;
	if ($[0] !== aui.chainOfThought || $[1] !== collapsed) {
		t0 = () => {
			aui.chainOfThought.setCollapsed(!collapsed);
		};
		$[0] = aui.chainOfThought;
		$[1] = collapsed;
		$[2] = t0;
	} else t0 = $[2];
	return t0;
};
/**
* A button component that toggles the collapsed state of the chain of thought accordion.
*
* This component automatically handles the toggle functionality, expanding or collapsing
* the chain of thought parts when clicked.
*
* @example
* ```tsx
* <ChainOfThoughtPrimitive.AccordionTrigger>
*   Toggle Reasoning
* </ChainOfThoughtPrimitive.AccordionTrigger>
* ```
*/
const ChainOfThoughtPrimitiveAccordionTrigger = createActionButton("ChainOfThoughtPrimitive.AccordionTrigger", useChainOfThoughtAccordionTrigger);
function _temp(s) {
	return s.chainOfThought.collapsed;
}
//#endregion
export { ChainOfThoughtPrimitiveAccordionTrigger };
