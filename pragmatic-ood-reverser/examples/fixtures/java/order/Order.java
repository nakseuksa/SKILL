package demo.order;

public class Order {
    private final String id;
    private final long paidCents;
    private boolean refunded;

    public Order(String id, long paidCents) {
        this.id = id;
        this.paidCents = paidCents;
    }
    public String id() { return id; }
    public long paidCents() { return paidCents; }
    public boolean refunded() { return refunded; }
    public void markRefunded() { refunded = true; }
}
