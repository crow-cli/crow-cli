import { type ExportedMessageRepository as ExportedMessageRepositoryType, type ThreadMessage, type ThreadMessageLike } from "@assistant-ui/core";
import type { AcpThreadMessage, AcpThreadState } from "./acpThreadState.js";
export declare const toThreadMessageLike: (message: AcpThreadMessage) => ThreadMessageLike;
export declare const toThreadMessage: (message: AcpThreadMessage) => ThreadMessage;
export declare function projectAcpThreadRepository(state: AcpThreadState): ExportedMessageRepositoryType;