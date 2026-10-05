/**
 * The chat/work split. Chat keeps the dominant share; the work pane is
 * collapsible from either the header or its own bar, and the geometry is
 * remembered — `onLayoutChanged` fires on release, not per drag frame, so
 * this writes localStorage once per resize.
 */
import { useCallback, type ReactNode } from "react";
import type { PanelImperativeHandle } from "react-resizable-panels";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { WorkPane } from "@/components/work/work-pane";
import { DEFAULT_LAYOUT, useWorkStore } from "@/lib/work-store";

export function WorkSplit({ children }: { children: ReactNode }) {
  const layout = useWorkStore((s) => s.layout);
  const setLayout = useWorkStore((s) => s.setLayout);
  const attachPanel = useWorkStore((s) => s.attachPanel);

  // A stable callback ref: an inline one detaches and reattaches on every
  // render, which would rewrite the store each time.
  const panelRef = useCallback(
    (handle: PanelImperativeHandle | null) => attachPanel(handle),
    [attachPanel],
  );

  return (
    <ResizablePanelGroup
      id="work-split"
      orientation="horizontal"
      className="min-h-0 flex-1"
      defaultLayout={layout ?? DEFAULT_LAYOUT}
      onLayoutChanged={(next, meta) => setLayout(meta.requestedLayout ?? next)}
    >
      <ResizablePanel id="chat" minSize="25" className="min-w-0">
        {children}
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel
        id="work"
        collapsible
        collapsedSize={0}
        minSize="18"
        maxSize="75"
        panelRef={panelRef}
        className="min-w-0"
      >
        <WorkPane />
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
