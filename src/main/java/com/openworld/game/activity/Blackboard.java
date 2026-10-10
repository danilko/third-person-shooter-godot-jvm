package com.openworld.game.activity;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * An activity run's own state between stages ("how many crates are loaded"), TYPED by its keys -- not a
 * Map&lt;String, Object&gt; soup -- and plain enough to go into an {@link ActivityCheckpoint} and a save file.
 *
 * <pre>
 *   static final Blackboard.Key&lt;Long&gt; LOADED = Blackboard.count("loaded");
 *   a.board().set(LOADED, a.board().get(LOADED) + 1);
 * </pre>
 */
public final class Blackboard {

    /** A key and what an unset one reads as. Declare them as constants of the activity class. */
    public record Key<T>(String name, Class<T> type, T unset) {}

    public static Key<Long> count(String name) { return new Key<>(name, Long.class, 0L); }
    public static Key<Double> number(String name) { return new Key<>(name, Double.class, 0.0); }
    public static Key<Boolean> flag(String name) { return new Key<>(name, Boolean.class, false); }
    public static Key<String> text(String name) { return new Key<>(name, String.class, ""); }

    private final Map<String, Object> values = new LinkedHashMap<>();

    public <T> T get(Key<T> k) {
        Object v = values.get(k.name());
        // a save file has no int / long / double distinction: read a number as the key's type
        if (v instanceof Number n && k.type() == Long.class) return k.type().cast(n.longValue());
        if (v instanceof Number n && k.type() == Double.class) return k.type().cast(n.doubleValue());
        return k.type().isInstance(v) ? k.type().cast(v) : k.unset();
    }

    public <T> void set(Key<T> k, T value) {
        if (value == null || value.equals(k.unset())) values.remove(k.name());
        else values.put(k.name(), value);
    }

    public Map<String, Object> toMap() { return new LinkedHashMap<>(values); }

    public void read(Map<String, Object> m) {
        values.clear();
        if (m != null) values.putAll(m);
    }
}
