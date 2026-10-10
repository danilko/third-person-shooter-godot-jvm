package com.openworld.util;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * A JSON object that REMEMBERS what was read from it (PLAN.md 2.0, the review's "typed records + one DataTable
 * loader"). Every table used to be walked by hand with casts and {@code getOrDefault}: a misspelt key in the data
 * ({@code "min_star"}) silently kept the default, and a string where a number belongs became 0. Here a parser asks
 * for each key by name and type; when it is done, {@link #finish} names every key nobody asked for and every value
 * of the wrong type, with its path ({@code crimes.gunfire.min_star: unknown key}).
 *
 * <p>Engine-free. A key named {@code note}, ending in {@code _note} or starting with {@code _} is a comment and is
 * never a problem. Several parsers may read from one reader (crimes.json feeds the wanted rules, the dispatch and
 * the recovery fees): the unknown-key check is over what ALL of them read.
 */
public final class DataReader {

    private final Map<String, Object> map;
    private final String path;
    private final List<String> problems;
    private final Set<String> read = new LinkedHashSet<>();
    private final List<DataReader> children = new ArrayList<>();
    /** One reader per child object, however many parsers ask for it: what one read, the other does not report. */
    private final Map<String, DataReader> childByKey = new LinkedHashMap<>();
    private final Map<String, List<DataReader>> itemsByKey = new LinkedHashMap<>();

    private DataReader(Map<String, Object> map, String path, List<String> problems) {
        this.map = map;
        this.path = path;
        this.problems = problems;
    }

    /** Parse {@code json} (an object at the top). A text that is not an object reads as empty, with a problem. */
    public static DataReader of(String json) {
        List<String> problems = new ArrayList<>();
        Object doc = null;
        try {
            doc = json == null ? null : MiniJson.parse(json);
        } catch (RuntimeException e) {
            problems.add("not JSON: " + e.getMessage());
        }
        Map<String, Object> m = asMap(doc);
        if (m == null) {
            if (problems.isEmpty()) problems.add("the document is not a JSON object");
            m = new LinkedHashMap<>();
        }
        return new DataReader(m, "", problems);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object o) { return o instanceof Map<?, ?> m ? (Map<String, Object>) m : null; }

    private String at(String key) { return path.isEmpty() ? key : path + "." + key; }

    private Object take(String key) {
        read.add(key);
        return map.get(key);
    }

    private void wrong(String key, String wanted, Object found) {
        problems.add(at(key) + ": expected " + wanted + ", found " + describe(found));
    }

    private static String describe(Object o) {
        if (o == null) return "null";
        if (o instanceof String) return "a string";
        if (o instanceof Number) return "a number";
        if (o instanceof Boolean) return "a boolean";
        if (o instanceof List<?>) return "a list";
        if (o instanceof Map<?, ?>) return "an object";
        return o.getClass().getSimpleName();
    }

    public boolean has(String key) { return map.containsKey(key); }

    /** Every key of this object that is not a comment, in file order (for a table keyed by id). */
    public List<String> keys() {
        List<String> out = new ArrayList<>();
        for (String k : map.keySet()) if (!isComment(k)) out.add(k);
        return out;
    }

    public String path() { return path; }

    // ── scalars ──

    public String str(String key, String def) {
        Object o = take(key);
        if (o == null) return def;
        if (o instanceof String s) return s;
        wrong(key, "a string", o);
        return def;
    }

    public double num(String key, double def) {
        Object o = take(key);
        if (o == null) return def;
        if (o instanceof Number n) return n.doubleValue();
        wrong(key, "a number", o);
        return def;
    }

    public long lng(String key, long def) {
        Object o = take(key);
        if (o == null) return def;
        if (o instanceof Number n) return Math.round(n.doubleValue());
        wrong(key, "a number", o);
        return def;
    }

    public int integer(String key, int def) { return (int) lng(key, def); }

    public boolean bool(String key, boolean def) {
        Object o = take(key);
        if (o == null) return def;
        if (o instanceof Boolean b) return b;
        wrong(key, "a boolean", o);
        return def;
    }

    /** A value that MUST be there: a missing one is a problem (and reads as {@code def}). */
    public double reqNum(String key, double def) {
        if (!map.containsKey(key)) problems.add(at(key) + ": missing");
        return num(key, def);
    }

    public String reqStr(String key, String def) {
        if (!map.containsKey(key)) problems.add(at(key) + ": missing");
        return str(key, def);
    }

    // ── lists ──

    private List<?> list(String key) {
        Object o = take(key);
        if (o == null) return null;
        if (o instanceof List<?> l) return l;
        wrong(key, "a list", o);
        return null;
    }

    /** A list of strings ([] when absent). */
    public List<String> strings(String key) {
        List<String> out = new ArrayList<>();
        List<?> l = list(key);
        if (l == null) return out;
        for (int i = 0; i < l.size(); i++) {
            if (l.get(i) instanceof String s) out.add(s);
            else wrong(key + "[" + i + "]", "a string", l.get(i));
        }
        return out;
    }

    /** A list of numbers; null when the key is absent (so a caller can keep its own default). */
    public double[] nums(String key) {
        List<?> l = list(key);
        if (l == null) return null;
        double[] out = new double[l.size()];
        for (int i = 0; i < out.length; i++) {
            if (l.get(i) instanceof Number n) out[i] = n.doubleValue();
            else wrong(key + "[" + i + "]", "a number", l.get(i));
        }
        return out;
    }

    /** A list of whole numbers; null when the key is absent. */
    public int[] ints(String key) {
        double[] d = nums(key);
        if (d == null) return null;
        int[] out = new int[d.length];
        for (int i = 0; i < out.length; i++) out[i] = (int) Math.round(d[i]);
        return out;
    }

    public List<Long> longs(String key) {
        List<Long> out = new ArrayList<>();
        double[] d = nums(key);
        if (d != null) for (double v : d) out.add(Math.round(v));
        return out;
    }

    /** A list of string lists (weapons by stars); [] when absent. */
    public List<List<String>> stringLists(String key) {
        List<List<String>> out = new ArrayList<>();
        List<?> l = list(key);
        if (l == null) return out;
        for (int i = 0; i < l.size(); i++) {
            List<String> row = new ArrayList<>();
            if (l.get(i) instanceof List<?> inner) {
                for (int j = 0; j < inner.size(); j++) {
                    if (inner.get(j) instanceof String s) row.add(s);
                    else wrong(key + "[" + i + "][" + j + "]", "a string", inner.get(j));
                }
            } else wrong(key + "[" + i + "]", "a list", l.get(i));
            out.add(row);
        }
        return out;
    }

    // ── structure ──

    /** The object under {@code key}, or null when absent (a value of another type is a problem). */
    public DataReader child(String key) {
        DataReader known = childByKey.get(key);
        if (known != null) return known;
        Object o = take(key);
        if (o == null) return null;
        Map<String, Object> m = asMap(o);
        if (m == null) {
            wrong(key, "an object", o);
            return null;
        }
        DataReader c = new DataReader(m, at(key), problems);
        children.add(c);
        childByKey.put(key, c);
        return c;
    }

    /** Like {@link #child} but never null: an absent object reads as an empty one (every key its default). */
    public DataReader childOrEmpty(String key) {
        DataReader c = child(key);
        if (c != null) return c;
        c = new DataReader(new LinkedHashMap<>(), at(key), problems);
        children.add(c);
        childByKey.put(key, c);
        return c;
    }

    /** A table keyed by id: {@code {"gunfire": {...}, "murder": {...}}} -> id -> its reader, in file order. */
    public Map<String, DataReader> rows(String key) {
        Map<String, DataReader> out = new LinkedHashMap<>();
        DataReader table = child(key);
        if (table == null) return out;
        for (String id : table.keys()) {
            DataReader row = table.child(id);
            if (row != null) out.put(id, row);
        }
        return out;
    }

    /** A list of objects ([] when absent); an element that is not an object is a problem and is skipped. */
    public List<DataReader> items(String key) {
        List<DataReader> known = itemsByKey.get(key);
        if (known != null) return known;
        List<DataReader> out = new ArrayList<>();
        itemsByKey.put(key, out);
        List<?> l = list(key);
        if (l == null) return out;
        for (int i = 0; i < l.size(); i++) {
            Map<String, Object> m = asMap(l.get(i));
            if (m == null) {
                wrong(key + "[" + i + "]", "an object", l.get(i));
                continue;
            }
            DataReader c = new DataReader(m, at(key) + "[" + i + "]", problems);
            children.add(c);
            out.add(c);
        }
        return out;
    }

    /** A problem only the parser can see (an id that names nothing, a weight that must be positive). */
    public void problem(String key, String message) { problems.add(at(key) + ": " + message); }

    /** The untyped value (a free-form part: an outfit's colour list or material path). Counts as read. */
    public Object raw(String key) { return take(key); }

    /** Keys another consumer owns, or that are deliberately not read here. */
    public DataReader ignore(String... keys) {
        for (String k : keys) read.add(k);
        return this;
    }

    private static boolean isComment(String key) {
        return key.equals("note") || key.endsWith("_note") || key.startsWith("_");
    }

    private void collectUnknown(List<String> out) {
        for (String k : map.keySet()) if (!read.contains(k) && !isComment(k)) out.add(at(k) + ": unknown key");
        for (DataReader c : children) c.collectUnknown(out);
    }

    /** Every problem found so far: wrong types, missing required keys, and keys nobody read (here and below). */
    public List<String> finish() {
        List<String> out = new ArrayList<>(problems);
        collectUnknown(out);
        return out;
    }
}
