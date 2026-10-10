package com.openworld.game.campaign;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * The campaign as declared (PLAN.md 2.1 / CR1): every flag, activity and ending the {@link CampaignModule}s named,
 * built once at boot. It answers, for ONE player in ONE world ({@link CampaignView}): which activities are available
 * now, and what completing one with a variant changes.
 *
 * <p><b>Unlocks are DERIVED per evaluation</b>, not stored: an activity is available while its requirement holds and
 * it has not been completed (unless repeatable), so a choice can close a branch as well as open one. Only an
 * activity declared {@code sticky()} is remembered as unlocked. An activity nobody declared is NOT available --
 * MissionDirector's "a mission with no declared row counts as unlocked" let an unstreamed node open a gated mission.
 *
 * <p><b>An ending is a state transition.</b> {@link Effect#ending} sets the phase to {@link #POST_ENDING}: free roam,
 * jobs and replays continue, and what the ending changed in the world stays (the ledger).
 */
public final class CampaignGraph {

    public static final String POST_ENDING = "POST_ENDING";

    private final Map<String, FlagKey> flags;
    private final Map<String, ActivityDef> activities;
    private final Set<String> endings;
    private final List<String> buildProblems;
    private final boolean openEnded;

    CampaignGraph(CampaignBuilder b) {
        flags = new LinkedHashMap<>(b.flags);
        activities = new LinkedHashMap<>(b.activities);
        endings = new LinkedHashSet<>(b.endings);
        buildProblems = List.copyOf(b.problems);
        openEnded = b.openEnded;
    }

    public FlagKey flag(String id) { return flags.get(id); }
    public List<FlagKey> flags() { return new ArrayList<>(flags.values()); }
    public ActivityDef activity(String id) { return activities.get(id); }
    public List<ActivityDef> activities() { return new ArrayList<>(activities.values()); }
    public Set<String> endings() { return new LinkedHashSet<>(endings); }
    public boolean isOpenEnded() { return openEnded; }
    List<String> buildProblems() { return buildProblems; }

    /** The key a completion is remembered by (the same shape MissionDirector's variant keys had). */
    public static String achievedKey(String activity, String variant) { return activity + "#" + (variant == null ? "" : variant); }

    /** May this player start it now, in this world? */
    public boolean isAvailable(String activityId, CampaignView v) {
        ActivityDef d = activities.get(activityId);
        if (d == null || d.planned) return false;
        if (!d.repeatable && v.achieved(d.id, "")) return false;
        return d.requirement.test(v) || (d.sticky && v.stickyUnlocked(d.id));
    }

    /** Every activity this player may start now, in declaration order. */
    public List<ActivityDef> available(CampaignView v) {
        List<ActivityDef> out = new ArrayList<>();
        for (ActivityDef d : activities.values()) if (isAvailable(d.id, v)) out.add(d);
        return out;
    }

    /** Why it is not available ("" = it is): the first failing part, for a tooltip / the console. */
    public String whyNot(String activityId, CampaignView v) {
        ActivityDef d = activities.get(activityId);
        if (d == null) return "no such activity";
        if (d.planned) return "not authored yet";
        if (!d.repeatable && v.achieved(d.id, "")) return "already completed";
        return isAvailable(activityId, v) ? "" : "requirement not met";
    }

    /** Remember every STICKY activity that is available now (call after anything that may have opened one). */
    public void refreshSticky(CampaignWrite w) {
        for (ActivityDef d : activities.values())
            if (d.sticky && !w.stickyUnlocked(d.id) && d.requirement.test(w)) w.unlockSticky(d.id);
    }

    /**
     * The player completed {@code activityId} with {@code variant}: record it and apply its effects. {@code world}
     * false applies the PERSONAL effects only (a guest without the host's consent). Returns false -- and changes
     * nothing -- for an unknown activity or variant.
     */
    public boolean complete(String activityId, String variant, CampaignWrite w, boolean world) {
        ActivityDef d = activities.get(activityId);
        if (d == null || !d.hasVariant(variant)) return false;
        w.achieve(activityId, variant);
        for (Effect e : d.effects(variant)) if (world || !e.world()) e.apply(w);
        refreshSticky(w);
        return true;
    }
}
