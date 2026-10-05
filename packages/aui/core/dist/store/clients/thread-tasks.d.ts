import type { ClientOutput } from "@assistant-ui/store";
import type { ThreadMessage } from "../../types/message.js";
import type { TaskState } from "../scopes/task.js";
/** Lookup key for a task client: its document-order index path, unique by construction where ids from nested payloads are not. */
export declare const getTaskKey: (task: TaskState) => string;
export declare const createTaskDeriver: () => (messages: readonly ThreadMessage[]) => readonly TaskState[];
export declare const TaskClient: import("@assistant-ui/tap").Resource<ClientOutput<"task">, [{
    task: TaskState;
}]>;