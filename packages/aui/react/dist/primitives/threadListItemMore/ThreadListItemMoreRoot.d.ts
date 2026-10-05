import { type Dispatch, type FC, type SetStateAction } from "react";
import { DropdownMenu as DropdownMenuPrimitive } from "radix-ui";
export declare const useThreadListItemMoreSetOpen: () => Dispatch<SetStateAction<boolean>>;
export declare const useThreadListItemMoreSharedFocusGroup: () => boolean;
export declare namespace ThreadListItemMorePrimitiveRoot {
    type Props = DropdownMenuPrimitive.DropdownMenuProps & {
        /**
         * Join the menu to the thread list's focus group: Right opens it, Left/Escape
         * close it and return focus to the trigger (mirrored in RTL). Forces the menu
         * non-modal, since a focus trap can't let focus cross the trigger/menu
         * boundary. Defaults to a standalone modal dropdown.
         */
        sharedFocusGroup?: boolean | undefined;
    };
}
/**
 * Root container for the overflow menu, built on Radix DropdownMenu.
 *
 * Defaults to a standard, self-contained modal dropdown. Pass
 * {@link ThreadListItemMorePrimitiveRoot.Props.sharedFocusGroup} to fold it into
 * the thread list's keyboard navigation instead.
 */
export declare const ThreadListItemMorePrimitiveRoot: FC<ThreadListItemMorePrimitiveRoot.Props>;