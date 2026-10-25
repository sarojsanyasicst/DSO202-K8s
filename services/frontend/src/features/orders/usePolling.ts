import { useEffect, useState } from 'react';

import { ApiError, messageOf } from '../../api';

export const POLL_INTERVAL_MS = 2000;

type Polled<T> = { value: T | null; notFound: boolean; error: string | null };

/**
 * Load `load()` now and every two seconds until `finished(value)` or unmount. A failed request
 * keeps the last value, shows the error, and tries again on the next tick; 404 (or a malformed
 * id, 422) stops polling and reports `notFound`.
 */
export function usePolling<T>(load: () => Promise<T>, finished: (value: T) => boolean, key: unknown): Polled<T> {
  const [state, setState] = useState<Polled<T>>({ value: null, notFound: false, error: null });

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setState({ value: null, notFound: false, error: null });

    async function tick() {
      try {
        const value = await load();
        if (stopped) return;
        setState({ value, notFound: false, error: null });
        if (finished(value)) return;
      } catch (error) {
        if (stopped) return;
        if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
          setState({ value: null, notFound: true, error: null });
          return;
        }
        setState((previous) => ({ ...previous, error: messageOf(error) }));
      }
      timer = setTimeout(tick, POLL_INTERVAL_MS);
    }

    void tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
    // `load` and `finished` are new functions on every render; `key` names what is polled.
  }, [key]);

  return state;
}
