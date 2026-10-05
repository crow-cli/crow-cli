import { withRenderProp } from "../utils/Primitive.js";
import { DropdownMenu } from "radix-ui";
//#region src/primitives/dropdownMenuRenderPrimitives.ts
const DropdownMenuRenderTrigger = withRenderProp(DropdownMenu.Trigger);
const DropdownMenuRenderContent = withRenderProp(DropdownMenu.Content);
const DropdownMenuRenderItem = withRenderProp(DropdownMenu.Item);
const DropdownMenuRenderSeparator = withRenderProp(DropdownMenu.Separator);
//#endregion
export { DropdownMenuRenderContent, DropdownMenuRenderItem, DropdownMenuRenderSeparator, DropdownMenuRenderTrigger };
