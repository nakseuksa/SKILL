package demo.payment;

import demo.order.Order;

public class RefundService {
    public interface Gateway { void refund(String orderId, long cents); }
    private final Gateway gateway;
    public RefundService(Gateway gateway) { this.gateway = gateway; }

    public void refund(Order order) {
        if (order.refunded()) throw new IllegalStateException("already refunded");
        gateway.refund(order.id(), order.paidCents());
        order.markRefunded();
    }
}
