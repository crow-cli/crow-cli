import { type Unstable_InteractableVersion } from "../../model-context/interactable-composer-metadata.js";
/**
 * Every version of a tool-created interactable recorded in the current
 * thread, oldest first: the creating tool call, each user edit, and each
 * `update_*` call. Each entry carries the full state as of that version and a
 * `restore()` that sets the live instance back to it — enough for a version
 * picker like an artifact's history dropdown.
 *
 * @deprecated Unstable / Experimental (not actually removed).
 */
export declare const unstable_useInteractableVersions: <TState = unknown>(id: string, name: string) => (Omit<Unstable_InteractableVersion, "state"> & {
    state: TState;
    restore: () => void;
})[];