package com.openworld.util;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.function.BiConsumer;
import java.util.function.Function;
import java.util.function.Supplier;

/**
 * One data file -> one typed, validated value (PLAN.md 2.0). The game's tables were each loaded by their own
 * hand-written code, each with its own idea of what a missing file or a bad value means; none of them noticed a
 * misspelt key. A {@code DataTable<T>} is declared ONCE ({@code game.data.Tables} is the list of them), reads its
 * {@code res://} file the first time it is asked, hands the parser a {@link DataReader}, and keeps what the reader
 * found wrong ({@link #problems}). Engine-free: {@code DataTablesTest} loads every table from the source tree and
 * fails on any problem, so a bad table never reaches a play session.
 *
 * <p>A table with problems still LOADS (the parser's defaults fill the gaps) -- a typo must not stop the game on a
 * player's machine; the gate is what refuses it. A file that is missing or not JSON gives {@code fallback}.
 *
 * <p>{@link #reload} re-reads the file and tells the listeners ({@link #onReload}), which is the debug hot reload:
 * a system that keeps a derived copy re-derives it there.
 */
public final class DataTable<T> {

    /** Where a table's text comes from: null = no such file. */
    public interface Source { String read(String resPath); }

    /** The engine's resource filesystem (works in an exported build). */
    public static final Source ENGINE = p -> godot.api.FileAccess.fileExists(p) ? godot.api.FileAccess.getFileAsString(p) : null;

    /** The source tree on disk, {@code res://} = the working directory: unit tests and tools. */
    public static final Source DISK = p -> {
        Path f = Path.of(p.startsWith("res://") ? p.substring("res://".length()) : p);
        try {
            return Files.isRegularFile(f) ? Files.readString(f, StandardCharsets.UTF_8) : null;
        } catch (java.io.IOException e) {
            return null;
        }
    };

    private static Source source = ENGINE;
    private static BiConsumer<DataTable<?>, String> log = (t, m) -> System.err.println("DataTable " + t.name + ": " + m);
    private static final List<DataTable<?>> ALL = new ArrayList<>();

    public static synchronized void setSource(Source s) { source = s == null ? ENGINE : s; }

    /** How a table's problems are told (the engine installs GD.printErr). */
    public static synchronized void setLog(BiConsumer<DataTable<?>, String> l) { if (l != null) log = l; }

    /** Every declared table, in declaration order. */
    public static synchronized List<DataTable<?>> all() { return List.copyOf(ALL); }

    public final String name;
    public final String path;
    private final Function<DataReader, T> parser;
    private final Supplier<T> fallback;
    private final List<Runnable> listeners = new ArrayList<>();
    private T value;
    private boolean loaded;
    private List<String> problems = List.of();
    private int version;

    private DataTable(String name, String path, Function<DataReader, T> parser, Supplier<T> fallback) {
        this.name = name;
        this.path = path;
        this.parser = parser;
        this.fallback = fallback;
    }

    /** Declare a table. {@code fallback} is what a missing or unreadable file gives (may return null). */
    public static <T> DataTable<T> define(String name, String path, Function<DataReader, T> parser, Supplier<T> fallback) {
        DataTable<T> t = new DataTable<>(name, path, parser, fallback);
        synchronized (DataTable.class) { ALL.add(t); }
        return t;
    }

    /** A table that is NOT in {@link #all} (a test's, a tool's one-off). */
    public static <T> DataTable<T> detached(String name, String path, Function<DataReader, T> parser, Supplier<T> fallback) {
        return new DataTable<>(name, path, parser, fallback);
    }

    /** The table's value, loaded on first use. */
    public synchronized T get() {
        if (!loaded) load();
        return value;
    }

    /** What is wrong with the file as last loaded ([] = clean). */
    public synchronized List<String> problems() {
        if (!loaded) load();
        return problems;
    }

    /** Counts the loads: a consumer that derived something from the table can tell it changed. */
    public synchronized int version() { return version; }

    private void load() {
        loaded = true;
        version++;
        List<String> found = new ArrayList<>();
        String text = null;
        try {
            text = source.read(path);
        } catch (RuntimeException e) {
            found.add("unreadable: " + e);
        }
        if (text == null) {
            if (found.isEmpty()) found.add("no file at " + path);
            value = fallback.get();
        } else {
            DataReader r = DataReader.of(text);
            try {
                value = parser.apply(r);
                found.addAll(r.finish());
            } catch (RuntimeException e) {
                found.addAll(r.finish());
                found.add("parse failed: " + e);
                value = fallback.get();
            }
        }
        problems = List.copyOf(found);
        for (String p : problems) log.accept(this, p);
    }

    /** Read the file again (debug hot reload) and tell the listeners. Returns the problems of the new load. */
    public List<String> reload() {
        List<Runnable> tell;
        synchronized (this) {
            load();
            tell = List.copyOf(listeners);
        }
        for (Runnable r : tell) r.run();
        return problems;
    }

    /** Run {@code r} after every {@link #reload}. */
    public synchronized void onReload(Runnable r) { if (r != null && !listeners.contains(r)) listeners.add(r); }

    public synchronized void offReload(Runnable r) { listeners.remove(r); }

    /** Load every declared table and return its problems as {@code "<name>: <problem>"} ([] = all clean). */
    public static List<String> validateAll() {
        List<String> out = new ArrayList<>();
        for (DataTable<?> t : all()) for (String p : t.problems()) out.add(t.name + ": " + p);
        return out;
    }

    /** Re-read every table (debug). Returns the problems. */
    public static List<String> reloadAll() {
        List<String> out = new ArrayList<>();
        for (DataTable<?> t : all()) for (String p : t.reload()) out.add(t.name + ": " + p);
        return out;
    }
}
