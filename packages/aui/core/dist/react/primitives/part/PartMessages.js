import { ReadonlyThreadProvider } from "../../providers/ReadonlyThreadProvider.js";
import { ThreadPrimitiveMessagesImpl } from "../thread/ThreadMessages.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { memo } from "@assistant-ui/tap/react-shim";
import { useAuiState } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
//#region src/react/primitives/part/PartMessages.tsx
const usePartMessages = () => {
	return useAuiState(_temp);
};
/**
* Renders the nested messages of a tool call part (e.g. sub-agent conversation).
*
* This primitive reads `messages` from the current tool call part in the PartScope
* and renders them using a readonly thread context. All existing message and part
* primitives work inside, and parent tool UI registrations are inherited.
* The nested thread reports `isRunning` while its trailing assistant message is running.
*
* @example
* ```tsx
* const toolkit = defineToolkit({
*   invoke_sub_agent: {
*     type: "backend",
*     render: () => (
*       <PartPrimitive.Messages>
*         {({ message }) => {
*           if (message.role === "user") return <MyUserMessage />;
*           return <MyAssistantMessage />;
*         }}
*       </PartPrimitive.Messages>
*     ),
*   },
* });
* ```
*/
const PartPrimitiveMessagesImpl = (t0) => {
	const $ = c(10);
	const { components, children } = t0;
	const messages = usePartMessages();
	if (!messages?.length) return null;
	if (components) {
		let t1;
		if ($[0] !== components) {
			t1 = /* @__PURE__ */ jsx(ThreadPrimitiveMessagesImpl, { components });
			$[0] = components;
			$[1] = t1;
		} else t1 = $[1];
		let t2;
		if ($[2] !== messages || $[3] !== t1) {
			t2 = /* @__PURE__ */ jsx(ReadonlyThreadProvider, {
				messages,
				children: t1
			});
			$[2] = messages;
			$[3] = t1;
			$[4] = t2;
		} else t2 = $[4];
		return t2;
	}
	let t1;
	if ($[5] !== children) {
		t1 = /* @__PURE__ */ jsx(ThreadPrimitiveMessagesImpl, { children });
		$[5] = children;
		$[6] = t1;
	} else t1 = $[6];
	let t2;
	if ($[7] !== messages || $[8] !== t1) {
		t2 = /* @__PURE__ */ jsx(ReadonlyThreadProvider, {
			messages,
			children: t1
		});
		$[7] = messages;
		$[8] = t1;
		$[9] = t2;
	} else t2 = $[9];
	return t2;
};
PartPrimitiveMessagesImpl.displayName = "PartPrimitive.Messages";
const PartPrimitiveMessages = memo(PartPrimitiveMessagesImpl);
function _temp(s) {
	const part = s.part;
	if (part.type !== "tool-call") return;
	return "messages" in part ? part.messages : void 0;
}
//#endregion
export { PartPrimitiveMessages, PartPrimitiveMessagesImpl };
