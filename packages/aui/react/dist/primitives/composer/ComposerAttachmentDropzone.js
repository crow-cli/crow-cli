"use client";
import { renderSlot } from "../../utils/Primitive.js";
import { forwardRef, isValidElement, useCallback, useEffect, useState } from "@assistant-ui/tap/react-shim";
import { useAui } from "@assistant-ui/store";
import { jsx } from "react/jsx-runtime";
import { composeEventHandlers } from "radix-ui/internal";
import { Slot } from "radix-ui";
//#region src/primitives/composer/ComposerAttachmentDropzone.tsx
const ComposerPrimitiveAttachmentDropzone = forwardRef(({ disabled, asChild = false, render, children, ...rest }, ref) => {
	const [isDragging, setIsDragging] = useState(false);
	const aui = useAui();
	useEffect(() => {
		if (!disabled) return;
		setIsDragging(false);
	}, [disabled]);
	const handleDragEnterCapture = useCallback((e) => {
		if (!e.dataTransfer.types.includes("Files")) return;
		e.preventDefault();
		if (disabled || !aui.thread.getState().capabilities.attachments) {
			e.dataTransfer.dropEffect = "none";
			return;
		}
		setIsDragging(true);
	}, [disabled, aui]);
	const handleDragOverCapture = useCallback((e_0) => {
		if (!e_0.dataTransfer.types.includes("Files")) return;
		e_0.preventDefault();
		if (disabled || !aui.thread.getState().capabilities.attachments) {
			e_0.dataTransfer.dropEffect = "none";
			return;
		}
		if (!isDragging) setIsDragging(true);
	}, [
		disabled,
		isDragging,
		aui
	]);
	const handleDragLeaveCapture = useCallback((e_1) => {
		if (disabled) return;
		e_1.preventDefault();
		const next = e_1.relatedTarget;
		if (next && e_1.currentTarget.contains(next)) return;
		setIsDragging(false);
	}, [disabled]);
	const handleDrop = useCallback(async (e_2) => {
		setIsDragging(false);
		if (!e_2.dataTransfer.types.includes("Files")) return;
		e_2.preventDefault();
		if (disabled) return;
		const files = Array.from(e_2.dataTransfer.files);
		if (!aui.thread.getState().capabilities.attachments || files.length === 0) return;
		await Promise.all(files.map(async (file) => {
			try {
				await aui.composer.addAttachment(file);
			} catch {}
		}));
	}, [disabled, aui]);
	const mergedProps = {
		...isDragging && !disabled ? { "data-dragging": "true" } : null,
		...rest,
		onDragEnterCapture: composeEventHandlers(rest.onDragEnterCapture, handleDragEnterCapture),
		onDragOverCapture: composeEventHandlers(rest.onDragOverCapture, handleDragOverCapture),
		onDragLeaveCapture: composeEventHandlers(rest.onDragLeaveCapture, handleDragLeaveCapture),
		onDropCapture: composeEventHandlers(rest.onDropCapture, handleDrop),
		ref
	};
	if (render && isValidElement(render)) return renderSlot(render, children, mergedProps);
	const Comp = asChild ? Slot.Root : "div";
	return /* @__PURE__ */ jsx(Comp, {
		...mergedProps,
		children
	});
});
ComposerPrimitiveAttachmentDropzone.displayName = "ComposerPrimitive.AttachmentDropzone";
//#endregion
export { ComposerPrimitiveAttachmentDropzone };
