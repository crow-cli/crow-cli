export declare namespace useTapRoot {
    type Unsubscribe = () => void;
    interface Root<R> {
        /**
         * Get the current value of the root.
         */
        getValue(): R;
        /**
         * Subscribe to the root.
         */
        subscribe(listener: () => void): Unsubscribe;
    }
}
export declare const useTapRoot: <R>(render: () => R) => useTapRoot.Root<R>;