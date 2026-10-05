export type ChangeNode = true | {
    [key: string]: ChangeNode;
};
export declare function createChangeNode(): {
    [key: string]: ChangeNode;
};
export declare function assertSafePathSegment(segment: string): void;
export declare function markChanged(node: ChangeNode, path: readonly string[]): ChangeNode;
export declare function mergeChanged(target: ChangeNode, source: ChangeNode): ChangeNode;
export declare function lookupChange(node: ChangeNode, path: readonly string[]): ChangeNode | false;
export declare function lookupValue(state: unknown, path: readonly string[]): unknown;
export declare function diffKeys(newNode: unknown, oldNode: unknown): string[];