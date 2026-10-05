import { useState } from "react";
import { CpuIcon, Loader2Icon } from "lucide-react";
import {
  useAcpConfigOptions,
  useAcpSetConfigOption,
  type AcpSessionConfigSelect,
} from "@assistant-ui/acp";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

/**
 * The header's model picker — the write half of `useAcpConfigOptions`.
 *
 * crow-cli advertises exactly one config option: a `select` named "Model"
 * whose values are `provider:model_id`. `session/set_config_option` stores the
 * choice AND moves the session's model identifier, so the next turn really
 * runs on it; the agent answers with the whole option list and no
 * `config_option_update` follows, which is why the marked value is read back
 * from `useAcpConfigOptions` rather than set optimistically here.
 *
 * An agent that advertises no select option gets NO picker, not a disabled
 * one: a greyed-out control still claims the agent could honour a choice.
 */
export function ModelSelector({ className }: { className?: string }) {
  const configOptions = useAcpConfigOptions();
  const setConfigOption = useAcpSetConfigOption();
  const [pending, setPending] = useState(false);
  const option = configOptions?.find(
    (o): o is AcpSessionConfigSelect => o.type === "select",
  );
  if (!option) return null;

  const choices = option.options ?? [];
  const label =
    choices.find((c) => c.value === option.currentValue)?.name ??
    option.currentValue;

  const choose = (value: string) => {
    if (pending || value === option.currentValue) return;
    setPending(true);
    // The action never rejects on an agent-side refusal — that goes to the
    // runtime's `onError` — so `finally` is the whole pending story.
    void setConfigOption(option.id, value).finally(() => setPending(false));
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          data-testid="model-selector"
          data-value={option.currentValue}
          data-pending={pending ? "true" : undefined}
          disabled={pending}
          aria-label={`${option.name}: ${label}`}
          title={`${option.name}: ${label}`}
          className={cn(
            "text-muted-foreground hover:text-foreground max-w-52 gap-1.5 px-2 text-xs font-normal",
            className,
          )}
        >
          {pending ? (
            <Loader2Icon
              aria-hidden
              className="size-3.5 shrink-0 animate-spin"
            />
          ) : (
            <CpuIcon aria-hidden className="size-3.5 shrink-0" />
          )}
          <span className="truncate">{label}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-w-80">
        <DropdownMenuRadioGroup
          value={option.currentValue}
          onValueChange={choose}
        >
          {choices.map((choice) => (
            <DropdownMenuRadioItem
              key={choice.value}
              value={choice.value}
              data-testid="model-option"
              data-value={choice.value}
              disabled={pending}
              className="flex-col items-start gap-0.5 py-1.5"
            >
              <span className="text-xs">{choice.name}</span>
              {choice.description && (
                <span className="text-muted-foreground font-mono text-[11px]">
                  {choice.description}
                </span>
              )}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
