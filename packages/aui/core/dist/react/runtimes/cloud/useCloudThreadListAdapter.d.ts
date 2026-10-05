import type { RemoteThreadListAdapter } from "../../../runtimes/remote-thread-list/types.js";
import { type CloudThreadListAdapterOptions } from "./createCloudThreadListAdapter.js";
export declare const useCloudThreadListAdapter: (adapter: CloudThreadListAdapterOptions) => RemoteThreadListAdapter;