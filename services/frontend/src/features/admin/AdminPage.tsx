// The instructor view: sign-in, the order backlog across all guests, and stock levels.
import { useCallback, useEffect, useState, type FormEvent } from 'react';

import { ApiError, api, call, messageOf } from '../../api';
import { formatTime } from '../../format';
import { InventoryTable } from './InventoryTable';
import { OrdersOverview } from './OrdersOverview';

/** How often the instructor view refreshes orders and stock. */
export const REFRESH_INTERVAL_MS = 3000;

type Access = { state: 'checking' } | { state: 'signed-out'; notice?: string } | { state: 'signed-in'; csrfToken: string };

export function AdminPage() {
  const [access, setAccess] = useState<Access>({ state: 'checking' });

  // An instructor session outlives page reloads: ask the API whether this browser still has one.
  useEffect(() => {
    let current = true;
    call(() => api.GET('/api/v1/admin/session')).then(
      ({ csrf_token }) => current && setAccess({ state: 'signed-in', csrfToken: csrf_token }),
      () => current && setAccess({ state: 'signed-out' }),
    );
    return () => {
      current = false;
    };
  }, []);

  const sessionEnded = useCallback(
    () => setAccess({ state: 'signed-out', notice: 'Your instructor session ended. Sign in again.' }),
    [],
  );

  if (access.state === 'checking') return <p className="loading">Checking your instructor session…</p>;
  if (access.state === 'signed-out') {
    return <SignIn notice={access.notice} onSignedIn={(csrfToken) => setAccess({ state: 'signed-in', csrfToken })} />;
  }
  return (
    <Dashboard
      csrfToken={access.csrfToken}
      onSignedOut={() => setAccess({ state: 'signed-out' })}
      onSessionEnded={sessionEnded}
    />
  );
}

function SignIn({ notice, onSignedIn }: { notice?: string; onSignedIn(csrfToken: string): void }) {
  const [problem, setProblem] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSubmitting(true);
    setProblem(null);
    try {
      const session = await call(() =>
        api.POST('/api/v1/admin/login', {
          body: { username: String(form.get('username')), password: String(form.get('password')) },
        }),
      );
      onSignedIn(session.csrf_token);
    } catch (error) {
      setProblem(
        error instanceof ApiError && error.status === 401
          ? 'Username or password is incorrect.'
          : error instanceof ApiError && error.status === 422
            ? 'Enter a username and a password.'
            : messageOf(error),
      );
      setSubmitting(false);
    }
  }

  return (
    <div className="sign-in">
      <div className="page-intro">
        <h1>Instructor sign-in</h1>
        <p>The instructor view shows every guest's orders and lets you change stock levels.</p>
      </div>
      {notice && (
        <p className="panel" role="status">
          {notice}
        </p>
      )}
      <form className="panel form" onSubmit={(event) => void submit(event)}>
        <label htmlFor="username">Username</label>
        <input id="username" name="username" autoComplete="username" required maxLength={64} />
        <label htmlFor="password">Password</label>
        <input id="password" name="password" type="password" autoComplete="current-password" required maxLength={256} />
        {problem && (
          <p className="problem" role="alert">
            {problem}
          </p>
        )}
        <button type="submit" className="button primary" disabled={submitting}>
          Sign in
        </button>
      </form>
    </div>
  );
}

type DashboardProps = { csrfToken: string; onSignedOut(): void; onSessionEnded(): void };

function Dashboard({ csrfToken, onSignedOut, onSessionEnded }: DashboardProps) {
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [tick, setTick] = useState(0);
  const [signOutProblem, setSignOutProblem] = useState<string | null>(null);

  useEffect(() => {
    const timer = setInterval(() => setTick((value) => value + 1), REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  const loaded = useCallback(() => setUpdatedAt(new Date()), []);

  async function signOut() {
    setSignOutProblem(null);
    try {
      await call(() => api.POST('/api/v1/admin/logout', { params: { header: { 'X-CSRF-Token': csrfToken } } }));
      onSignedOut();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onSignedOut();
      else setSignOutProblem(messageOf(error));
    }
  }

  return (
    <>
      <div className="page-intro admin-intro">
        <div>
          <h1>Instructor view</h1>
          <p className="muted">
            Refreshes every {REFRESH_INTERVAL_MS / 1000} seconds.
            {updatedAt && ` Last updated ${formatTime(updatedAt)}.`}
          </p>
        </div>
        <button type="button" className="button secondary" onClick={() => void signOut()}>
          Sign out
        </button>
      </div>
      {signOutProblem && (
        <p className="problem" role="alert">
          {signOutProblem}
        </p>
      )}
      <OrdersOverview tick={tick} onLoaded={loaded} onSessionEnded={onSessionEnded} />
      <InventoryTable tick={tick} csrfToken={csrfToken} onSessionEnded={onSessionEnded} />
    </>
  );
}
