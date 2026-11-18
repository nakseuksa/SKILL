import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class TestLockedSetHandle {
    public static void main(String[] args) throws Exception {
        var set = new LockedSetHandle<Integer>();
        if (set.isMember(0)) throw new AssertionError("not initially empty");
        Callable<Integer> addAndRead = () -> {
            int added = 0;
            for (int i = 0; i < 1000; i++) {
                if (set.insert(i)) added++;
                if (!set.isMember(i)) throw new AssertionError("lost insertion");
            }
            return added;
        };
        var pool = Executors.newFixedThreadPool(2);
        try {
            var a = pool.submit(addAndRead);
            var b = pool.submit(addAndRead);
            if (a.get(10, TimeUnit.SECONDS) + b.get(10, TimeUnit.SECONDS) != 1000)
                throw new AssertionError("duplicate insertion or lost element");
        } finally {
            pool.shutdownNow();
        }
    }
}
