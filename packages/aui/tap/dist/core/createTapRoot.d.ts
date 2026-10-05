import { useTapRoot } from "../hooks/useTapRoot.js";
export declare const createTapRoot: <R>(render: () => R, options?: {
    mountOnSubscribe?: boolean;
}) => useTapRoot.Root<R> & {
    unmount: () => void;
};