// The API, worker, and TEST-ONLY database controls behind the browser tests.
// Every command runs services/backend/tests/e2e_stack.py through uv against the disposable
// PostgreSQL and RabbitMQ named by CLOUDCART_TEST_POSTGRES_URL / CLOUDCART_TEST_BROKER_URL.
import { type ChildProcess, execFileSync, spawn } from 'node:child_process';
import path from 'node:path';

const REPO_ROOT = path.resolve(import.meta.dirname, '../../../..');
const BACKEND_PROJECT = path.join(REPO_ROOT, 'services/backend');
const STACK_SCRIPT = path.join(BACKEND_PROJECT, 'tests/e2e_stack.py');

export const API_PORT = 18000;
export const WEB_PORT = 14173;
export const API_RELEASE = 'e2e-api';
export const STOREFRONT_RELEASE = 'e2e-web';
// TEST-ONLY instructor password for the throwaway cloudcart_e2e database.
export const ADMIN_PASSWORD = 'e2e-test-instructor-password';
// Simulated packing time, long enough to see "Being packed" in the storefront.
export const FULFILLMENT_DELAY_MS = 1500;

const WORKER_READY_TIMEOUT_MS = 30_000;
const WORKER_STOP_TIMEOUT_MS = 15_000;

export function requireTestDependencies(): void {
  for (const variable of ['CLOUDCART_TEST_POSTGRES_URL', 'CLOUDCART_TEST_BROKER_URL']) {
    if (!process.env[variable]) {
      throw new Error(
        `${variable} is not set. Start the dependencies with \`make test-deps-up\` and run \`make test-e2e\`.`,
      );
    }
  }
}

export function stackCommand(...args: string[]): string[] {
  return ['uv', 'run', '--locked', '--project', BACKEND_PROJECT, 'python', STACK_SCRIPT, ...args];
}

export function shellCommand(args: string[]): string {
  return args.map((arg) => `'${arg.replaceAll("'", `'\\''`)}'`).join(' ');
}

/** Run one stack command to completion and return its standard output. */
export function runStack(...args: string[]): string {
  const [command, ...rest] = stackCommand(...args);
  return execFileSync(command!, rest, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] });
}

export function resetCatalog(): void {
  runStack('reset-catalog');
}

export function setStock(sku: string, stock: number): void {
  runStack('set-stock', sku, String(stock));
}

export function expireGuestSessions(): void {
  runStack('expire-guest-sessions');
}

export type WorkerOptions = {
  /** TEST-ONLY fault: the simulated dispatch fails on attempts 1..N of every order (four attempts fail it). */
  failingAttempts?: number;
};

/** The fulfillment worker as a subprocess the tests can stop and start again. */
export class FulfillmentWorker {
  private process: ChildProcess | null = null;
  private failingAttempts = 0;
  private output = '';

  /** Leave a normal worker running, whatever a test did to it. */
  async restoreDefault(): Promise<void> {
    if (this.failingAttempts !== 0) await this.stop();
    await this.start();
  }

  async start({ failingAttempts = 0 }: WorkerOptions = {}): Promise<void> {
    if (this.process) {
      if (failingAttempts === this.failingAttempts) return;
      throw new Error('Stop the running worker before starting one with different faults.');
    }
    const [command, ...rest] = stackCommand(
      'worker',
      '--delay-ms',
      String(FULFILLMENT_DELAY_MS),
      '--failing-attempts',
      String(failingAttempts),
    );
    this.failingAttempts = failingAttempts;
    this.output = '';
    const child = spawn(command!, rest, { stdio: ['ignore', 'pipe', 'pipe'] });
    child.stdout?.on('data', (chunk) => (this.output += chunk));
    child.stderr?.on('data', (chunk) => (this.output += chunk));
    this.process = child;
    const deadline = Date.now() + WORKER_READY_TIMEOUT_MS;
    while (Number(runStack('queue-consumers').trim()) < 1) {
      if (child.exitCode !== null || Date.now() > deadline) {
        await this.stop();
        throw new Error(`The worker did not start consuming the orders queue. Output:\n${this.output}`);
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }

  /** SIGTERM (warm shutdown: the current task finishes), then wait for the process to exit. */
  async stop(): Promise<void> {
    const child = this.process;
    if (!child) return;
    this.process = null;
    this.failingAttempts = 0;
    if (child.exitCode !== null) return;
    const exited = new Promise<void>((resolve) => child.once('exit', () => resolve()));
    child.kill('SIGTERM');
    const timer = setTimeout(() => child.kill('SIGKILL'), WORKER_STOP_TIMEOUT_MS);
    await exited;
    clearTimeout(timer);
  }
}
