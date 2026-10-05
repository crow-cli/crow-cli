import type { ClientOutput } from "@assistant-ui/store";
import type { ChainOfThoughtPart } from "../scopes/chain-of-thought.js";
import type { PartMethods } from "../scopes/part.js";
export declare const ChainOfThoughtClient: import("@assistant-ui/tap").Resource<ClientOutput<"chainOfThought">, [{
    parts: readonly ChainOfThoughtPart[];
    getMessagePart: (selector: {
        index: number;
    }) => PartMethods;
}]>;