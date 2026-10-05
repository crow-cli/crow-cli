"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { useActionBarSpeak } from "@assistant-ui/core/react";
//#region src/primitives/actionBar/ActionBarSpeak.ts
const useActionBarSpeak$1 = () => {
	const { disabled, speak } = useActionBarSpeak();
	if (disabled) return null;
	return speak;
};
const ActionBarPrimitiveSpeak = createActionButton("ActionBarPrimitive.Speak", useActionBarSpeak$1);
//#endregion
export { ActionBarPrimitiveSpeak };
