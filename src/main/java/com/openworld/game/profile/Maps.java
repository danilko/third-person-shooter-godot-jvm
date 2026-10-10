package com.openworld.game.profile;

import java.util.List;
import java.util.Map;

/** Typed reads out of a MiniJson tree (numbers arrive as Double). Package helpers for the profile / save shapes. */
public final class Maps {
    private Maps() {}

    @SuppressWarnings("unchecked")
    public static Map<String, Object> map(Object o) { return o instanceof Map<?, ?> m ? (Map<String, Object>) m : null; }

    @SuppressWarnings("unchecked")
    public static List<Object> list(Map<String, Object> m, String k) {
        Object o = m == null ? null : m.get(k);
        return o instanceof List<?> l ? (List<Object>) l : List.of();
    }

    public static String str(Map<String, Object> m, String k, String def) {
        Object o = m == null ? null : m.get(k);
        return o instanceof String s ? s : def;
    }

    public static long lng(Map<String, Object> m, String k, long def) {
        Object o = m == null ? null : m.get(k);
        return o instanceof Number n ? Math.round(n.doubleValue()) : def;
    }

    public static double num(Map<String, Object> m, String k, double def) {
        Object o = m == null ? null : m.get(k);
        return o instanceof Number n ? n.doubleValue() : def;
    }

    public static boolean bool(Map<String, Object> m, String k, boolean def) {
        Object o = m == null ? null : m.get(k);
        return o instanceof Boolean b ? b : def;
    }
}
