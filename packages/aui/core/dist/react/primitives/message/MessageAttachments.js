import { MessageAttachmentByIndexProvider } from "../../providers/AttachmentByIndexProvider.js";
import { c } from "@assistant-ui/tap/react-shim/compiler-runtime";
import { memo, useMemo } from "@assistant-ui/tap/react-shim";
import { RenderChildrenWithAccessor, useAuiState } from "@assistant-ui/store";
import { useShallowSelector } from "@assistant-ui/store/internal";
import { jsx } from "react/jsx-runtime";
//#region src/react/primitives/message/MessageAttachments.tsx
const getComponent = (components, attachment) => {
	switch (attachment.type) {
		case "image": return components?.Image ?? components?.Attachment;
		case "document": return components?.Document ?? components?.Attachment;
		case "file": return components?.File ?? components?.Attachment;
		default: return components?.Attachment;
	}
};
const AttachmentComponent = (t0) => {
	const $ = c(5);
	const { components } = t0;
	const attachment = useAuiState(_temp);
	if (!attachment) return null;
	let t1;
	if ($[0] !== attachment || $[1] !== components) {
		t1 = getComponent(components, attachment);
		$[0] = attachment;
		$[1] = components;
		$[2] = t1;
	} else t1 = $[2];
	const Component = t1;
	if (!Component) return null;
	let t2;
	if ($[3] !== Component) {
		t2 = /* @__PURE__ */ jsx(Component, {});
		$[3] = Component;
		$[4] = t2;
	} else t2 = $[4];
	return t2;
};
/**
* Renders a single attachment at the specified index within the current message.
*/
const MessagePrimitiveAttachmentByIndex = memo((t0) => {
	const $ = c(5);
	const { index, components } = t0;
	let t1;
	if ($[0] !== components) {
		t1 = /* @__PURE__ */ jsx(AttachmentComponent, { components });
		$[0] = components;
		$[1] = t1;
	} else t1 = $[1];
	let t2;
	if ($[2] !== index || $[3] !== t1) {
		t2 = /* @__PURE__ */ jsx(MessageAttachmentByIndexProvider, {
			index,
			children: t1
		});
		$[2] = index;
		$[3] = t1;
		$[4] = t2;
	} else t2 = $[4];
	return t2;
}, (prev, next) => prev.index === next.index && prev.components?.Image === next.components?.Image && prev.components?.Document === next.components?.Document && prev.components?.File === next.components?.File && prev.components?.Attachment === next.components?.Attachment);
MessagePrimitiveAttachmentByIndex.displayName = "MessagePrimitive.AttachmentByIndex";
const MessagePrimitiveAttachmentsInner = ({ children }) => {
	const attachmentIds = useAuiState(useShallowSelector((s) => {
		if (s.message.role !== "user") return [];
		return (s.message.submission?.attachments ?? s.message.attachments ?? []).map((attachment) => attachment.id);
	}));
	return useMemo(() => attachmentIds.map((attachmentId, index) => /* @__PURE__ */ jsx(MessageAttachmentByIndexProvider, {
		index,
		children: /* @__PURE__ */ jsx(RenderChildrenWithAccessor, {
			getItemState: (aui) => aui.message.attachment({ index }).getState(),
			children: (getItem) => children({ get attachment() {
				return getItem();
			} })
		})
	}, attachmentId)), [attachmentIds, children]);
};
const MessagePrimitiveAttachments = (t0) => {
	const $ = c(4);
	const { components, children } = t0;
	if (components) {
		let t1;
		if ($[0] !== components) {
			t1 = /* @__PURE__ */ jsx(MessagePrimitiveAttachmentsInner, { children: (t2) => {
				const { attachment } = t2;
				const Component = getComponent(components, attachment);
				if (!Component) return null;
				return /* @__PURE__ */ jsx(Component, {});
			} });
			$[0] = components;
			$[1] = t1;
		} else t1 = $[1];
		return t1;
	}
	let t1;
	if ($[2] !== children) {
		t1 = /* @__PURE__ */ jsx(MessagePrimitiveAttachmentsInner, { children });
		$[2] = children;
		$[3] = t1;
	} else t1 = $[3];
	return t1;
};
MessagePrimitiveAttachments.displayName = "MessagePrimitive.Attachments";
function _temp(s) {
	return s.attachment;
}
//#endregion
export { MessagePrimitiveAttachmentByIndex, MessagePrimitiveAttachments };
