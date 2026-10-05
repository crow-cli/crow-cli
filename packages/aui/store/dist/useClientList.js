import { useClientLookup } from "./useClientLookup.js";
import { useEffect, useRef, useState } from "@assistant-ui/tap/react-shim";
import { withKey } from "@assistant-ui/tap";
//#region src/useClientList.ts
const createProps = (key, data, remove) => {
	return {
		key,
		getInitialData: () => {
			if (!data.hasData) throw new Error("getInitialData may only be called during initial render");
			return data.data;
		},
		remove
	};
};
const useClientList = (props) => {
	const { initialValues, getKey, resource: Resource } = props;
	const initialDataHandles = useRef([]).current;
	const [items_0, setItems] = useState(() => {
		const entries = [];
		for (const data of initialValues) {
			const key = getKey(data);
			const handle = {
				data,
				hasData: true
			};
			entries.push([key, createProps(key, handle, () => {
				setItems((items) => {
					const newItems = new Map(items);
					newItems.delete(key);
					return newItems;
				});
			})]);
			initialDataHandles.push(handle);
		}
		return new Map(entries);
	});
	const lookup = useClientLookup([...items_0.values()].map((props_0) => withKey(props_0.key, Resource(props_0), [props_0])));
	useEffect(() => {
		for (const handle_0 of initialDataHandles) {
			handle_0.data = void 0;
			handle_0.hasData = false;
		}
		initialDataHandles.length = 0;
	});
	const add = (data_0) => {
		const key_0 = getKey(data_0);
		setItems((items_1) => {
			if (items_1.has(key_0)) throw new Error(`Tried to add item with a key ${key_0} that already exists`);
			const handle_1 = {
				data: data_0,
				hasData: true
			};
			initialDataHandles.push(handle_1);
			return new Map(items_1).set(key_0, createProps(key_0, handle_1, () => {
				setItems((items_2) => {
					const newItems_0 = new Map(items_2);
					newItems_0.delete(key_0);
					return newItems_0;
				});
			}));
		});
	};
	return {
		state: lookup.state,
		get: lookup.get,
		add
	};
};
//#endregion
export { useClientList };
