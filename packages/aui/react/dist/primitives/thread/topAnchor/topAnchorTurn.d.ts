type TopAnchorTurnMessage = {
    readonly id: string;
    readonly role: string;
};
export type TopAnchorTurn = {
    readonly anchorId: string;
    readonly targetId: string;
};
/**
 * A stored turn stays valid only while it is still the trailing turn: the
 * anchor immediately precedes the target, and anything after the target is a
 * pending user message awaiting the next run. An assistant message after the
 * target means the turn was superseded (e.g. an external store synced in a
 * turn completed elsewhere), so the reserve must be torn down, not preserved.
 */
export declare const isTopAnchorTurnValid: (turn: TopAnchorTurn | null, messages: readonly TopAnchorTurnMessage[]) => boolean;
export declare const getActiveTopAnchorTurn: ({ isRunning, messages, }: {
    readonly isRunning: boolean;
    readonly messages: readonly TopAnchorTurnMessage[];
}) => {
    anchorId: string;
    targetId: string;
} | null;
export declare const getActiveTopAnchorAnchorId: (options: Parameters<typeof getActiveTopAnchorTurn>[0]) => string | undefined;
export declare const getActiveTopAnchorTargetId: (options: Parameters<typeof getActiveTopAnchorTurn>[0]) => string | undefined;
export {};