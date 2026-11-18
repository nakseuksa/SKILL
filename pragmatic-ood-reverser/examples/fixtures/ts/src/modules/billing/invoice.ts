import type { Order } from '../ordering/order';

export interface Invoice { orderId: Order['id']; total: number }
