package com.openworld.world;

import com.openworld.util.DataReader;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Ambient traffic by REGION (user, 2026-10-10: "industry more trucks, city normal cars + trucks, farm small trucks +
 * normal cars", and the amount per region) -- {@code game/traffic.json} through {@code Tables.TRAFFIC}. One island-wide
 * mix made a container quay and a shopping street draw the same cars. A region is a box of the places record
 * ({@link Places#regionAt}); its row is the one whose key is the longest PREFIX of the region's name, else the default.
 *
 * <p>Engine-free ({@code TrafficMixTest}). The pick is by a roll in [0, 1), so the host's choice is one number and a
 * test can walk it. Only the civilian pool is here: police / military traffic keep their own cars
 * ({@code VehicleModels.trafficScene}).
 */
public final class TrafficMix {

    /** One row: the share of the car budget, and the weighted models. */
    public record Row(double scale, List<String> ids, double[] weights, double total) {
        /** The model for a roll in [0, 1). */
        public String pick(double roll) {
            if (ids.isEmpty()) return "";
            double t = Math.max(0.0, Math.min(roll, 0.999999)) * total;
            for (int i = 0; i < weights.length; i++) if ((t -= weights[i]) < 0) return ids.get(i);
            return ids.get(ids.size() - 1);
        }

        /** A model's share of this row (0..1). */
        public double share(String id) {
            int i = ids.indexOf(id);
            return i < 0 || total <= 0 ? 0.0 : weights[i] / total;
        }
    }

    public static final Row EMPTY = new Row(1.0, List.of(), new double[0], 0.0);

    public final Row fallback;
    public final Map<String, Row> regions;

    public TrafficMix(Row fallback, Map<String, Row> regions) {
        this.fallback = fallback;
        this.regions = regions;
    }

    public static TrafficMix parse(String json) { return read(DataReader.of(json), id -> true); }

    /** {@code knownModel}: is this a vehicle the game has (an unknown id in a mix is a problem, and is skipped). */
    public static TrafficMix read(DataReader d, java.util.function.Predicate<String> knownModel) {
        DataReader def = d.child("default");
        Row fallback = def == null ? EMPTY : row(def, knownModel);
        if (def == null) d.problem("default", "missing (the mix of a region with no row)");
        Map<String, Row> regions = new LinkedHashMap<>();
        for (Map.Entry<String, DataReader> e : d.rows("regions").entrySet()) regions.put(e.getKey(), row(e.getValue(), knownModel));
        return new TrafficMix(fallback, regions);
    }

    private static Row row(DataReader r, java.util.function.Predicate<String> knownModel) {
        double scale = Math.max(0.0, r.num("scale", 1.0));
        List<String> ids = new ArrayList<>();
        List<Double> ws = new ArrayList<>();
        DataReader mix = r.child("mix");
        if (mix == null) r.problem("mix", "missing");
        else for (String id : mix.keys()) {
            double w = mix.num(id, 0.0);
            if (!knownModel.test(id)) { mix.problem(id, "not a vehicle model"); continue; }
            if (w <= 0) { mix.problem(id, "a weight must be positive"); continue; }
            ids.add(id);
            ws.add(w);
        }
        double[] weights = new double[ws.size()];
        double total = 0;
        for (int i = 0; i < weights.length; i++) total += weights[i] = ws.get(i);
        return new Row(scale, List.copyOf(ids), weights, total);
    }

    /** The row of a region name: the longest key that is a prefix of it, else the default. */
    public Row rowOf(String region) {
        Row best = fallback;
        int len = -1;
        if (region != null)
            for (Map.Entry<String, Row> e : regions.entrySet())
                if (region.startsWith(e.getKey()) && e.getKey().length() > len) {
                    best = e.getValue();
                    len = e.getKey().length();
                }
        return best.ids().isEmpty() ? fallback : best;
    }

    /** The civilian model id for a car set down in {@code region} ("" = no table: the caller's old mix). */
    public String pick(String region, double roll) { return rowOf(region).pick(roll); }

    /** The share of the car budget kept in {@code region}. */
    public double scale(String region) { return rowOf(region).scale(); }
}
