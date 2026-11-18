import type { Invoice } from '../billing/invoice';
import { cents } from '@shop/money';

export interface Order { id: string; total: number; invoice?: Invoice }

export function amount(order: Order) {
  return cents(order.total);
}
