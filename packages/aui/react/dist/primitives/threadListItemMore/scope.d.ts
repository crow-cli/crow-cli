import { DropdownMenu as DropdownMenuPrimitive } from "radix-ui";
import type { Context } from "radix-ui/internal";
export declare const useDropdownMenuScope: ReturnType<typeof DropdownMenuPrimitive.createDropdownMenuScope>;
export type ScopedProps<P> = P & {
    __scopeThreadListItemMore?: Context.Scope;
};