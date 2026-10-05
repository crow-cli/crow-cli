"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { useActionBarEdit } from "@assistant-ui/core/react";
//#region src/primitives/actionBar/ActionBarEdit.ts
/**
* Hook that provides edit functionality for action bar buttons.
*
* This hook returns a callback function that starts editing the current message,
* or null if editing is not available (e.g., already in editing mode).
*
* @returns An edit callback function, or null if editing is disabled
*
* @example
* ```tsx
* function CustomEditButton() {
*   const edit = useActionBarEdit();
*
*   return (
*     <button onClick={edit} disabled={!edit}>
*       {edit ? "Edit Message" : "Cannot Edit"}
*     </button>
*   );
* }
* ```
*/
const useActionBarEdit$1 = () => {
	const { disabled, edit } = useActionBarEdit();
	if (disabled) return null;
	return edit;
};
/**
* A button component that starts editing the current message.
*
* This component automatically handles starting the edit mode for the current message
* and is disabled when editing is not available (e.g., already in editing mode).
*
* @example
* ```tsx
* <ActionBarPrimitive.Edit>
*   Edit Message
* </ActionBarPrimitive.Edit>
* ```
*/
const ActionBarPrimitiveEdit = createActionButton("ActionBarPrimitive.Edit", useActionBarEdit$1);
//#endregion
export { ActionBarPrimitiveEdit };
