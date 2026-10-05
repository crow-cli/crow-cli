/**
 * The fs explorer: svar's react-filemanager adapted to crow-web.
 *
 * The widget is the tree, the table, the context menus and the prompts; this
 * file is only the seam between its event bus and the /fs socket. Ids are
 * absolute-looking paths ("/src/App.tsx") because the widget derives name,
 * extension and parent from the id; crow-web wants them root-relative, so
 * every crossing chops or adds the leading slash.
 *
 * The tree is lazy the way the server is: folders carry `lazy: true` and the
 * widget asks for a directory exactly when it expands or navigates into one.
 * Mutations are intercepted, performed as a single /fs op, and then the
 * server's own `fs` event refreshes the parent — so what you see is never an
 * optimistic guess.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Filemanager,
  getMenuOptions,
  Willow,
  WillowDark,
  type IApi,
  type IEntity,
  type IFileMenuOption,
  type TContextMenuType,
} from "@svar-ui/react-filemanager";
import "@svar-ui/react-filemanager/all.css";
import "@/assets/svar-icons/wx-icons.css";
import { fsClient, type Entry, type Tree } from "@/lib/fs-client";
import { useWorkStore } from "@/lib/work-store";
import { useColorScheme } from "@/lib/theme";
import "./explorer.css";

const ROOT = "/";

/** crow-web path → widget id and back. */
const toId = (path: string) => `/${path}`;
const toPath = (id: string) => (id === ROOT ? "" : id.slice(1));
const parentOf = (id: string) => id.slice(0, id.lastIndexOf("/")) || ROOT;
const nameOf = (id: string) => id.slice(id.lastIndexOf("/") + 1);
/** crow-web paths have no leading slash, so the root parent joins to nothing. */
const join = (dir: string, name: string) => (dir === "" ? name : `${dir}/${name}`);

function toEntity(entry: Entry): IEntity {
  return {
    id: toId(entry.path),
    type: entry.type === "dir" ? "folder" : "file",
    size: entry.size ?? undefined,
    date: entry.mtime ? new Date(entry.mtime) : undefined,
    lazy: entry.type === "dir" || undefined,
  };
}

const ADD_ICONS: Record<string, string> = {
  "add-file": "wxi-file",
  "add-folder": "wxi-folder",
};

/** The verbs crow-web has an op for; everything else stays out of the menu. */
const MENU = new Set([
  "add-file",
  "add-folder",
  "rename",
  "delete",
  "copy",
  "move",
  "paste",
]);

export function Explorer() {
  const scheme = useColorScheme();
  const root = useWorkStore((s) => s.root);
  const [data, setData] = useState<IEntity[] | null>(null);
  const apiRef = useRef<IApi | null>(null);

  const refresh = useCallback(async (dirId: string) => {
    const api = apiRef.current;
    if (!api) return;
    await fsClient.ready();
    const open = !!api.getState().data.byId(dirId)?.open;
    const tree = await fsClient.call<Tree>("tree", { path: toPath(dirId) });
    await api.exec("provide-data", { id: dirId, data: tree.entries.map(toEntity) });
    // provide-data fills the folder entity in place, but Folder.jsx memoizes
    // "hasFolders" on that object's identity, so the expand arrow would never
    // appear for a lazily loaded folder. open-tree-folder runs update(), which
    // replaces the object — and putting the open flag back keeps the branch
    // from collapsing under a refresh.
    api.exec("open-tree-folder", { id: dirId, mode: open });
  }, []);

  // The root listing, and a live ear on the server: whatever moves the tree
  // anywhere tells us which parent to re-read.
  useEffect(() => {
    let live = true;
    const fail = (error: unknown) => useWorkStore.getState().fail(error);
    // The socket is not necessarily up yet — the work pane boots it from an
    // effect that runs after this one — and it can come back after a drop, so
    // the root is (re)read on every transition to open. onState replays the
    // current state, which is what makes the first read happen.
    const offState = fsClient.onState((state) => {
      if (state !== "open") return;
      fsClient
        .call<Tree>("tree", { path: "" })
        .then((tree) => {
          if (live) setData(tree.entries.map(toEntity));
        })
        .catch(fail);
    });
    const off = fsClient.onEvent((event) => {
      if (event.event !== "fs") return;
      const { kind, parent } = event.data;
      if (kind === "close") return;
      refresh(parent ? toId(parent) : ROOT).catch(fail);
    });
    return () => {
      live = false;
      offState();
      off();
    };
  }, [refresh]);

  // A re-root swaps the served tree while the socket stays open, so the
  // open-state effect above does not fire again. Re-read the root on change.
  useEffect(() => {
    let live = true;
    fsClient
      .ready()
      .then(() => fsClient.call<Tree>("tree", { path: "" }))
      .then((tree) => {
        if (live) setData(tree.entries.map(toEntity));
      })
      .catch((error) => useWorkStore.getState().fail(error));
    return () => {
      live = false;
    };
  }, [root]);

  const onRequestData = useCallback(
    (ev: { id: string }) => {
      refresh(ev.id).catch((error) => useWorkStore.getState().fail(error));
    },
    [refresh],
  );

  const init = useCallback((api: IApi) => {
    apiRef.current = api;
    const fail = (error: unknown) => useWorkStore.getState().fail(error);

    api.on("open-file", ({ id }) => {
      void useWorkStore.getState().open(toPath(id));
    });

    // In narrow mode a preview pane replaces the whole widget and renders no
    // toolbar to leave it by, so the column has no preview at all.
    api.intercept("show-preview", () => false);

    // Every mutation is one /fs op and then nothing: returning false keeps the
    // widget's in-memory copy out of it, so the tree only ever shows what the
    // server's `fs` event (and the explicit refresh of a move/copy target) says.
    api.intercept("create-file", async ({ file, parent }) => {
      const path = join(toPath(parent), file.name);
      try {
        if (file.type === "folder") {
          await fsClient.call("mkdir", { path });
        } else {
          const text = file.file ? await file.file.text() : "";
          await fsClient.call("write", { path, text });
          await fsClient.call("commit", { path });
          // write/commit push `buffer` events, not `fs` ones: a brand-new file
          // is invisible to the tree until its parent is re-read.
          await refresh(parent);
        }
      } catch (error) {
        fail(error);
      }
      return false;
    });

    api.intercept("rename-file", async ({ id, name }) => {
      try {
        await fsClient.call("rename", {
          path: toPath(id),
          to: join(toPath(parentOf(id)), name),
        });
      } catch (error) {
        fail(error);
      }
      return false;
    });

    api.intercept("delete-files", async ({ ids }) => {
      for (const id of ids) {
        try {
          await fsClient.call("delete", { path: toPath(id) });
        } catch (error) {
          fail(error);
        }
      }
      return false;
    });

    api.intercept("move-files", async ({ ids, target }) => {
      for (const id of ids) {
        try {
          await fsClient.call("rename", {
            path: toPath(id),
            to: join(toPath(target), nameOf(id)),
          });
        } catch (error) {
          fail(error);
        }
      }
      // The server's event names the source parent; the destination is ours.
      refresh(target).catch(fail);
      return false;
    });

    api.intercept("copy-files", async ({ ids, target }) => {
      for (const id of ids) {
        try {
          await fsClient.call("copy", {
            path: toPath(id),
            to: join(toPath(target), nameOf(id)),
          });
        } catch (error) {
          fail(error);
        }
      }
      return false;
    });
  }, [refresh]);

  const menuOptions = useCallback((mode: TContextMenuType) => {
    const defaults = getMenuOptions(mode);
    if (mode === "add") {
      // "Add new file/folder" ship with Material Design Icons, a font crow-web
      // does not carry; the vendored svar font has the same two glyphs.
      return defaults
        .filter((option) => option.id !== "upload")
        .map((option) => ({ ...option, icon: ADD_ICONS[String(option.id)] ?? option.icon }));
    }
    return defaults.filter(
      (option: IFileMenuOption) => option.comp === "separator" || MENU.has(String(option.id)),
    );
  }, []);

  if (!data) return <div className="crow-explorer crow-explorer-loading" />;

  const tree = (
    <Filemanager
      data={data}
      mode="table"
      preview={false}
      icons="simple"
      init={init}
      onRequestData={onRequestData}
      menuOptions={menuOptions}
    />
  );

  return (
    <div className="crow-explorer" data-testid="explorer">
      {scheme === "dark" ? <WillowDark fonts={false}>{tree}</WillowDark> : <Willow fonts={false}>{tree}</Willow>}
    </div>
  );
}
