import { generateId } from "../../utils/id.js";
import { fromThreadMessageLike } from "./thread-message-like.js";
import { getRepositoryContentAutoStatus } from "./auto-status.js";
//#region src/runtime/utils/message-repository.ts
const ExportedMessageRepository = {
	fromArray: (messages) => {
		const conv = messages.map((m) => fromThreadMessageLike(m, generateId(), getRepositoryContentAutoStatus(m.content)));
		return { messages: conv.map((m, idx) => ({
			parentId: idx > 0 ? conv[idx - 1].id : null,
			message: m
		})) };
	},
	fromBranchableArray: (items, options) => {
		return {
			...options?.headId !== void 0 ? { headId: options.headId } : void 0,
			messages: items.map(({ message, parentId }) => {
				if (!message.id) throw new Error("ExportedMessageRepository.fromBranchableArray: Each message must have an 'id' field set.");
				return {
					parentId,
					message: fromThreadMessageLike(message, message.id, getRepositoryContentAutoStatus(message.content))
				};
			})
		};
	}
};
const findHead = (message) => {
	let current = message;
	while (current.next) current = current.next;
	return "current" in current ? current : null;
};
const withParentsFirst = (messages, isStored) => {
	const listed = new Set(messages.map((item) => item.message.id));
	const added = /* @__PURE__ */ new Set();
	const waiting = /* @__PURE__ */ new Map();
	const ordered = [];
	for (const item of messages) {
		const { parentId } = item;
		if (parentId !== null && listed.has(parentId) && !added.has(parentId) && !isStored(parentId)) {
			const children = waiting.get(parentId);
			if (children) children.push(item);
			else waiting.set(parentId, [item]);
			continue;
		}
		for (let i = ordered.push(item) - 1; i < ordered.length; i++) {
			const { id } = ordered[i].message;
			if (added.has(id)) continue;
			added.add(id);
			const children = waiting.get(id);
			if (!children) continue;
			waiting.delete(id);
			ordered.push(...children);
		}
	}
	for (const children of waiting.values()) ordered.push(...children);
	return ordered;
};
const withoutOrphanedMessages = (repository) => {
	const listed = new Set(repository.messages.map((item) => item.message.id));
	const children = /* @__PURE__ */ new Map();
	const pending = [];
	for (const { message, parentId } of repository.messages) {
		if (parentId === null) continue;
		const siblings = children.get(parentId);
		if (siblings) siblings.push(message.id);
		else children.set(parentId, [message.id]);
		if (!listed.has(parentId)) pending.push(message.id);
	}
	const dropped = /* @__PURE__ */ new Set();
	for (let i = 0; i < pending.length; i++) {
		const id = pending[i];
		if (dropped.has(id)) continue;
		dropped.add(id);
		for (const child of children.get(id) ?? []) pending.push(child);
	}
	const headMissing = repository.headId != null && !listed.has(repository.headId);
	if (dropped.size === 0 && !headMissing) return {
		repository,
		droppedIds: []
	};
	const droppedIds = [];
	const keptParents = /* @__PURE__ */ new Set();
	const messages = repository.messages.filter(({ message, parentId }) => {
		if (dropped.has(message.id)) {
			droppedIds.push(message.id);
			return false;
		}
		if (parentId !== null) keptParents.add(parentId);
		return true;
	});
	let { headId } = repository;
	if (headId != null && (headMissing || dropped.has(headId))) {
		headId = null;
		for (const { message } of messages) if (!keptParents.has(message.id)) headId = message.id;
	}
	return {
		repository: {
			...repository,
			messages,
			...headId !== void 0 && { headId }
		},
		droppedIds
	};
};
var CachedValue = class {
	_value = null;
	func;
	constructor(func) {
		this.func = func;
	}
	get value() {
		if (this._value === null) this._value = this.func();
		return this._value;
	}
	dirty() {
		this._value = null;
	}
};
var MessageRepository = class {
	messages = /* @__PURE__ */ new Map();
	head = null;
	root = {
		children: [],
		next: null
	};
	updateLevels(message, newLevel) {
		const pending = [{
			message,
			level: newLevel
		}];
		while (pending.length > 0) {
			const current = pending.pop();
			current.message.level = current.level;
			for (const childId of current.message.children) {
				const childMessage = this.messages.get(childId);
				if (childMessage) pending.push({
					message: childMessage,
					level: current.level + 1
				});
			}
		}
	}
	selectPathTo(message) {
		for (let current = message; current; current = current.prev) (current.prev ?? this.root).next = current;
	}
	performOp(newParent, child, operation) {
		const parentOrRoot = child.prev ?? this.root;
		const newParentOrRoot = newParent ?? this.root;
		if (operation === "relink" && parentOrRoot === newParentOrRoot) return;
		if (operation === "relink") {
			for (let current = newParent; current; current = current.prev) if (current.current.id === child.current.id) throw new Error("MessageRepository(performOp/relink): A message with the same id already exists in the parent tree. This error occurs if the same message id is found multiple times. This is likely an internal bug in assistant-ui.");
		}
		if (operation !== "link") {
			parentOrRoot.children = parentOrRoot.children.filter((m) => m !== child.current.id);
			if (parentOrRoot.next === child) {
				const fallbackId = parentOrRoot.children.at(-1);
				const fallback = fallbackId ? this.messages.get(fallbackId) : null;
				if (fallback === void 0) throw new Error("MessageRepository(performOp/cut): Fallback sibling message not found. This is likely an internal bug in assistant-ui.");
				parentOrRoot.next = fallback;
			}
		}
		if (operation !== "cut") {
			newParentOrRoot.children = [...newParentOrRoot.children, child.current.id];
			child.prev = newParent;
			if (findHead(child) === this.head) this.selectPathTo(child);
			else if (newParentOrRoot.next === null) {
				newParentOrRoot.next = child;
				if (this.head === newParentOrRoot) this.head = findHead(child);
			}
			const newLevel = newParent ? newParent.level + 1 : 0;
			this.updateLevels(child, newLevel);
		}
	}
	_messages = new CachedValue(() => {
		const messages = new Array((this.head?.level ?? -1) + 1);
		for (let current = this.head; current; current = current.prev) messages[current.level] = current.current;
		return messages;
	});
	get headId() {
		return this.head?.current.id ?? null;
	}
	get canonicalHeadId() {
		let head = this.head;
		while (head?.current.metadata?.isOptimistic) head = head.prev;
		return head?.current.id ?? null;
	}
	getMessages(headId) {
		if (headId === void 0 || headId === this.head?.current.id) return this._messages.value;
		const headMessage = this.messages.get(headId);
		if (!headMessage) throw new Error("MessageRepository(getMessages): Head message not found. This is likely an internal bug in assistant-ui.");
		const messages = new Array(headMessage.level + 1);
		for (let current = headMessage; current; current = current.prev) messages[current.level] = current.current;
		return messages;
	}
	addOrUpdateMessage(parentId, message) {
		const existingItem = this.messages.get(message.id);
		const prev = parentId ? this.messages.get(parentId) : null;
		if (prev === void 0) throw new Error("MessageRepository(addOrUpdateMessage): Parent message not found. This is likely an internal bug in assistant-ui.");
		if (existingItem) {
			this.performOp(prev, existingItem, "relink");
			existingItem.current = message;
			this._messages.dirty();
			return;
		}
		const newItem = {
			prev,
			current: message,
			next: null,
			children: [],
			level: prev ? prev.level + 1 : 0
		};
		this.messages.set(message.id, newItem);
		this.performOp(prev, newItem, "link");
		if (this.head === prev) this.head = newItem;
		this._messages.dirty();
	}
	getMessage(messageId) {
		const message = this.messages.get(messageId);
		if (!message) throw new Error("MessageRepository(updateMessage): Message not found. This is likely an internal bug in assistant-ui.");
		return {
			parentId: message.prev?.current.id ?? null,
			message: message.current,
			index: message.level
		};
	}
	deleteMessage(messageId, replacementId) {
		const message = this.messages.get(messageId);
		if (!message) throw new Error("MessageRepository(deleteMessage): Message not found. This is likely an internal bug in assistant-ui.");
		const replacement = replacementId === void 0 ? message.prev : replacementId === null ? null : this.messages.get(replacementId);
		if (replacement === void 0) throw new Error("MessageRepository(deleteMessage): Replacement not found. This is likely an internal bug in assistant-ui.");
		for (let current = replacement; current; current = current.prev) if (current === message) throw new Error("MessageRepository(deleteMessage): Replacement is the deleted message or one of its descendants. This is likely an internal bug in assistant-ui.");
		for (const child of message.children) {
			const childMessage = this.messages.get(child);
			if (!childMessage) throw new Error("MessageRepository(deleteMessage): Child message not found. This is likely an internal bug in assistant-ui.");
			this.performOp(replacement, childMessage, "relink");
		}
		this.performOp(null, message, "cut");
		this.messages.delete(messageId);
		if (this.head === message) this.head = findHead(replacement ?? this.root);
		this._messages.dirty();
	}
	hasChildren(messageId) {
		return (this.messages.get(messageId)?.children.length ?? 0) > 0;
	}
	getBranches(messageId) {
		const message = this.messages.get(messageId);
		if (!message) throw new Error("MessageRepository(getBranches): Message not found. This is likely an internal bug in assistant-ui.");
		const { children } = message.prev ?? this.root;
		return children;
	}
	/**
	* Evicts optimistic messages (`metadata.isOptimistic`) on the branch the head
	* just moved away from. Only that branch is walked, so an optimistic message
	* added off the head branch (such as the server-id copy that replaces a
	* client-id placeholder before the head moves to it) is kept until a
	* `switchToBranch` or `resetHead` moves the head off the branch it is on.
	* Keeps a client→server id swap from leaving a phantom sibling.
	*/
	evictOffBranchOptimisticMessages(previousHead, currentHead) {
		if (!previousHead) return;
		const onHeadBranch = /* @__PURE__ */ new Set();
		for (let current = currentHead; current; current = current.prev) onHeadBranch.add(current.current.id);
		const stale = [];
		for (let current = previousHead; current; current = current.prev) {
			if (onHeadBranch.has(current.current.id)) break;
			if (current.current.metadata?.isOptimistic) stale.push(current.current.id);
		}
		for (const id of stale) if (this.messages.has(id)) this.deleteMessage(id);
	}
	switchToBranch(messageId) {
		const message = this.messages.get(messageId);
		if (!message) throw new Error("MessageRepository(switchToBranch): Branch not found. This is likely an internal bug in assistant-ui.");
		const previousHead = this.head;
		this.selectPathTo(message);
		this.head = findHead(message);
		this.evictOffBranchOptimisticMessages(previousHead, this.head);
		this._messages.dirty();
	}
	resetHead(messageId) {
		if (messageId === null) {
			this.clear();
			return;
		}
		const message = this.messages.get(messageId);
		if (!message) throw new Error("MessageRepository(resetHead): Branch not found. This is likely an internal bug in assistant-ui.");
		const previousHead = this.head;
		if (message.children.length > 0) {
			const pending = [...message.children];
			while (pending.length > 0) {
				const childId = pending.pop();
				const childMessage = this.messages.get(childId);
				if (childMessage) {
					for (const descendantId of childMessage.children) pending.push(descendantId);
					this.messages.delete(childId);
				}
			}
			message.children = [];
			message.next = null;
		}
		this.head = message;
		this.selectPathTo(message);
		this.evictOffBranchOptimisticMessages(previousHead, this.head);
		this._messages.dirty();
	}
	clear() {
		this.messages.clear();
		this.head = null;
		this.root = {
			children: [],
			next: null
		};
		this._messages.dirty();
	}
	export() {
		const exportItems = [];
		const pending = [...this.root.children].reverse();
		while (pending.length > 0) {
			const message = this.messages.get(pending.pop());
			if (!message) continue;
			for (let i = message.children.length - 1; i >= 0; i--) pending.push(message.children[i]);
			if (message.current.metadata?.isOptimistic) continue;
			let prev = message.prev;
			while (prev && prev.current.metadata?.isOptimistic) prev = prev.prev;
			exportItems.push({
				message: message.current,
				parentId: prev?.current.id ?? null
			});
		}
		return {
			headId: this.canonicalHeadId,
			messages: exportItems
		};
	}
	import({ headId, messages }) {
		const ordered = withParentsFirst(messages, (id) => this.messages.has(id));
		for (const { message, parentId } of ordered) this.addOrUpdateMessage(parentId, message);
		this.resetHead(headId ?? ordered.at(-1)?.message.id ?? null);
	}
};
//#endregion
export { ExportedMessageRepository, MessageRepository, withoutOrphanedMessages };
