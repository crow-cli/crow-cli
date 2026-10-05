"use client";
import { createActionButton } from "../../utils/createActionButton.js";
import { useActionBarReload } from "@assistant-ui/core/react";
//#region src/primitives/actionBar/ActionBarReload.ts
/**
* Hook that provides reload functionality for action bar buttons.
*
* This hook returns a callback function that reloads/regenerates the current assistant message,
* or null if reloading is not available (e.g., thread is running, disabled, or message is not from assistant).
*
* @returns A reload callback function, or null if reloading is disabled
*
* @example
* ```tsx
* function CustomReloadButton() {
*   const reload = useActionBarReload();
*
*   return (
*     <button onClick={reload} disabled={!reload}>
*       {reload ? "Reload Message" : "Cannot Reload"}
*     </button>
*   );
* }
* ```
*/
const useActionBarReload$1 = () => {
	const { disabled, reload } = useActionBarReload();
	if (disabled) return null;
	return reload;
};
/**
* A button component that reloads/regenerates the current assistant message.
*
* This component automatically handles reloading the current assistant message
* and is disabled when reloading is not available (e.g., thread is running,
* disabled, or message is not from assistant).
*
* @example
* ```tsx
* <ActionBarPrimitive.Reload>
*   Reload Message
* </ActionBarPrimitive.Reload>
* ```
*/
const ActionBarPrimitiveReload = createActionButton("ActionBarPrimitive.Reload", useActionBarReload$1);
//#endregion
export { ActionBarPrimitiveReload };
