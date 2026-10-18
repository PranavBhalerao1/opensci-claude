/**
 * setInterval for polling the API, minus the polls nobody sees: it stops while the tab is hidden
 * (minimised, in the background) and fetches once, then resumes, as soon as the tab is visible
 * again. Returns the cleanup function, like an effect.
 *
 * Every poll reads the database behind the API, and the database's traffic is metered, so a
 * forgotten background tab must not keep polling for hours.
 */
export function pollWhileVisible(fn: () => void, ms: number): () => void {
  let timer: ReturnType<typeof setInterval> | null = null;
  const start = () => {
    if (timer === null) timer = setInterval(fn, ms);
  };
  const stop = () => {
    if (timer !== null) clearInterval(timer);
    timer = null;
  };
  const onVisibility = () => {
    if (document.hidden) {
      stop();
    } else if (timer === null) {
      fn();
      start();
    }
  };
  document.addEventListener("visibilitychange", onVisibility);
  if (!document.hidden) start();
  return () => {
    stop();
    document.removeEventListener("visibilitychange", onVisibility);
  };
}
