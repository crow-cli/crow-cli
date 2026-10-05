import { useCallback, useEffect, useState } from "react";

export const THEMES = ["system", "light", "dark", "macchiato"] as const;
export type Theme = (typeof THEMES)[number];
export type Resolved = Exclude<Theme, "system">;
/** What a component that only knows light from dark can consume: every dark
 *  flavour (dark, macchiato) publishes the `dark` class on <html>. */
export type ColorScheme = "light" | "dark";

const KEY = "crow-chat.theme";
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

const resolve = (theme: Theme): Resolved =>
  theme === "system" ? (media().matches ? "dark" : "light") : theme;

/** The resolved scheme, read off <html> where useTheme publishes it — the
 *  editor follows the theme dropdown without threading it through the runtime. */
export function useColorScheme(): ColorScheme {
  const [scheme, setScheme] = useState<ColorScheme>(() =>
    document.documentElement.classList.contains("dark") ? "dark" : "light",
  );
  useEffect(() => {
    const root = document.documentElement;
    const read = () => setScheme(root.classList.contains("dark") ? "dark" : "light");
    read();
    const observer = new MutationObserver(read);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return scheme;
}

/** One attribute on <html> picks the token set in src/themes/*.css; the
 *  dark class rides along so dark: utilities follow the resolved theme. */
export function useTheme(): [Theme, (next: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem(KEY) as Theme | null;
    return stored && (THEMES as readonly string[]).includes(stored)
      ? stored
      : "system";
  });
  const [resolved, setResolved] = useState<Resolved>(() => resolve(theme));

  useEffect(() => {
    const apply = () => setResolved(resolve(theme));
    apply();
    const mq = media();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = resolved;
    root.classList.toggle("dark", resolved !== "light");
  }, [resolved]);

  const save = useCallback((next: Theme) => {
    localStorage.setItem(KEY, next);
    setTheme(next);
  }, []);
  return [theme, save];
}
