import { type FC } from "react";
import type { ToolCallMessagePartProps } from "../types/MessagePartComponentTypes.js";
export declare const useInlineRender: <TArgs, TResult>(toolUI: FC<ToolCallMessagePartProps<TArgs, TResult>>) => FC<ToolCallMessagePartProps<TArgs, TResult>>;