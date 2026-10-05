import { __exportAll } from "../_virtual/_rolldown/runtime.js";
import { ComposerPrimitiveSend } from "./composer/ComposerSend.js";
import { ComposerPrimitiveRoot } from "./composer/ComposerRoot.js";
import { ComposerPrimitiveTriggerPopoverRoot, useTriggerPopoverRootContext, useTriggerPopoverRootContextOptional, useTriggerPopoverTriggers, useTriggerPopoverTriggersOptional } from "./composer/trigger/TriggerPopoverRootContext.js";
import { ComposerPrimitiveInput } from "./composer/ComposerInput.js";
import { ComposerPrimitiveCancel } from "./composer/ComposerCancel.js";
import { ComposerPrimitiveAddAttachment } from "./composer/ComposerAddAttachment.js";
import { ComposerPrimitiveAttachmentByIndex, ComposerPrimitiveAttachments } from "./composer/ComposerAttachments.js";
import { ComposerPrimitiveAttachmentDropzone } from "./composer/ComposerAttachmentDropzone.js";
import { ComposerPrimitiveDictate } from "./composer/ComposerDictate.js";
import { ComposerPrimitiveStopDictation } from "./composer/ComposerStopDictation.js";
import { ComposerPrimitiveDictationTranscript } from "./composer/ComposerDictationTranscript.js";
import { ComposerPrimitiveIf } from "./composer/ComposerIf.js";
import { ComposerPrimitiveQuote, ComposerPrimitiveQuoteDismiss, ComposerPrimitiveQuoteText } from "./composer/ComposerQuote.js";
import { ComposerPrimitiveQueue } from "./composer/ComposerQueue.js";
import { useTriggerPopoverScopeContext, useTriggerPopoverScopeContextOptional } from "./composer/trigger/TriggerPopover.js";
import { ComposerPrimitiveTriggerPopoverCategories, ComposerPrimitiveTriggerPopoverCategoryItem } from "./composer/trigger/TriggerPopoverCategories.js";
import { ComposerPrimitiveTriggerPopoverItem, ComposerPrimitiveTriggerPopoverItems } from "./composer/trigger/TriggerPopoverItems.js";
import { ComposerPrimitiveTriggerPopoverBack } from "./composer/trigger/TriggerPopoverBack.js";
import { ComposerPrimitiveTriggerPopover } from "./composer/trigger/index.js";
//#region src/primitives/composer.ts
var composer_exports = /* @__PURE__ */ __exportAll({
	AddAttachment: () => ComposerPrimitiveAddAttachment,
	AttachmentByIndex: () => ComposerPrimitiveAttachmentByIndex,
	AttachmentDropzone: () => ComposerPrimitiveAttachmentDropzone,
	Attachments: () => ComposerPrimitiveAttachments,
	Cancel: () => ComposerPrimitiveCancel,
	Dictate: () => ComposerPrimitiveDictate,
	DictationTranscript: () => ComposerPrimitiveDictationTranscript,
	If: () => ComposerPrimitiveIf,
	Input: () => ComposerPrimitiveInput,
	Queue: () => ComposerPrimitiveQueue,
	Quote: () => ComposerPrimitiveQuote,
	QuoteDismiss: () => ComposerPrimitiveQuoteDismiss,
	QuoteText: () => ComposerPrimitiveQuoteText,
	Root: () => ComposerPrimitiveRoot,
	Send: () => ComposerPrimitiveSend,
	StopDictation: () => ComposerPrimitiveStopDictation,
	Unstable_TriggerPopover: () => ComposerPrimitiveTriggerPopover,
	Unstable_TriggerPopoverBack: () => ComposerPrimitiveTriggerPopoverBack,
	Unstable_TriggerPopoverCategories: () => ComposerPrimitiveTriggerPopoverCategories,
	Unstable_TriggerPopoverCategoryItem: () => ComposerPrimitiveTriggerPopoverCategoryItem,
	Unstable_TriggerPopoverItem: () => ComposerPrimitiveTriggerPopoverItem,
	Unstable_TriggerPopoverItems: () => ComposerPrimitiveTriggerPopoverItems,
	Unstable_TriggerPopoverRoot: () => ComposerPrimitiveTriggerPopoverRoot,
	unstable_useTriggerPopoverRootContext: () => useTriggerPopoverRootContext,
	unstable_useTriggerPopoverRootContextOptional: () => useTriggerPopoverRootContextOptional,
	unstable_useTriggerPopoverScopeContext: () => useTriggerPopoverScopeContext,
	unstable_useTriggerPopoverScopeContextOptional: () => useTriggerPopoverScopeContextOptional,
	unstable_useTriggerPopoverTriggers: () => useTriggerPopoverTriggers,
	unstable_useTriggerPopoverTriggersOptional: () => useTriggerPopoverTriggersOptional
});
//#endregion
export { ComposerPrimitiveAddAttachment as AddAttachment, ComposerPrimitiveAttachmentByIndex as AttachmentByIndex, ComposerPrimitiveAttachmentDropzone as AttachmentDropzone, ComposerPrimitiveAttachments as Attachments, ComposerPrimitiveCancel as Cancel, ComposerPrimitiveDictate as Dictate, ComposerPrimitiveDictationTranscript as DictationTranscript, ComposerPrimitiveIf as If, ComposerPrimitiveInput as Input, ComposerPrimitiveQueue as Queue, ComposerPrimitiveQuote as Quote, ComposerPrimitiveQuoteDismiss as QuoteDismiss, ComposerPrimitiveQuoteText as QuoteText, ComposerPrimitiveRoot as Root, ComposerPrimitiveSend as Send, ComposerPrimitiveStopDictation as StopDictation, ComposerPrimitiveTriggerPopover as Unstable_TriggerPopover, ComposerPrimitiveTriggerPopoverBack as Unstable_TriggerPopoverBack, ComposerPrimitiveTriggerPopoverCategories as Unstable_TriggerPopoverCategories, ComposerPrimitiveTriggerPopoverCategoryItem as Unstable_TriggerPopoverCategoryItem, ComposerPrimitiveTriggerPopoverItem as Unstable_TriggerPopoverItem, ComposerPrimitiveTriggerPopoverItems as Unstable_TriggerPopoverItems, ComposerPrimitiveTriggerPopoverRoot as Unstable_TriggerPopoverRoot, composer_exports, useTriggerPopoverRootContext as unstable_useTriggerPopoverRootContext, useTriggerPopoverRootContextOptional as unstable_useTriggerPopoverRootContextOptional, useTriggerPopoverScopeContext as unstable_useTriggerPopoverScopeContext, useTriggerPopoverScopeContextOptional as unstable_useTriggerPopoverScopeContextOptional, useTriggerPopoverTriggers as unstable_useTriggerPopoverTriggers, useTriggerPopoverTriggersOptional as unstable_useTriggerPopoverTriggersOptional };
