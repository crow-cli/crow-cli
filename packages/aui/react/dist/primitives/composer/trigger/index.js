import { ComposerPrimitiveTriggerPopoverRoot, useTriggerPopoverRootContext, useTriggerPopoverRootContextOptional, useTriggerPopoverTriggers, useTriggerPopoverTriggersOptional } from "./TriggerPopoverRootContext.js";
import { ComposerPrimitiveTriggerPopover as ComposerPrimitiveTriggerPopover$1, useTriggerPopoverScopeContext, useTriggerPopoverScopeContextOptional } from "./TriggerPopover.js";
import { ComposerPrimitiveTriggerPopoverCategories, ComposerPrimitiveTriggerPopoverCategoryItem } from "./TriggerPopoverCategories.js";
import { ComposerPrimitiveTriggerPopoverItem, ComposerPrimitiveTriggerPopoverItems } from "./TriggerPopoverItems.js";
import { ComposerPrimitiveTriggerPopoverBack } from "./TriggerPopoverBack.js";
import { ComposerPrimitiveTriggerPopoverAction } from "./TriggerPopoverAction.js";
import { ComposerPrimitiveTriggerPopoverDirective } from "./TriggerPopoverDirective.js";
//#region src/primitives/composer/trigger/index.ts
const ComposerPrimitiveTriggerPopover = Object.assign(ComposerPrimitiveTriggerPopover$1, {
	Directive: ComposerPrimitiveTriggerPopoverDirective,
	Action: ComposerPrimitiveTriggerPopoverAction
});
//#endregion
export { ComposerPrimitiveTriggerPopover, ComposerPrimitiveTriggerPopoverBack, ComposerPrimitiveTriggerPopoverCategories, ComposerPrimitiveTriggerPopoverCategoryItem, ComposerPrimitiveTriggerPopoverItem, ComposerPrimitiveTriggerPopoverItems, ComposerPrimitiveTriggerPopoverRoot, useTriggerPopoverRootContext, useTriggerPopoverRootContextOptional, useTriggerPopoverScopeContext, useTriggerPopoverScopeContextOptional, useTriggerPopoverTriggers, useTriggerPopoverTriggersOptional };
