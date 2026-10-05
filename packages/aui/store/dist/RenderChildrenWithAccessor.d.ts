import { type ReactNode } from "react";
import type { AssistantClient } from "./types/client.js";
export declare const useGetItemAccessor: <T>(getItemState: (aui: AssistantClient) => T) => () => T;
/**
 * Component that sets up a lazy item accessor and memoizes propless children.
 *
 * For the common pattern where children returns a component without props
 * (e.g. `<Foo />`), the output is memoized and not re-created on parent re-renders.
 *
 * @example
 * ```tsx
 * <RenderChildrenWithAccessor
 *   getItemState={(aui) => aui.fooList().foo({ index }).getState()}
 * >
 *   {() => <Foo />}
 * </RenderChildrenWithAccessor>
 * ```
 */
export declare function RenderChildrenWithAccessor<T>({ getItemState, children, }: {
    getItemState: (aui: AssistantClient) => T;
    children: (getItem: () => T) => ReactNode;
}): ReactNode;