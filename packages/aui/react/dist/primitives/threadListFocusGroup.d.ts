import { Collection } from "radix-ui/internal";
import { type RefObject } from "react";
declare const useThreadListCollection: (scope: any) => () => {
    ref: RefObject<HTMLButtonElement | null>;
}[];
export declare const ThreadListCollection: {
    readonly Provider: React.FC<{
        children?: React.ReactNode;
        scope: any;
    }>;
    readonly Slot: React.ForwardRefExoticComponent<Collection.CollectionProps & React.RefAttributes<HTMLElement>>;
    readonly ItemSlot: import("react").ForwardRefExoticComponent<{
        children: React.ReactNode;
        scope: any;
    } & import("react").RefAttributes<HTMLButtonElement>>;
};
export { useThreadListCollection };
type ThreadListItemFocus = {
    triggerRef: RefObject<HTMLButtonElement | null>;
    moreRef: RefObject<HTMLButtonElement | null>;
};
export declare const ThreadListItemFocusProvider: import("react").Provider<ThreadListItemFocus | null>;
export declare const useThreadListItemFocus: () => ThreadListItemFocus | null;