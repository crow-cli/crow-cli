import { type ComponentType } from "react";
export declare const makeAssistantVisible: <T extends ComponentType<any>>(Component: T, config?: {
    clickable?: boolean | undefined;
    editable?: boolean | undefined;
}) => T;
export default makeAssistantVisible;