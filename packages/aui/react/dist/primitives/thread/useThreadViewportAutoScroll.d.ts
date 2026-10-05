import { type RefCallback } from "react";
export declare namespace useThreadViewportAutoScroll {
    type Options = {
        /**
         * Whether to automatically scroll to the bottom when new messages are added.
         * When enabled, the viewport will automatically scroll to show the latest content.
         *
         * Default false if `turnAnchor` is "top", otherwise defaults to true.
         */
        autoScroll?: boolean | undefined;
        /**
         * Whether to scroll to bottom when a new run starts.
         *
         * Defaults to true.
         */
        scrollToBottomOnRunStart?: boolean | undefined;
        /**
         * Whether to scroll to bottom when messages first appear in the thread.
         *
         * Defaults to true.
         */
        scrollToBottomOnInitialize?: boolean | undefined;
        /**
         * Whether to scroll to bottom when switching to a different thread.
         *
         * Defaults to true.
         */
        scrollToBottomOnThreadSwitch?: boolean | undefined;
    };
}
export declare const useThreadViewportAutoScroll: <TElement extends HTMLElement>({ autoScroll, scrollToBottomOnRunStart, scrollToBottomOnInitialize, scrollToBottomOnThreadSwitch, }: useThreadViewportAutoScroll.Options) => RefCallback<TElement>;