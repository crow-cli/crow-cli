import type { ComposerSendOptions } from "../../store/scopes/composer.js";
export declare const useComposerSend: () => {
    send: (opts?: ComposerSendOptions) => void;
    disabled: boolean;
};