import { getMessagePartKeys } from "../../../utils/getMessagePartKeys.js";
import { ChainOfThoughtPartsContext } from "../../providers/ChainOfThoughtByIndicesProvider.js";
import { ChainOfThoughtPartByIndexProvider } from "../../providers/ChainOfThoughtPartByIndexProvider.js";
import { MessagePartComponent } from "../message/MessageParts.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { useContext, useMemo } from "@assistant-ui/tap/react-shim";
import { RenderChildrenWithAccessor, useAuiState } from "@assistant-ui/store";
import { useShallowSelector } from "@assistant-ui/store/internal";
import { jsx } from "react/jsx-runtime";
//#region src/react/primitives/chainOfThought/ChainOfThoughtParts.tsx
const ChainOfThoughtPrimitivePartsInner = ({ children }) => {
	const partsContext = useContext(ChainOfThoughtPartsContext);
	const partKeys = useAuiState(useShallowSelector((s) => partsContext?.partKeys ?? getMessagePartKeys(s.chainOfThought.parts)));
	return useMemo(() => partKeys.map((key, index) => /* @__PURE__ */ jsx(ChainOfThoughtPartByIndexProvider, {
		index,
		children: /* @__PURE__ */ jsx(RenderChildrenWithAccessor, {
			getItemState: (aui) => aui.part.getState(),
			children: (getItem) => children({ get part() {
				return getItem();
			} })
		})
	}, key)), [partKeys, children]);
};
/**
* Renders the parts within a chain of thought, with support for collapsed/expanded states.
*
* When collapsed, no parts are shown. When expanded, all parts are rendered
* using the provided component configuration through the part scope mechanism.
*/
const ChainOfThoughtPrimitiveParts = (t0) => {
	const $ = c(10);
	const { components, children } = t0;
	if (children) {
		let t1;
		if ($[0] !== children) {
			t1 = /* @__PURE__ */ jsx(ChainOfThoughtPrimitivePartsInner, { children });
			$[0] = children;
			$[1] = t1;
		} else t1 = $[1];
		return t1;
	}
	components?.Reasoning;
	components?.tools?.Fallback;
	const t1 = components?.Reasoning;
	const t2 = components?.tools?.Fallback;
	let t3;
	if ($[2] !== t2) {
		t3 = { Fallback: t2 };
		$[2] = t2;
		$[3] = t3;
	} else t3 = $[3];
	let t4;
	if ($[4] !== t1 || $[5] !== t3) {
		t4 = {
			Reasoning: t1,
			tools: t3
		};
		$[4] = t1;
		$[5] = t3;
		$[6] = t4;
	} else t4 = $[6];
	const messageComponents = t4;
	const Layout = components?.Layout;
	let t5;
	if ($[7] !== Layout || $[8] !== messageComponents) {
		t5 = /* @__PURE__ */ jsx(ChainOfThoughtPrimitivePartsInner, { children: () => Layout ? /* @__PURE__ */ jsx(Layout, { children: /* @__PURE__ */ jsx(MessagePartComponent, { components: messageComponents }) }) : /* @__PURE__ */ jsx(MessagePartComponent, { components: messageComponents }) });
		$[7] = Layout;
		$[8] = messageComponents;
		$[9] = t5;
	} else t5 = $[9];
	return t5;
};
ChainOfThoughtPrimitiveParts.displayName = "ChainOfThoughtPrimitive.Parts";
//#endregion
export { ChainOfThoughtPrimitiveParts };
