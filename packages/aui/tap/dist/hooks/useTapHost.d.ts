export declare namespace useTapHost {
    interface Result<R> {
        /**
         * The current render output of the host resource.
         */
        value: R;
        /**
         * Commits the host's pending render result. Pass to a deps-less
         * useEffect in a descendant component to land the commit ahead of
         * the descendants' own effects; the first instance to run wins. A
         * plain callback (not a hook) so React Compiler can compile the
         * consumer; its identity changes on every host render.
         */
        effects: () => void;
    }
}
export declare const useTapHost: <R>(callback: () => R) => useTapHost.Result<R>;