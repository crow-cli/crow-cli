import { isDevelopment } from "./env.js";
//#region src/core/helpers/root.ts
const createResourceFiberRoot = (dispatchUpdate) => {
	return {
		version: 0,
		committedVersion: 0,
		dispatchUpdate,
		changelog: [],
		committedLog: [],
		unsettledCount: 0,
		rollbackCallbacks: []
	};
};
const commitRoot = (root) => {
	root.committedVersion = root.version;
	for (const record of root.changelog) {
		record.logged = false;
		if (!record.settled) {
			record.settled = true;
			root.unsettledCount--;
		}
		root.committedLog.push(record);
	}
	root.changelog.length = 0;
	if (root.unsettledCount === 0) root.committedLog.length = 0;
	root.rollbackCallbacks.length = 0;
};
const setRootVersion = (root, version) => {
	const rollback = root.version > version;
	root.version = version;
	if (rollback) {
		for (let i = 0; i < root.rollbackCallbacks.length; i++) root.rollbackCallbacks[i]();
		root.rollbackCallbacks.length = 0;
		if (version <= root.committedVersion) {
			const rewound = [];
			while (root.committedVersion - rewound.length > version) {
				const record = root.committedLog.pop();
				if (record === void 0) {
					if (isDevelopment) throw new Error("tap: committed history is shorter than the replay base.");
					break;
				}
				markReducerDirty(record.fiber, record.cell);
				record.cell.workInProgress = record.prevState;
				rewound.push({
					record,
					prevState: record.prevState,
					eagerState: record.eagerState,
					hasEagerState: record.hasEagerState
				});
			}
			if (rewound.length > 0) {
				const restoredVersion = root.committedVersion;
				addRollback(root, () => {
					for (let i = rewound.length - 1; i >= 0; i--) {
						const entry = rewound[i];
						entry.record.prevState = entry.prevState;
						entry.record.eagerState = entry.eagerState;
						entry.record.hasEagerState = entry.hasEagerState;
						root.committedLog.push(entry.record);
					}
					root.committedVersion = restoredVersion;
				});
			}
			root.committedVersion = version;
			for (const record of root.changelog) record.logged = false;
			root.changelog.length = 0;
		} else {
			while (root.committedVersion + root.changelog.length > version) root.changelog.pop().logged = false;
			for (let i = 0; i < root.changelog.length; i++) applyChangelogRecord(root.changelog[i]);
			commitRoot(root);
		}
	}
};
const applyChangelogRecord = (record) => {
	markReducerDirty(record.fiber, record.cell);
	if (!record.queued) {
		record.queued = true;
		(record.cell.queue ??= []).push(record);
	}
};
const addCommit = (fiber, callback) => {
	fiber.wipCommitCallbacks.push(callback);
};
const addRollback = (root, callback) => {
	root.rollbackCallbacks.push(callback);
};
const markReducerDirty = (fiber, cell) => {
	if (cell.isDirty) return;
	cell.isDirty = true;
	fiber.markDirty?.();
	addRollback(fiber.root, () => {
		if (cell.queue !== null) {
			for (const record of cell.queue) record.queued = false;
			cell.queue = null;
		}
		cell.workInProgress = cell.current;
		cell.isDirty = false;
	});
};
//#endregion
export { addCommit, addRollback, applyChangelogRecord, commitRoot, createResourceFiberRoot, markReducerDirty, setRootVersion };
