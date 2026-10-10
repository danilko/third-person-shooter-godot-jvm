package com.openworld.game.profile;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * One car the player OWNS (PLAN.md 1.4 / F4): which model, its paint, its per-instance upgrades and damage, and where
 * it is kept. Applied to a spawned Vehicle -- never written into the shared {@code VehicleConfig} .tres, which every
 * car of that model reads (the shared-resource trap, CLAUDE.md).
 */
public final class VehicleInstanceData {
    public String instanceId = "";
    /** The vehicle scene ({@code res://.../SPC1.tscn}). */
    public String model = "";
    /** Body colour as "#rrggbb", "" = the model's own. */
    public String paint = "";
    /** Upgrade name -> level ("nos" -> 1, "armour" -> 2 ...). */
    public final Map<String, Long> upgrades = new LinkedHashMap<>();
    /** 0..1 of the hull's health when it was last stored (1 = repaired). */
    public double condition = 1.0;
    /** The garage holding it ("" = out in the world / lost). */
    public String garageId = "";

    public long upgrade(String name) {
        Long v = upgrades.get(name);
        return v == null ? 0 : v;
    }

    Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", instanceId);
        m.put("model", model);
        m.put("paint", paint);
        m.put("upgrades", new LinkedHashMap<>(upgrades));
        m.put("condition", condition);
        m.put("garage", garageId);
        return m;
    }

    static VehicleInstanceData fromMap(Map<String, Object> m) {
        if (m == null) return null;
        VehicleInstanceData v = new VehicleInstanceData();
        v.instanceId = Maps.str(m, "id", "");
        v.model = Maps.str(m, "model", "");
        if (v.instanceId.isEmpty() || v.model.isEmpty()) return null;
        v.paint = Maps.str(m, "paint", "");
        Map<String, Object> up = Maps.map(m.get("upgrades"));
        if (up != null) for (String k : up.keySet()) v.upgrades.put(k, Maps.lng(up, k, 0));
        v.condition = Math.max(0.0, Math.min(1.0, Maps.num(m, "condition", 1.0)));
        v.garageId = Maps.str(m, "garage", "");
        return v;
    }
}
