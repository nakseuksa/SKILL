package demo.trade;

public class TradeOrder {
    private long itemsCents, discountCents;
    private String carrier, tracking;

    public void price(long items, long discount) {
        if (items < 0 || discount < 0 || discount > items) throw new IllegalArgumentException();
        itemsCents = items;
        discountCents = discount;
    }
    public long due() { return itemsCents - discountCents; }
    public void ship(String via, String ref) {
        if (due() == 0 || via.isBlank() || ref.isBlank()) throw new IllegalStateException();
        carrier = via;
        tracking = ref;
    }
}
