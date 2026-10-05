import { type ReactNode } from "react";
import { AssistantRuntimeProvider } from "../legacy-runtime/AssistantRuntimeProvider.js";
export type CloudRendererHostProps = {
    /** The app's thread UI, usually its own `<Thread />`. */
    children: ReactNode;
    /** Dashboard origins allowed to send a conversation. Defaults to Assistant Cloud's dashboard. */
    allowedOrigins?: readonly string[] | undefined;
    /** The same client or config the app passes to AssistantRuntimeProvider, so tool UIs, data UIs and generative UI render as they do in the app. */
    aui?: AssistantRuntimeProvider.Props["aui"];
    config?: AssistantRuntimeProvider.Props["config"];
};
export declare function CloudRendererHost({ children, allowedOrigins, aui, config, }: CloudRendererHostProps): ReactNode;