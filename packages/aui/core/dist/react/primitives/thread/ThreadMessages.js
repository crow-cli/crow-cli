import { MessageByIndexProvider } from "../../providers/MessageByIndexProvider.js";
import { MessageByIdProvider } from "../../providers/MessageByIdProvider.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { memo, useMemo } from "@assistant-ui/tap/react-shim";
import { RenderChildrenWithAccessor, useAuiState } from "@assistant-ui/store";
import { useShallowSelector } from "@assistant-ui/store/internal";
import { jsx } from "react/jsx-runtime";
//#region src/react/primitives/thread/ThreadMessages.tsx
const isComponentsSame = (prev, next) => {
	return prev.Message === next.Message && prev.EditComposer === next.EditComposer && prev.UserEditComposer === next.UserEditComposer && prev.AssistantEditComposer === next.AssistantEditComposer && prev.SystemEditComposer === next.SystemEditComposer && prev.UserMessage === next.UserMessage && prev.AssistantMessage === next.AssistantMessage && prev.SystemMessage === next.SystemMessage;
};
const DEFAULT_SYSTEM_MESSAGE = () => null;
const messageIdSetCache = /* @__PURE__ */ new WeakMap();
const hasMessageId = (messages, messageId) => {
	let ids = messageIdSetCache.get(messages);
	if (!ids) {
		ids = new Set(messages.map((m) => m.id));
		messageIdSetCache.set(messages, ids);
	}
	return ids.has(messageId);
};
const getComponent = (components, role, isEditing) => {
	switch (role) {
		case "user": if (isEditing) return components.UserEditComposer ?? components.EditComposer ?? components.UserMessage ?? components.Message;
		else return components.UserMessage ?? components.Message;
		case "assistant": if (isEditing) return components.AssistantEditComposer ?? components.EditComposer ?? components.AssistantMessage ?? components.Message;
		else return components.AssistantMessage ?? components.Message;
		case "system": if (isEditing) return components.SystemEditComposer ?? components.EditComposer ?? components.SystemMessage ?? components.Message ?? DEFAULT_SYSTEM_MESSAGE;
		else return components.SystemMessage ?? components.Message ?? DEFAULT_SYSTEM_MESSAGE;
		default: throw new Error(`Unknown message role: ${role}`);
	}
};
const ThreadMessageComponent = (t0) => {
	const $ = c(6);
	const { components } = t0;
	const role = useAuiState(_temp);
	const isEditing = useAuiState(_temp2);
	let t1;
	if ($[0] !== components || $[1] !== isEditing || $[2] !== role) {
		t1 = getComponent(components, role, isEditing);
		$[0] = components;
		$[1] = isEditing;
		$[2] = role;
		$[3] = t1;
	} else t1 = $[3];
	const Component = t1;
	let t2;
	if ($[4] !== Component) {
		t2 = /* @__PURE__ */ jsx(Component, {});
		$[4] = Component;
		$[5] = t2;
	} else t2 = $[5];
	return t2;
};
/**
* Renders a single message at the specified index in the current thread.
*/
const ThreadPrimitiveMessageByIndex = memo((t0) => {
	const $ = c(5);
	const { index, components } = t0;
	let t1;
	if ($[0] !== components) {
		t1 = /* @__PURE__ */ jsx(ThreadMessageComponent, { components });
		$[0] = components;
		$[1] = t1;
	} else t1 = $[1];
	let t2;
	if ($[2] !== index || $[3] !== t1) {
		t2 = /* @__PURE__ */ jsx(MessageByIndexProvider, {
			index,
			children: t1
		});
		$[2] = index;
		$[3] = t1;
		$[4] = t2;
	} else t2 = $[4];
	return t2;
}, (prev, next) => prev.index === next.index && isComponentsSame(prev.components, next.components));
ThreadPrimitiveMessageByIndex.displayName = "ThreadPrimitive.MessageByIndex";
/**
* Renders the message with the given id in the current thread.
*
* Unlike {@link ThreadPrimitiveMessageByIndex}, this keys off the message id,
* so it stays attached to the same message across reordering and windowing -
* the shape needed to drive a virtualized or custom message list together with
* `unstable_useThreadMessageIds`. A missing or removed id renders `null` rather
* than throwing.
*
* @deprecated Unstable / Experimental - may change in any release.
*
* @example
* ```tsx
* const messageIds = unstable_useThreadMessageIds();
* return messageIds.map((messageId) => (
*   <ThreadPrimitive.Unstable_MessageById
*     key={messageId}
*     messageId={messageId}
*     components={MESSAGE_COMPONENTS}
*   />
* ));
* ```
*/
const ThreadPrimitiveUnstable_MessageById = memo((t0) => {
	const $ = c(7);
	const { messageId, components } = t0;
	let t1;
	if ($[0] !== messageId) {
		t1 = (s) => hasMessageId(s.thread.messages, messageId);
		$[0] = messageId;
		$[1] = t1;
	} else t1 = $[1];
	if (!useAuiState(t1)) return null;
	let t2;
	if ($[2] !== components) {
		t2 = /* @__PURE__ */ jsx(ThreadMessageComponent, { components });
		$[2] = components;
		$[3] = t2;
	} else t2 = $[3];
	let t3;
	if ($[4] !== messageId || $[5] !== t2) {
		t3 = /* @__PURE__ */ jsx(MessageByIdProvider, {
			id: messageId,
			children: t2
		});
		$[4] = messageId;
		$[5] = t2;
		$[6] = t3;
	} else t3 = $[6];
	return t3;
}, (prev, next) => prev.messageId === next.messageId && isComponentsSame(prev.components, next.components));
ThreadPrimitiveUnstable_MessageById.displayName = "ThreadPrimitive.Unstable_MessageById";
const ThreadPrimitiveMessagesInner = ({ children }) => {
	const messageIds = useAuiState(useShallowSelector((s) => s.thread.messages.map((message) => message.id)));
	return useMemo(() => {
		if (messageIds.length === 0) return null;
		return messageIds.map((messageId, index) => /* @__PURE__ */ jsx(MessageByIndexProvider, {
			index,
			children: /* @__PURE__ */ jsx(RenderChildrenWithAccessor, {
				getItemState: (aui) => aui.thread.message({ index }).getState(),
				children: (getItem) => children({ get message() {
					return getItem();
				} })
			})
		}, messageId));
	}, [messageIds, children]);
};
/**
* Renders all messages in the current thread.
*
* @example
* ```tsx
* <ThreadPrimitive.Messages>
*   {({ message }) => {
*     if (message.role === "user") return <MyUserMessage />;
*     return <MyAssistantMessage />;
*   }}
* </ThreadPrimitive.Messages>
* ```
*/
const ThreadPrimitiveMessagesImpl = (t0) => {
	const $ = c(4);
	const { components, children } = t0;
	if (components) {
		let t1;
		if ($[0] !== components) {
			t1 = /* @__PURE__ */ jsx(ThreadPrimitiveMessagesInner, { children: () => /* @__PURE__ */ jsx(ThreadMessageComponent, { components }) });
			$[0] = components;
			$[1] = t1;
		} else t1 = $[1];
		return t1;
	}
	let t1;
	if ($[2] !== children) {
		t1 = /* @__PURE__ */ jsx(ThreadPrimitiveMessagesInner, { children });
		$[2] = children;
		$[3] = t1;
	} else t1 = $[3];
	return t1;
};
ThreadPrimitiveMessagesImpl.displayName = "ThreadPrimitive.Messages";
const ThreadPrimitiveMessages = memo(ThreadPrimitiveMessagesImpl, (prev, next) => {
	if (prev.children || next.children) return prev.children === next.children;
	return isComponentsSame(prev.components, next.components);
});
function _temp(s) {
	return s.message.role;
}
function _temp2(s_0) {
	return s_0.message.composer.isEditing;
}
//#endregion
export { ThreadPrimitiveMessageByIndex, ThreadPrimitiveMessages, ThreadPrimitiveMessagesImpl, ThreadPrimitiveUnstable_MessageById };
