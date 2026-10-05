import type { ThreadsClientSchema } from "./scopes/threads.js";
import type { ThreadListItemClientSchema } from "./scopes/thread-list-item.js";
import type { ThreadClientSchema } from "./scopes/thread.js";
import type { MessageClientSchema } from "./scopes/message.js";
import type { PartClientSchema } from "./scopes/part.js";
import type { ComposerClientSchema } from "./scopes/composer.js";
import type { AttachmentClientSchema } from "./scopes/attachment.js";
import type { ModelContextClientSchema } from "./scopes/model-context.js";
import type { SuggestionsClientSchema } from "./scopes/suggestions.js";
import type { SuggestionClientSchema } from "./scopes/suggestion.js";
import type { ChainOfThoughtClientSchema } from "./scopes/chain-of-thought.js";
import type { QueueItemClientSchema } from "./scopes/queue-item.js";
import type { TaskClientSchema } from "./scopes/task.js";
declare module "@assistant-ui/store" {
    interface ScopeRegistry {
        threads: ThreadsClientSchema;
        threadListItem: ThreadListItemClientSchema;
        thread: ThreadClientSchema;
        message: MessageClientSchema;
        part: PartClientSchema;
        composer: ComposerClientSchema;
        attachment: AttachmentClientSchema;
        modelContext: ModelContextClientSchema;
        suggestions: SuggestionsClientSchema;
        suggestion: SuggestionClientSchema;
        chainOfThought: ChainOfThoughtClientSchema;
        queueItem: QueueItemClientSchema;
        task: TaskClientSchema;
    }
}