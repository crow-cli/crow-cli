import { type ReactNode } from "react";
import type { QuoteInfo } from "../../../types/quote.js";
export declare namespace MessagePrimitiveQuote {
    type Props = {
        /** Render function called when a quote is present. Receives quote info. */
        children: (value: QuoteInfo) => ReactNode;
    };
}
export declare const MessagePrimitiveQuote: import("react").NamedExoticComponent<MessagePrimitiveQuote.Props>;