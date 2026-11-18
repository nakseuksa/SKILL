import java.util.HashSet;
import java.util.Set;

/** The handle owns the backing set. Element equality/hash codes must remain stable. */
public final class LockedSetHandle<T> {
    private final Set<T> rep = new HashSet<>();

    public synchronized boolean insert(T item) {
        return rep.add(item);
    }

    public synchronized boolean isMember(T item) {
        return rep.contains(item);
    }
}
