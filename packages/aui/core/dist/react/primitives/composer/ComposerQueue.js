import { QueueItemByIndexProvider } from "../../providers/QueueItemByIndexProvider.js";
import { memo, useMemo } from "@assistant-ui/tap/react-shim";
import { RenderChildrenWithAccessor, useAuiState } from "@assistant-ui/store";
import { useShallowSelector } from "@assistant-ui/store/internal";
import { jsx } from "react/jsx-runtime";
//#region src/react/primitives/composer/ComposerQueue.tsx
const ComposerPrimitiveQueueInner = ({ children }) => {
	const queueItemIds = useAuiState(useShallowSelector((s) => s.composer.queue.map((item) => item.id)));
	return useMemo(() => queueItemIds.map((queueItemId, index) => /* @__PURE__ */ jsx(QueueItemByIndexProvider, {
		index,
		children: /* @__PURE__ */ jsx(RenderChildrenWithAccessor, {
			getItemState: (aui) => aui.composer.queueItem({ index }).getState(),
			children: (getItem) => children({ get queueItem() {
				return getItem();
			} })
		})
	}, queueItemId)), [queueItemIds, children]);
};
/**
* Renders all queue items in the composer.
*
* @example
* ```tsx
* <ComposerPrimitive.Queue>
*   {({ queueItem }) => (
*     <div>
*       <QueueItemPrimitive.Text />
*       <QueueItemPrimitive.Steer>Run Now</QueueItemPrimitive.Steer>
*     </div>
*   )}
* </ComposerPrimitive.Queue>
* ```
*/
const ComposerPrimitiveQueue = memo(ComposerPrimitiveQueueInner);
ComposerPrimitiveQueue.displayName = "ComposerPrimitive.Queue";
//#endregion
export { ComposerPrimitiveQueue };
