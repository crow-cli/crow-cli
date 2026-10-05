"use client";

import {
  useCallback,
  useEffect,
  useInsertionEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  useExternalStoreRuntime,
  useExternalStoreSharedOptions,
  useRuntimeAdapters,
} from "@assistant-ui/core/react";
import {
  createMessageQueue,
  type AppendMessage,
  type AssistantRuntime,
  type AttachmentAdapter,
  type DictationAdapter,
  type ExternalStoreAdapter,
  type ExternalStoreSharedOptions,
  type ExternalStoreThreadListAdapter,
  type ExternalThreadQueueAdapter,
  type FeedbackAdapter,
  type MessageQueueController,
  type RealtimeVoiceAdapter,
  type RespondToToolApprovalOptions,
  type SpeechSynthesisAdapter,
  type ThreadMessage,
} from "@assistant-ui/core";
import { invokeUserCallback } from "@assistant-ui/core/internal";
import {
  AcpClient,
  type AcpClientOptions,
  type AcpWebSocketFactory,
  type AcpWebSocketLike,
} from "./AcpClient";
import {
  AcpThreadController,
  type AcpPermissionsMode,
} from "./AcpThreadController";
import { isAcpStateRunning } from "./acpThreadState";
import { projectAcpThreadRepository } from "./acpMessageProjection";
import { useAcpControllerState } from "./useAcpControllerState";
import { acpExtras } from "./acpExtras";
import type { AcpImplementation, AcpMcpServer, AcpSessionInfo } from "./types";

export type UseAcpRuntimeOptions = ExternalStoreSharedOptions & {
  /** Pre-built ACP client instance. Provide this OR `url`. */
  client?: AcpClient;
  /** WebSocket endpoint of the ACP agent, e.g. `ws://127.0.0.1:2770/`. */
  url?: string;
  /**
   * Working directory passed to `session/new`. ACP requires an absolute path;
   * defaults to `"/"`.
   */
  cwd?: string;
  /** MCP servers passed to `session/new`. */
  mcpServers?: readonly AcpMcpServer[];
  /** Client identity for the `initialize` handshake. */
  clientInfo?: AcpImplementation;
  /** Inject a WebSocket implementation (tests / custom transports). */
  webSocketFactory?: AcpWebSocketFactory;
  /**
   * Permission policy. `"ask"` (default) surfaces ACP permission requests as
   * tool-call approvals in the UI; `"auto-allow"` answers them with the
   * agent's first allow-family option.
   */
  permissions?: AcpPermissionsMode;
  /** Connect on mount. Defaults to true. */
  autoConnect?: boolean;
  /**
   * After connecting, open the agent's newest thread for this cwd — or mint
   * a session when it remembers none — so a session exists (and its id is
   * visible) before the first prompt. Defaults to false: hosts that prefer
   * a lazy `session/new` on the first prompt keep it.
   */
  restoreOnConnect?: boolean;
  /**
   * Let a send made while a turn is running wait in `composer.queue` and go
   * out as its own `session/prompt`, in order, as each turn settles. Off by
   * default: without it a mid-run send cancels the turn in flight, since an
   * ACP agent runs one turn per session and has no way to take a second
   * prompt while it works.
   */
  unstable_enableMessageQueue?: boolean;

  /** Called when an error occurs. */
  onError?: (error: Error) => void;
  /** Called when a run is cancelled. */
  onCancel?: () => void;

  /**
   * There is deliberately no `history` adapter: the agent owns an ACP
   * conversation, so a transcript restored from storage would show messages the
   * next `session/new` knows nothing about.
   */
  adapters?: {
    attachments?: AttachmentAdapter;
    speech?: SpeechSynthesisAdapter;
    dictation?: DictationAdapter;
    voice?: RealtimeVoiceAdapter;
    feedback?: FeedbackAdapter;
  };
};

type ManagedAcpClientOptions = Pick<
  AcpClientOptions,
  "url" | "cwd" | "mcpServers" | "clientInfo"
>;

type AcpRegistry = {
  readonly key: string;
  readonly client: AcpClient;
  readonly controller: AcpThreadController;
  activate(): void;
  release(): void;
};

const createRegistry = (
  key: string,
  client: AcpClient,
  ownsClient: boolean,
): AcpRegistry => {
  let disposeTimer: ReturnType<typeof setTimeout> | undefined;

  return {
    key,
    client,
    controller: new AcpThreadController({ client }),
    activate() {
      if (disposeTimer === undefined) return;
      clearTimeout(disposeTimer);
      disposeTimer = undefined;
    },
    release() {
      if (!ownsClient) return;
      disposeTimer ??= setTimeout(() => {
        disposeTimer = undefined;
        void client.cancel().then(
          () => client.dispose(),
          () => client.dispose(),
        );
      }, 0);
    },
  };
};

const toError = (error: unknown): Error =>
  error instanceof Error ? error : new Error(String(error));

/**
 * One session's send queue, plus how many run starts its driver has seen. The
 * count tells a dispatch that never became a run — a detached controller, a
 * prompt the client refused — from one that did, so only the former releases
 * the queue by hand instead of waiting for an idle edge that cannot come.
 */
type SessionQueue = {
  edges: number;
  controller: MessageQueueController | null;
};

const buildManagedClientOptions = (
  options: UseAcpRuntimeOptions,
): ManagedAcpClientOptions => {
  const { url } = options;
  if (!url) throw new Error("useAcpRuntime requires either `client` or `url`");
  return {
    url,
    ...(options.cwd !== undefined && { cwd: options.cwd }),
    mcpServers: options.mcpServers ?? [],
    ...(options.clientInfo && { clientInfo: options.clientInfo }),
  };
};

export function useAcpRuntime(options: UseAcpRuntimeOptions): AssistantRuntime {
  const runtimeAdapters = useRuntimeAdapters();

  const webSocketFactory = options.webSocketFactory;
  const webSocketFactoryRef = useRef(webSocketFactory);
  useEffect(() => {
    webSocketFactoryRef.current = webSocketFactory;
  }, [webSocketFactory]);

  const stableWebSocketFactory = useMemo<AcpWebSocketFactory>(
    () => (url) => {
      const factory = webSocketFactoryRef.current;
      if (factory) return factory(url);
      return new WebSocket(url) as unknown as AcpWebSocketLike;
    },
    [],
  );

  const externalClient = options.client;
  const managedClientOptions = externalClient
    ? undefined
    : buildManagedClientOptions(options);
  const registryKey = externalClient
    ? "external"
    : JSON.stringify(managedClientOptions);

  const createRegistryClient = () =>
    externalClient
      ? externalClient
      : new AcpClient({
          ...managedClientOptions!,
          webSocketFactory: stableWebSocketFactory,
        });

  const ownsClient = !externalClient;

  const [pinned, setPinned] = useState(() =>
    createRegistry(registryKey, createRegistryClient(), ownsClient),
  );

  let registry = pinned;
  const clientChanged = externalClient
    ? registry.client !== externalClient
    : registry.key !== registryKey;
  if (clientChanged) {
    registry = createRegistry(registryKey, createRegistryClient(), ownsClient);
    setPinned(registry);
  }

  const { controller, client } = registry;

  useEffect(() => {
    registry.activate();
    void controller.attach();
    return () => {
      void controller.detach();
      registry.release();
    };
  }, [controller, registry]);

  const permissions = options.permissions;
  const autoConnect = options.autoConnect;
  const restoreOnConnect = options.restoreOnConnect;

  // Hosts write `onError: (error) => ...` inline, so both callbacks are read
  // through refs. Keying an effect on their identity instead re-runs it on
  // every host render, and since the thread-list refresh below renders the
  // host, that is a `session/list` per render rather than one per moment.
  const onErrorRef = useRef(options.onError);
  const onCancelRef = useRef(options.onCancel);
  useEffect(() => {
    onErrorRef.current = options.onError;
    onCancelRef.current = options.onCancel;
  });
  const reportError = useCallback((error: unknown) => {
    invokeUserCallback("acp", "onError", onErrorRef.current, toError(error));
  }, []);
  const reportCancel = useCallback(() => {
    invokeUserCallback("acp", "onCancel", onCancelRef.current);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await controller.updateOptions({
        client,
        permissions,
        autoConnect,
        restoreOnConnect,
        onError: reportError,
        onCancel: reportCancel,
      });
      if (cancelled) return;
      await controller.load();
    })().catch(reportError);
    return () => {
      cancelled = true;
    };
  }, [
    autoConnect,
    client,
    controller,
    permissions,
    reportCancel,
    reportError,
    restoreOnConnect,
  ]);

  const adapters = options.adapters;
  const adapterAdapters = useMemo(
    () => ({
      attachments: adapters?.attachments ?? runtimeAdapters?.attachments,
      speech: adapters?.speech,
      dictation: adapters?.dictation,
      voice: adapters?.voice,
      feedback: adapters?.feedback,
    }),
    [adapters, runtimeAdapters],
  );

  const state = useAcpControllerState(controller);

  const messageRepository = useMemo(
    () => projectAcpThreadRepository(state),
    [state],
  );

  const extras = useMemo(
    () =>
      acpExtras.provide({
        setConfigOption: (configId: string, value: string) =>
          controller.setConfigOption(configId, value),
        connectionState: state.connectionState,
        sessionId: state.sessionId,
        agentInfo: state.agentInfo,
        agentCapabilities: state.agentCapabilities,
        plan: state.plan,
        sessionTitle: state.sessionTitle,
        currentModeId: state.currentModeId,
        availableCommands: state.availableCommands,
        configOptions: state.configOptions,
        usage: state.usage,
      }),
    [controller, state],
  );

  const shared = useExternalStoreSharedOptions(options);
  const isLoading = state.loadState.type === "loading";
  const isRunning = isAcpStateRunning(state);

  // Queued prompts belong to the session they were typed in, so each session
  // gets its own queue and only the open one reaches the store: a background
  // session's items wait for the user to come back instead of draining into
  // whatever conversation is on screen.
  const enableQueue = options.unstable_enableMessageQueue === true;
  const queues = useRef(new Map<string, SessionQueue>());
  const appendTarget = useRef(controller);
  const activeQueueRef = useRef<SessionQueue | null>(null);
  useInsertionEffect(() => {
    appendTarget.current = controller;
  }, [controller]);

  const sessionId = state.sessionId;
  const activeQueue = useMemo<SessionQueue | null>(() => {
    if (!enableQueue) return null;
    const key = sessionId ?? "";
    const existing = queues.current.get(key);
    if (existing) return existing;
    const queue: SessionQueue = { edges: 0, controller: null };
    queue.controller = createMessageQueue({
      run: (message) => {
        const edges = queue.edges;
        // `append` settles when the run it started ends, so an edge count that
        // never moved means no run started and no idle edge is coming to
        // release the queue: release it here, or every later send buffers
        // behind a run that does not exist.
        const releaseIfNoRun = () => {
          if (queue.edges === edges) queue.controller?.notifyIdle();
        };
        void appendTarget.current
          .append(message)
          .then(releaseIfNoRun, releaseIfNoRun);
      },
      // No `cancel` driver: steering then degrades to "process next", which is
      // all an agent that runs one turn at a time can honour anyway.
    });
    queues.current.set(key, queue);
    return queue;
  }, [enableQueue, sessionId]);

  useEffect(() => {
    if (enableQueue) return;
    for (const queue of queues.current.values()) queue.controller?.clear();
    queues.current.clear();
  }, [enableQueue]);

  const queueController = activeQueue?.controller ?? null;
  useInsertionEffect(() => {
    activeQueueRef.current = activeQueue;
  }, [activeQueue]);

  // A thread switch cancels the turn in flight, and that settle would drain
  // the queue of the session being left into whatever the controller points at
  // next. Holding it first keeps the prompts with their session: still there,
  // and still sent, when the user comes back.
  const holdActiveQueue = useCallback(() => {
    activeQueueRef.current?.controller?.hold();
  }, []);

  // The adapter below keeps one identity per session while its items are
  // replaced in place, so the store's composer client never re-reads them on
  // its own: a queue change has to arrive as a new adapter — and therefore a
  // new store — for `composer.queue` to move. Without this tick a queued send
  // only shows up once the next unrelated store update re-renders the client.
  const [queueTick, setQueueTick] = useState(0);
  useEffect(
    () => queueController?.subscribe(() => setQueueTick((tick) => tick + 1)),
    [queueController],
  );

  // The queue buffers while a run is in flight and advances when it settles,
  // so both edges have to be reported — including the ones a direct send
  // produces, which is what tells the queue that a turn it did not start is
  // over. Becoming the open queue is an edge of its own: a session's queue is
  // held while another one is open, so coming back releases it and states the
  // run it missed.
  const wasRunning = useRef(isRunning);
  const openQueue = useRef<SessionQueue | null>(null);
  useEffect(() => {
    if (!activeQueue) return;
    const queue = activeQueue.controller;
    if (openQueue.current !== activeQueue) {
      openQueue.current = activeQueue;
      wasRunning.current = isRunning;
      queue?.release();
      if (isRunning) {
        activeQueue.edges += 1;
        queue?.notifyBusy();
      }
      return;
    }
    const previous = wasRunning.current;
    wasRunning.current = isRunning;
    if (previous === isRunning) return;
    if (isRunning) {
      activeQueue.edges += 1;
      queue?.notifyBusy();
    } else {
      queue?.notifyIdle();
    }
  }, [activeQueue, isRunning]);

  // A cancel drains rather than pauses. `createMessageQueue` offers
  // `__internal_notifyCancelled` to hold pending items after a stop; the crow
  // TUI does the opposite, settling an interrupted turn straight into the next
  // queued prompt, and leaving the hook out is the documented way to drain.
  // Neither choice drops anything: the items stay on screen until they go.
  const queueAdapter = useMemo<ExternalThreadQueueAdapter | undefined>(() => {
    if (!queueController) return undefined;
    // Read only to make the dependency below honest: the tick gives this memo
    // a new identity on every queue change, which is what re-syncs the store.
    void queueTick;
    const { adapter } = queueController;
    return {
      get items() {
        return adapter.items;
      },
      get steerItems() {
        return adapter.steerItems;
      },
      enqueue: (message) => adapter.enqueue(message),
      steer: (message) => adapter.steer(message),
      // Send now, the `ctrl+enter` twin of the TUI's steer: the frame goes out
      // while the turn in flight is still running and gets its own turn when
      // the agent reaches it, instead of waiting in a lane for the settle.
      sendNow: (message) => {
        void controller.steer(message);
      },
      move: (queueItemId, placement) => adapter.move(queueItemId, placement),
      edit: (queueItemId, message) => adapter.edit(queueItemId, message),
      remove: (queueItemId) => adapter.remove(queueItemId),
      __internal_setDispatchTransform: (transform) =>
        adapter.__internal_setDispatchTransform?.(transform),
    };
  }, [controller, queueController, queueTick]);

  const [threads, setThreads] = useState<readonly AcpSessionInfo[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const refreshInFlight = useRef<Promise<void> | undefined>(undefined);
  const refreshThreads = useCallback(() => {
    // A thread switch both lands here and moves `sessionId`, which re-runs the
    // effect below: one ask per moment, not one per signal.
    refreshInFlight.current ??= (async () => {
      setThreadsLoading(true);
      try {
        const page = await client.listSessions(
          options.cwd !== undefined ? { cwd: options.cwd } : undefined,
        );
        setThreads(page.sessions);
      } catch (error) {
        reportError(error);
      } finally {
        setThreadsLoading(false);
        refreshInFlight.current = undefined;
      }
    })();
    return refreshInFlight.current;
  }, [client, options.cwd, reportError]);

  // A thread's title and updatedAt move when a turn ends, and the list gains
  // or loses a row when a session is minted, switched or deleted — so those
  // are the moments to re-ask the agent what it remembers.
  useEffect(() => {
    if (state.connectionState !== "connected") return;
    void refreshThreads();
  }, [isRunning, refreshThreads, state.connectionState, state.sessionId]);

  const threadList = useMemo<ExternalStoreThreadListAdapter>(
    () => ({
      threadId: state.sessionId,
      isLoading: threadsLoading,
      threads: threads.map((session) => ({
        status: "regular" as const,
        id: session.sessionId,
        ...(session.title !== undefined && { title: session.title }),
        custom: {
          cwd: session.cwd,
          ...(session.updatedAt !== undefined && {
            updatedAt: session.updatedAt,
          }),
        },
      })),
      onSwitchToNewThread: async () => {
        holdActiveQueue();
        await controller.switchToNewThread();
        await refreshThreads();
      },
      onSwitchToThread: async (threadId) => {
        holdActiveQueue();
        await controller.switchToThread(threadId);
        await refreshThreads();
      },
      // deleting a thread that is not open changes the agent's list without
      // moving any state the effect below watches, so it re-asks here
      onDelete: async (threadId) => {
        // Deleting the open thread leaves it the way a switch does; deleting
        // another one must not touch the queue that is draining here.
        if (threadId === state.sessionId) holdActiveQueue();
        await controller.deleteThread(threadId);
        // A deleted session cannot be prompted, so its prompts go with it
        // instead of waiting for a thread that no longer exists.
        const deleted = queues.current.get(threadId);
        if (deleted) {
          deleted.controller?.clear();
          queues.current.delete(threadId);
        }
        await refreshThreads();
      },
    }),
    [
      controller,
      holdActiveQueue,
      refreshThreads,
      state.sessionId,
      threads,
      threadsLoading,
    ],
  );

  const store = useMemo(
    () =>
      ({
        ...shared,
        isLoading,
        isRunning,
        unstable_persistsHistory: true,
        messageRepository,
        extras,
        onNew: (message: AppendMessage) =>
          // With no queue there is no steer lane to route a send-now through,
          // so it goes straight to the controller's steer path.
          message.steer === true
            ? controller.steer(message)
            : controller.append(message),
        onCancel: () => controller.cancel(),
        onRespondToToolApproval: (approval: RespondToToolApprovalOptions) =>
          controller.respondToApproval(approval),
        setMessages: (messages: readonly ThreadMessage[]) =>
          controller.applyExternalMessages(messages),
        onImport: (messages: readonly ThreadMessage[]) =>
          controller.applyExternalMessages(messages),
        ...(queueAdapter !== undefined && { queue: queueAdapter }),
        adapters: { ...adapterAdapters, threadList },
      }) satisfies ExternalStoreAdapter<ThreadMessage>,
    [
      adapterAdapters,
      controller,
      extras,
      isLoading,
      isRunning,
      messageRepository,
      queueAdapter,
      shared,
      threadList,
    ],
  );

  return useExternalStoreRuntime(store);
}
