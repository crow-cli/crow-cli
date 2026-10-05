import { type ComponentType, type FC, type ReactNode } from "react";
import type { ThreadListItemState } from "../../../store/scopes/thread-list-item.js";
type ThreadListItemsComponentConfig = {
    ThreadListItem: ComponentType;
};
export declare namespace ThreadListPrimitiveItems {
    type Props = {
        archived?: boolean | undefined;
    } & ({
        /** @deprecated Use the children render function instead. */
        components: ThreadListItemsComponentConfig;
        children?: never;
    } | {
        /** Render function called for each thread list item. Receives the item. */
        children: (value: {
            threadListItem: ThreadListItemState;
        }) => ReactNode;
        components?: never;
    });
}
export declare namespace ThreadListPrimitiveItemByIndex {
    type Props = {
        index: number;
        archived?: boolean | undefined;
        components: ThreadListItemsComponentConfig;
    };
}
/**
 * Renders a single thread list item at the specified index.
 */
export declare const ThreadListPrimitiveItemByIndex: FC<ThreadListPrimitiveItemByIndex.Props>;
export declare const ThreadListPrimitiveItems: FC<ThreadListPrimitiveItems.Props>;
export {};