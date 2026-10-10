package com.openworld.util;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * A small engine-free JSON reader: objects become {@code Map<String,Object>}, arrays
 * {@code List<Object>}, numbers {@code Double}, plus {@code String}, {@code Boolean} and null.
 *
 * <p>Exists so a large data file (a 2.4 MB {@code .lanekit.json}) can be read in plain Java — once
 * through Godot's {@code JSON} every number is a bridge call, and a unit test cannot run it at all.
 * Strict enough for machine-written files; it throws {@link IllegalArgumentException} on anything
 * malformed rather than guessing.
 */
public final class MiniJson {

    private final String s;
    private int i;

    private MiniJson(String s) { this.s = s; }

    public static Object parse(String text) {
        MiniJson p = new MiniJson(text);
        p.ws();
        Object v = p.value();
        p.ws();
        if (p.i != p.s.length()) throw p.err("trailing text");
        return v;
    }

    private Object value() {
        if (i >= s.length()) throw err("unexpected end");
        char c = s.charAt(i);
        switch (c) {
            case '{': return object();
            case '[': return array();
            case '"': return string();
            case 't': lit("true");  return Boolean.TRUE;
            case 'f': lit("false"); return Boolean.FALSE;
            case 'n': lit("null");  return null;
            default:  return number();
        }
    }

    private Map<String, Object> object() {
        Map<String, Object> m = new LinkedHashMap<>();
        i++; ws();
        if (peek() == '}') { i++; return m; }
        while (true) {
            ws();
            if (peek() != '"') throw err("expected key");
            String k = string();
            ws(); expect(':'); ws();
            m.put(k, value());
            ws();
            char c = next();
            if (c == '}') return m;
            if (c != ',') throw err("expected , or }");
        }
    }

    private List<Object> array() {
        List<Object> a = new ArrayList<>();
        i++; ws();
        if (peek() == ']') { i++; return a; }
        while (true) {
            ws();
            a.add(value());
            ws();
            char c = next();
            if (c == ']') return a;
            if (c != ',') throw err("expected , or ]");
        }
    }

    private String string() {
        i++;
        StringBuilder sb = null;
        int start = i;
        while (true) {
            if (i >= s.length()) throw err("unterminated string");
            char c = s.charAt(i);
            if (c == '"') {
                String out = sb == null ? s.substring(start, i) : sb.append(s, start, i).toString();
                i++;
                return out;
            }
            if (c == '\\') {
                if (sb == null) sb = new StringBuilder();
                sb.append(s, start, i);
                char e = s.charAt(i + 1);
                switch (e) {
                    case 'n': sb.append('\n'); break;
                    case 't': sb.append('\t'); break;
                    case 'r': sb.append('\r'); break;
                    case 'b': sb.append('\b'); break;
                    case 'f': sb.append('\f'); break;
                    case 'u': sb.append((char) Integer.parseInt(s.substring(i + 2, i + 6), 16)); i += 4; break;
                    default:  sb.append(e);
                }
                i += 2;
                start = i;
                continue;
            }
            i++;
        }
    }

    private Double number() {
        int start = i;
        while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
        if (start == i) throw err("unexpected character '" + s.charAt(i) + "'");
        return Double.parseDouble(s.substring(start, i));
    }

    private void lit(String w) {
        if (!s.startsWith(w, i)) throw err("expected " + w);
        i += w.length();
    }

    private void ws() {
        while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++;
    }

    private char peek() { return i < s.length() ? s.charAt(i) : '\0'; }

    private char next() {
        if (i >= s.length()) throw err("unexpected end");
        return s.charAt(i++);
    }

    private void expect(char c) {
        if (next() != c) throw err("expected '" + c + "'");
    }

    private IllegalArgumentException err(String what) {
        return new IllegalArgumentException("JSON: " + what + " at offset " + i);
    }

    /**
     * The writer twin of {@link #parse}: Map (keys in the map's order) / List / String / Number / Boolean / null, into
     * compact JSON. A whole number is written without a fraction, so a long round-trips through {@code parse}'s
     * Double exactly (up to 2^53). Throws on anything else rather than guessing.
     */
    public static String write(Object v) {
        StringBuilder b = new StringBuilder();
        writeTo(b, v);
        return b.toString();
    }

    private static void writeTo(StringBuilder b, Object v) {
        if (v == null) { b.append("null"); return; }
        if (v instanceof String str) { quote(b, str); return; }
        if (v instanceof Boolean bo) { b.append(bo); return; }
        if (v instanceof Number n) {
            double d = n.doubleValue();
            if (Double.isNaN(d) || Double.isInfinite(d)) throw new IllegalArgumentException("JSON: " + d);
            if (n instanceof Long || n instanceof Integer || n instanceof Short || n instanceof Byte
                    || (d == Math.rint(d) && Math.abs(d) < 9.007199254740992E15)) b.append((long) d);
            else b.append(d);
            return;
        }
        if (v instanceof java.util.Map<?, ?> m) {
            b.append('{');
            boolean first = true;
            for (java.util.Map.Entry<?, ?> e : m.entrySet()) {
                if (!first) b.append(',');
                first = false;
                quote(b, String.valueOf(e.getKey()));
                b.append(':');
                writeTo(b, e.getValue());
            }
            b.append('}');
            return;
        }
        if (v instanceof java.util.Collection<?> c) {
            b.append('[');
            boolean first = true;
            for (Object o : c) {
                if (!first) b.append(',');
                first = false;
                writeTo(b, o);
            }
            b.append(']');
            return;
        }
        throw new IllegalArgumentException("JSON: cannot write " + v.getClass().getName());
    }

    private static void quote(StringBuilder out, String s) {
        out.append('"');
        for (int k = 0; k < s.length(); k++) {
            char c = s.charAt(k);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) out.append(String.format("\\u%04x", (int) c));
                    else out.append(c);
                }
            }
        }
        out.append('"');
    }
}
