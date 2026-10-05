import { type FC, type PropsWithChildren } from "react";
import type { ThreadMessage } from "../../types/message.js";
export declare namespace ReadonlyThreadProvider {
    type Props = PropsWithChildren<{
        messages: readonly ThreadMessage[];
    }>;
}
export declare const ReadonlyThreadProvider: FC<ReadonlyThreadProvider.Props>;