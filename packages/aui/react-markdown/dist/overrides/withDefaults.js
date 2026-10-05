import classNames from "classnames";
//#region src/overrides/withDefaults.ts
const withDefaultProps = ({ className, ...defaultProps }) => ({ className: classNameProp, ...props }) => {
	return {
		className: classNames(className, classNameProp),
		...defaultProps,
		...props
	};
};
//#endregion
export { withDefaultProps };
