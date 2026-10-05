import { memo, useState } from "react";
import {
  ChevronsDownUpIcon,
  ChevronsUpDownIcon,
  FolderOpenIcon,
  PaletteIcon,
  PanelRightIcon,
  PanelRightOpenIcon,
  PlugIcon,
} from "lucide-react";
import { useAcpAgentInfo, useAcpConnectionState } from "@assistant-ui/acp";
import { Button } from "@/components/ui/button";
import { ContextMeter } from "@/components/context-meter";
import { DirectoryPicker } from "@/components/directory-picker";
import { ModelSelector } from "@/components/model-selector";
import { SessionBadge } from "@/components/session-badge";
import { McpSettingsDialog } from "@/components/mcp-settings-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { collapseAll, useCollapseAll } from "@/lib/collapse-all";
import { useWorkStore } from "@/lib/work-store";
import { cn } from "@/lib/utils";
import { THEMES, type Theme } from "@/lib/theme";

const DOT: Record<string, string> = {
  connected: "bg-success",
  connecting: "bg-warning animate-pulse",
  disconnected: "bg-destructive",
};

export type AppHeaderProps = {
  cwd: string;
  acpError: string | null;
  onSaveCwd: (next: string) => void;
  mcpText: string;
  onSaveMcp: (next: string) => void;
  theme: Theme;
  onTheme: (next: Theme) => void;
};

// Memoized for the same reason the sidebar is: every prop is a stable setting
// or setter, and the live values — connection dot, agent name, context meter —
// come from hooks that subscribe on their own. A streamed chunk re-renders the
// host that owns the runtime; none of it lands here.
export const AppHeader = memo(function AppHeader({
  acpError,
  cwd,
  onSaveCwd,
  mcpText,
  onSaveMcp,
  theme,
  onTheme,
}: AppHeaderProps) {
  const connectionState = useAcpConnectionState();
  const agentInfo = useAcpAgentInfo();
  const collapsed = useCollapseAll();
  // Read straight from the work store: the header is memoized against the
  // runtime subtree, and this is not the runtime's business.
  const workHidden = useWorkStore((s) => s.collapsed);
  const toggleWork = useWorkStore((s) => s.togglePane);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [mcpOpen, setMcpOpen] = useState(false);

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b px-4">
      <span
        data-testid="connection-dot"
        data-state={connectionState}
        className={cn("size-2 rounded-full", DOT[connectionState])}
        title={connectionState}
      />
      <div className="flex min-w-0 flex-1 items-center">
        <span className="shrink-0 text-sm font-medium">crow-chat</span>
        {agentInfo && (
          <span className="text-muted-foreground ml-2 text-xs">
            {agentInfo.title ?? agentInfo.name}
            {agentInfo.version ? ` v${agentInfo.version}` : ""}
          </span>
        )}
        {connectionState === "disconnected" && acpError && (
          <span
            data-testid="connection-error"
            className="ms-2 truncate text-xs text-destructive"
            title={acpError}
          >
            {acpError}
          </span>
        )}
        <SessionBadge className="ms-2" />
      </div>
      <ModelSelector />
      <ContextMeter />
      <Button
        variant="ghost"
        size="icon"
        data-testid="collapse-all"
        data-state={collapsed ? "collapsed" : "expanded"}
        aria-label={
          collapsed
            ? "Expand all tool calls and thoughts"
            : "Collapse all tool calls and thoughts"
        }
        title="Collapse all · ctrl+shift+o"
        onClick={() => collapseAll.toggle()}
      >
        {collapsed ? (
          <ChevronsUpDownIcon className="size-4" />
        ) : (
          <ChevronsDownUpIcon className="size-4" />
        )}
      </Button>
      <Button
        variant="ghost"
        size="icon"
        data-testid="work-toggle"
        data-state={workHidden ? "hidden" : "shown"}
        aria-label={workHidden ? "Show the work pane" : "Hide the work pane"}
        title="Toggle the work pane"
        onClick={toggleWork}
      >
        {workHidden ? (
          <PanelRightOpenIcon className="size-4" />
        ) : (
          <PanelRightIcon className="size-4" />
        )}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="Theme">
            <PaletteIcon className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuRadioGroup value={theme} onValueChange={(v) => onTheme(v as Theme)}>
            {THEMES.map((t) => (
              <DropdownMenuRadioItem key={t} value={t} className="capitalize">
                {t}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <Button
        variant="ghost"
        size="icon"
        aria-label="MCP servers"
        onClick={() => setMcpOpen(true)}
      >
        <PlugIcon className="size-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Session settings"
        title="Working directory"
        onClick={() => setPickerOpen(true)}
      >
        <FolderOpenIcon className="size-4" />
      </Button>
      <DirectoryPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        initial={cwd}
        onSelect={onSaveCwd}
      />
      <McpSettingsDialog
        open={mcpOpen}
        onOpenChange={setMcpOpen}
        value={mcpText}
        onSave={onSaveMcp}
      />
    </header>
  );
});
