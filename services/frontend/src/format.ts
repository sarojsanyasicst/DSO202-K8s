const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
const time = new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' });

export function formatMoney(cents: number): string {
  return money.format(cents / 100);
}

export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

export function formatTime(date: Date): string {
  return time.format(date);
}

/** The first eight hex digits of an order id: what shoppers and the instructor call the order. */
export function orderNumber(orderId: string): string {
  return orderId.slice(0, 8).toUpperCase();
}

export function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}
