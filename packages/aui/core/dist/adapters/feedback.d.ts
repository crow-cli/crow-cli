import type { ThreadMessage } from "../types/message.js";
type FeedbackAdapterFeedback = {
    message: ThreadMessage;
    type: "positive" | "negative";
    comment?: string;
};
export type FeedbackAdapter = {
    submit: (feedback: FeedbackAdapterFeedback) => void;
};
export {};