package com.openworld.game.campaign;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * One node of the campaign graph (PLAN.md 2.1 / CR1): an activity's id, when it may be started, the variants it can
 * end with and what each one changes. Declared centrally by a {@link CampaignModule} -- not by a scene node's
 * {@code _ready}, which made a mission whose declaring node had not streamed in count as unlocked.
 *
 * <pre>
 *   b.activity("m01_konbini").title("The konbini job")
 *       .variant("BOSS_KILLED", Effect.storyDead("m01_boss"))
 *       .variant("BOSS_SPARED", Effect.set(SPARED_THE_BOSS));
 * </pre>
 */
public final class ActivityDef {

    /** STORY: once per variant, drives the campaign. JOB / RACE: repeatable free-roam activities. */
    public enum Kind { STORY, JOB, RACE }

    public final String id;
    String title = "";
    Kind kind = Kind.STORY;
    Requirement requirement = Requirement.always();
    boolean sticky;
    boolean repeatable;
    boolean planned;
    final Map<String, List<Effect>> variants = new LinkedHashMap<>();

    ActivityDef(String id) { this.id = id; }

    public ActivityDef title(String t) { title = t; return this; }

    public ActivityDef kind(Kind k) {
        kind = k;
        if (k != Kind.STORY) repeatable = true;
        return this;
    }

    /** When it may be started (default: always). Derived at every evaluation, so a branch can CLOSE again. */
    public ActivityDef requires(Requirement r) { requirement = r; return this; }

    /** Once it has been available it stays available, whatever the requirement says later. Off by default:
     *  choice-driven exclusivity needs branches that close. */
    public ActivityDef sticky() { sticky = true; return this; }

    /** May be completed again after it has been (a story activity is once; a REPLAY is another mode, not this). */
    public ActivityDef repeatable() { repeatable = true; return this; }

    /** Declared so other nodes can name it, but NOT AUTHORED yet: never available, and the lint says so in its
     *  notes instead of asking for variants. Remove it when the activity exists. */
    public ActivityDef planned() { planned = true; return this; }

    /** An outcome it can end with and what that changes. */
    public ActivityDef variant(String variant, Effect... effects) {
        variants.put(variant, List.of(effects));
        return this;
    }

    public String title() { return title; }
    public Kind kind() { return kind; }
    public Requirement requirement() { return requirement; }
    public boolean isSticky() { return sticky; }
    public boolean isRepeatable() { return repeatable; }
    public boolean isPlanned() { return planned; }
    public List<String> variants() { return new ArrayList<>(variants.keySet()); }
    public List<Effect> effects(String variant) { return variants.getOrDefault(variant, List.of()); }
    public boolean hasVariant(String variant) { return variants.containsKey(variant); }
}
