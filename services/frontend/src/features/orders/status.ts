import type { OrderStatus } from '../../api';

/** Where an order is, in shoppers' words. "waiting" is an accepted order not yet handed to the queue. */
export type Stage = 'waiting' | 'queued' | 'packing' | 'fulfilled' | 'failed';

export function stageOf(order: { status: OrderStatus; publication_pending: boolean }): Stage {
  switch (order.status) {
    case 'accepted':
      return order.publication_pending ? 'waiting' : 'queued';
    case 'processing':
      return 'packing';
    case 'fulfilled':
      return 'fulfilled';
    case 'failed':
      return 'failed';
  }
}

export function isFinished(stage: Stage): boolean {
  return stage === 'fulfilled' || stage === 'failed';
}

export const STAGES: Record<Stage, { label: string; headline: string; detail: string }> = {
  waiting: {
    label: 'Waiting to be queued',
    headline: 'Waiting to be queued',
    detail: 'Your order is saved. It joins the fulfillment queue as soon as the queue accepts it.',
  },
  queued: {
    label: 'Queued',
    headline: 'Queued for packing',
    detail: 'Your order is in the fulfillment queue, waiting for a packer to pick it up.',
  },
  packing: {
    label: 'Being packed',
    headline: 'Being packed',
    detail: 'A packer is preparing your order for dispatch.',
  },
  fulfilled: {
    label: 'Fulfilled',
    headline: 'Fulfilled',
    detail: 'Your order was packed and dispatched. The receipt is ready.',
  },
  failed: {
    label: 'Failed',
    headline: 'Could not be fulfilled',
    detail: 'Packing failed after several attempts. The items went back on the shelf and nothing was charged.',
  },
};

/** The route an order travels; a failed order stops at packing. */
export const STEPS = ['Placed', 'Queued', 'Packing', 'Dispatched'] as const;

export function currentStep(stage: Stage): number {
  return { waiting: 0, queued: 1, packing: 2, fulfilled: 3, failed: 2 }[stage];
}
