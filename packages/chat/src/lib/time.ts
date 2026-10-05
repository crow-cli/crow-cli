/**
 * A thread row's age in the shortest honest form: "just now", "12m ago",
 * "3h ago", "2d ago", then the date. Empty for a session the agent reported
 * without an `updatedAt`, so the row shows no stamp rather than a wrong one.
 */
export function relativeTime(
  iso: string | undefined,
  now: number = Date.now(),
): string {
  if (!iso) return "";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const seconds = Math.round((now - then) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(then).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}
