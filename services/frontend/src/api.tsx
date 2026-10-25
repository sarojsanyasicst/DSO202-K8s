// Typed access to the CloudCart API and the guest session every shopper request runs under.
// Request and response types come from src/api/schema.d.ts, generated from the API's OpenAPI
// document by `make frontend-types`; nothing here restates a backend schema by hand.
import createClient from 'openapi-fetch';
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';

import type { components, paths } from './api/schema';

export type Product = components['schemas']['ProductView'];
export type Cart = components['schemas']['CartView'];
export type Order = components['schemas']['OrderView'];
export type OrderItem = components['schemas']['OrderItemView'];
export type Receipt = components['schemas']['ReceiptView'];
export type AdminOrders = components['schemas']['AdminOrdersView'];
export type AdminOrder = components['schemas']['AdminOrderView'];
export type OrderStatus = Order['status'];

export const api = createClient<paths>({ baseUrl: window.location.origin });

/** The API answered with an error status. `message` is the API's own explanation when it gave one. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** The request never got an answer: the network or the shop is unreachable. */
export class ConnectionError extends Error {
  constructor() {
    super('The shop did not answer. Check your connection and try again.');
  }
}

/** The guest session ended while a change was under way, so the change was not retried in the new one. */
export class SessionRenewedError extends Error {
  constructor() {
    super('Your previous session ended, so you have a new, empty cart.');
  }
}

type Answer<T> = { data?: T; error?: unknown; response: Response };

/** Run one openapi-fetch request and return its data, or throw ApiError / ConnectionError. */
export async function call<T>(request: () => Promise<Answer<T>>): Promise<T> {
  let answer: Answer<T>;
  try {
    answer = await request();
  } catch {
    throw new ConnectionError();
  }
  if (answer.response.ok) return answer.data as T;
  throw new ApiError(answer.response.status, detailOf(answer.error));
}

function detailOf(error: unknown): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === 'string') return detail;
  return 'The shop could not complete that request.';
}

export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Try again.';
}

/** A fresh Idempotency-Key. getRandomValues also works on plain-HTTP origins, unlike randomUUID. */
export function newIdempotencyKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

type GuestRun<T> = (csrfToken: string, renewed: boolean) => Promise<T>;

type GuestSession = {
  /**
   * Run guest requests with the session's CSRF token. A 401, or a 403 for a stale CSRF token,
   * starts a new session once; `run` is then retried with `renewed` true unless `retry` is false,
   * in which case SessionRenewedError is thrown.
   */
  withGuest<T>(run: GuestRun<T>, options?: { retry?: boolean }): Promise<T>;
  /** Increases whenever the shopper becomes a different guest; data loaded for an older guest is stale. */
  epoch: number;
  sessionEnded: boolean;
  dismissSessionEnded(): void;
};

const GuestSessionContext = createContext<GuestSession | null>(null);

export function GuestSessionProvider({ children }: { children: ReactNode }) {
  const pending = useRef<Promise<string> | null>(null);
  const current = useRef<string | null>(null);
  const [epoch, setEpoch] = useState(0);
  const [sessionEnded, setSessionEnded] = useState(false);

  // One GET /session at a time: two simultaneous first calls would create two guests.
  const session = useCallback((): Promise<string> => {
    pending.current ??= call(() => api.GET('/api/v1/session')).then(
      ({ csrf_token }) => {
        if (current.current !== null && current.current !== csrf_token) {
          setEpoch((value) => value + 1);
          setSessionEnded(true);
        }
        current.current = csrf_token;
        return csrf_token;
      },
      (error: unknown) => {
        pending.current = null;
        throw error;
      },
    );
    return pending.current;
  }, []);

  const withGuest = useCallback(
    async <T,>(run: GuestRun<T>, { retry = true }: { retry?: boolean } = {}): Promise<T> => {
      const used = session();
      try {
        return await run(await used, false);
      } catch (error) {
        if (!(error instanceof ApiError) || (error.status !== 401 && error.status !== 403)) throw error;
        if (pending.current === used) pending.current = null;
        const renewed = await session();
        if (!retry) throw new SessionRenewedError();
        return run(renewed, true);
      }
    },
    [session],
  );

  const value = useMemo(
    () => ({ withGuest, epoch, sessionEnded, dismissSessionEnded: () => setSessionEnded(false) }),
    [withGuest, epoch, sessionEnded],
  );
  return <GuestSessionContext.Provider value={value}>{children}</GuestSessionContext.Provider>;
}

export function useGuestSession(): GuestSession {
  const session = useContext(GuestSessionContext);
  if (!session) throw new Error('useGuestSession needs a GuestSessionProvider.');
  return session;
}
