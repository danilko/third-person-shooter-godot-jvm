package com.openworld.world;

import godot.api.FileAccess;
import godot.api.Translation;
import godot.api.TranslationServer;
import godot.global.GD;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Everything the world writes in a native script -- street plates, expressway guide signs, station boards, the
 * respawn cards -- by ID, from ONE string table: {@link #PATH} ({@code key,ja,zh_TW,en}, written by
 * {@code tools/build_sign_table.py}, which only ever adds what is missing).
 *
 * <p>User, 2026-10-12: "keep these names with id, and names can be more easily translated, without need to
 * recompile"; "for now keep Japanese, but also able to go Chinese Traditional (English subtitle on both)". So:
 * <ul>
 *   <li>the table is read at first use, and {@link #USER_PATH} on top of it (a row there replaces the shipped one, a
 *       new column adds a language) -- a translation is an edit and a restart, no compile and no import;</li>
 *   <li>a sign shows TWO lines, {@link #local} in the sign language ({@link #language()}, the GAME tab's choice,
 *       {@code settings.cfg [game] sign_language}) and {@link #en} under it -- two columns of one row at once,
 *       which is why this reads the table itself rather than asking {@code tr()} for the one current locale;</li>
 *   <li>every language column is also registered with Godot's {@link TranslationServer} (locale = the column's
 *       name), so a scene or a script can {@code tr("street.nishi_dori")} like any other Godot string.</li>
 * </ul>
 * An empty cell falls back to {@code ja}, then to the key's own tail, so a half-translated language still reads.
 */
public final class SignText {

    public static final String PATH = "res://src/main/resources/com/openworld/i18n/signs.csv";
    public static final String USER_PATH = "user://signs.csv";
    /** The language the names were written in: the fallback of every other column. */
    public static final String SOURCE = "ja";
    public static final String ENGLISH = "en";

    private static Map<String, Map<String, String>> rows;
    private static final List<String> languages = new ArrayList<>();
    private static String language = SOURCE;

    private SignText() {}

    /** The sign languages the table carries (every column but the key and English), the source first. */
    public static List<String> languages() {
        table();
        return languages;
    }

    public static String language() { return language; }

    /** Pick the sign language (a column's name). An unknown one keeps the source language. */
    public static void setLanguage(String lang) {
        table();
        language = lang != null && languages.contains(lang) ? lang : SOURCE;
    }

    /** {@code key}'s text in the sign language; the source language's when that cell is empty; else the key's tail. */
    public static String local(String key) { return in(language, key); }

    /** {@code key}'s English line. */
    public static String en(String key) { return in(ENGLISH, key); }

    /** True when the table has a row for {@code key}. */
    public static boolean has(String key) { return table().containsKey(key); }

    public static String in(String lang, String key) {
        Map<String, String> r = table().get(key);
        if (r == null) return key == null ? "" : key.substring(key.indexOf('.') + 1);
        String v = r.get(lang);
        if (v == null || v.isEmpty()) v = r.get(SOURCE);
        return v == null || v.isEmpty() ? key.substring(key.indexOf('.') + 1) : v;
    }

    /** {@link #local} of a pattern row, its {@code {0}}, {@code {1}} replaced by {@code args}. */
    public static String local(String key, String... args) { return fill(local(key), args); }

    public static String en(String key, String... args) { return fill(en(key), args); }

    private static String fill(String s, String[] args) {
        for (int i = 0; i < args.length; i++) s = s.replace("{" + i + "}", args[i] == null ? "" : args[i]);
        return s;
    }

    /** Forget the table (a probe that rewrote the user file; the next call reads it again). */
    public static void reload() { rows = null; }

    private static Map<String, Map<String, String>> table() {
        if (rows != null) return rows;
        rows = new HashMap<>();
        languages.clear();
        read(PATH);
        read(USER_PATH);
        if (!languages.contains(SOURCE)) languages.add(0, SOURCE);
        register();
        return rows;
    }

    private static void read(String path) {
        if (!FileAccess.fileExists(path)) return;
        List<List<String>> lines = parse(FileAccess.getFileAsString(path));
        if (lines.isEmpty()) return;
        List<String> cols = lines.get(0);
        for (int c = 1; c < cols.size(); c++) {
            String name = cols.get(c).trim();
            if (!name.isEmpty() && !name.equals(ENGLISH) && !languages.contains(name)) languages.add(name);
        }
        for (int i = 1; i < lines.size(); i++) {
            List<String> l = lines.get(i);
            if (l.isEmpty() || l.get(0).isEmpty()) continue;
            Map<String, String> r = rows.computeIfAbsent(l.get(0), k -> new HashMap<>());
            for (int c = 1; c < cols.size() && c < l.size(); c++) {
                if (!l.get(c).isEmpty()) r.put(cols.get(c).trim(), l.get(c));
            }
        }
    }

    /** RFC 4180 enough for a spreadsheet's export: quoted cells, doubled quotes, commas and newlines inside quotes. */
    static List<List<String>> parse(String text) {
        List<List<String>> out = new ArrayList<>();
        List<String> row = new ArrayList<>();
        StringBuilder cell = new StringBuilder();
        boolean quoted = false;
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (quoted) {
                if (ch == '"' && i + 1 < text.length() && text.charAt(i + 1) == '"') { cell.append('"'); i++; }
                else if (ch == '"') quoted = false;
                else cell.append(ch);
            } else if (ch == '"') quoted = true;
            else if (ch == ',') { row.add(cell.toString()); cell.setLength(0); }
            else if (ch == '\n' || ch == '\r') {
                if (ch == '\r' && i + 1 < text.length() && text.charAt(i + 1) == '\n') i++;
                row.add(cell.toString());
                cell.setLength(0);
                if (row.size() > 1 || !row.get(0).isEmpty()) out.add(row);
                row = new ArrayList<>();
            } else if (ch != '﻿') cell.append(ch);
        }
        if (cell.length() > 0 || !row.isEmpty()) { row.add(cell.toString()); out.add(row); }
        return out;
    }

    /** One Godot Translation per column, so tr() and TranslationServer.translate see the same strings. */
    private static void register() {
        try {
            List<String> all = new ArrayList<>(languages);
            all.add(ENGLISH);
            for (String lang : all) {
                Translation t = new Translation();
                t.setLocale(lang);
                for (Map.Entry<String, Map<String, String>> e : rows.entrySet()) {
                    String v = e.getValue().get(lang);
                    if (v != null && !v.isEmpty()) t.addMessage(e.getKey(), v, "");
                }
                TranslationServer.addTranslation(t);
            }
        } catch (RuntimeException e) {
            GD.printErr("SignText: could not register the table with the TranslationServer: " + e.getMessage());
        }
    }
}
