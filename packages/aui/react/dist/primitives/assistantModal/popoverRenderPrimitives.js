import { withRenderProp } from "../../utils/Primitive.js";
import { Popover } from "radix-ui";
//#region src/primitives/assistantModal/popoverRenderPrimitives.ts
const PopoverRenderTrigger = withRenderProp(Popover.Trigger);
const PopoverRenderAnchor = withRenderProp(Popover.Anchor);
const PopoverRenderContent = withRenderProp(Popover.Content);
//#endregion
export { PopoverRenderAnchor, PopoverRenderContent, PopoverRenderTrigger };
