import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { parseMcpConfig } from "@/lib/mcp-config";

export function McpSettingsDialog({
  open,
  onOpenChange,
  value,
  onSave,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  value: string;
  onSave: (next: string) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>MCP servers</DialogTitle>
          <DialogDescription>
            JSON or YAML: a name-to-server map (the crow-cli config.yaml shape,
            with or without the wrapping mcpServers key) or a list of servers
            carrying their own name. stdio servers need a command; http and
            sse need a url. The ACP agent owns no tools of its own — this list
            is the whole tool supply handed to it at session/new, so saving
            starts a new session.
          </DialogDescription>
        </DialogHeader>
        <McpEditor key={value} initial={value} onSave={onSave} />
      </DialogContent>
    </Dialog>
  );
}

function McpEditor({
  initial,
  onSave,
}: {
  initial: string;
  onSave: (next: string) => void;
}) {
  const [text, setText] = useState(initial);
  const parsed = parseMcpConfig(text);
  const names = parsed.servers.map((s) => s.name).join(", ");

  return (
    <>
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={14}
        spellCheck={false}
        className="font-mono text-xs"
        aria-label="MCP server configuration"
      />
      <p
        className={
          parsed.error ? "text-destructive text-xs" : "text-muted-foreground text-xs"
        }
      >
        {parsed.error ?? `${parsed.servers.length} server(s): ${names || "none"}`}
      </p>
      <DialogFooter>
        <Button
          disabled={parsed.error !== undefined}
          onClick={() => onSave(text)}
        >
          Save and reconnect
        </Button>
      </DialogFooter>
    </>
  );
}
