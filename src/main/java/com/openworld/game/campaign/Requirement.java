package com.openworld.game.campaign;

import java.util.List;
import java.util.function.Consumer;

/**
 * When an activity may be started (PLAN.md 2.1 / CR1): a small typed predicate algebra over a {@link CampaignView},
 * instead of MissionDirector's "all of these variant keys". It is DATA the lint can read -- which flags and variants
 * it names -- and not a lambda, which is why {@link CampaignLint} can prove every requirement names something
 * declared and that no reachable state is a dead end.
 *
 * <pre>
 *   all(achieved("m01_konbini", "BOSS_SPARED"), not(flag(INFORMANT_BURNED)), storyAlive("m01_boss"))
 * </pre>
 */
public sealed interface Requirement {

    boolean test(CampaignView v);

    /** Visit this node and everything under it (the lint collects what is named). */
    default void visit(Consumer<Requirement> c) { c.accept(this); }

    record Always() implements Requirement {
        @Override public boolean test(CampaignView v) { return true; }
    }

    /** The flag has {@code value} ("" = it is set to anything). */
    record Flag(FlagKey key, String value) implements Requirement {
        @Override public boolean test(CampaignView v) {
            String now = v.flag(key);
            return value.isEmpty() ? !now.isEmpty() : value.equals(now);
        }
    }

    /** Completed {@code activity} with {@code variant} ("" = any). */
    record Achieved(String activity, String variant) implements Requirement {
        @Override public boolean test(CampaignView v) { return v.achieved(activity, variant); }
    }

    /** The player's effective career. */
    record Career(String career) implements Requirement {
        @Override public boolean test(CampaignView v) { return v.hasCareer(career); }
    }

    record CashAtLeast(long dollars) implements Requirement {
        @Override public boolean test(CampaignView v) { return v.balance() >= dollars; }
    }

    /** A WORLD requirement: this story character is alive in the world the activity would run in. */
    record StoryAlive(String storyId) implements Requirement {
        @Override public boolean test(CampaignView v) { return !v.storyDead(storyId); }
    }

    /** Before any ending ({@code post} false) or after one ({@code post} true). */
    record PostEnding(boolean post) implements Requirement {
        @Override public boolean test(CampaignView v) { return CampaignGraph.POST_ENDING.equals(v.phase()) == post; }
    }

    record EndingSeen(String ending) implements Requirement {
        @Override public boolean test(CampaignView v) { return v.endingSeen(ending); }
    }

    record All(List<Requirement> of) implements Requirement {
        public All { of = List.copyOf(of); }
        @Override public boolean test(CampaignView v) {
            for (Requirement r : of) if (!r.test(v)) return false;
            return true;
        }
        @Override public void visit(Consumer<Requirement> c) { c.accept(this); for (Requirement r : of) r.visit(c); }
    }

    record Any(List<Requirement> of) implements Requirement {
        public Any { of = List.copyOf(of); }
        @Override public boolean test(CampaignView v) {
            for (Requirement r : of) if (r.test(v)) return true;
            return false;
        }
        @Override public void visit(Consumer<Requirement> c) { c.accept(this); for (Requirement r : of) r.visit(c); }
    }

    record Not(Requirement of) implements Requirement {
        @Override public boolean test(CampaignView v) { return !of.test(v); }
        @Override public void visit(Consumer<Requirement> c) { c.accept(this); of.visit(c); }
    }

    // ── how content writes them ──

    static Requirement always() { return new Always(); }
    static Requirement flag(FlagKey key) { return new Flag(key, ""); }
    static Requirement flag(FlagKey key, String value) { return new Flag(key, value); }
    static Requirement achieved(String activity) { return new Achieved(activity, ""); }
    static Requirement achieved(String activity, String variant) { return new Achieved(activity, variant); }
    static Requirement career(String career) { return new Career(career); }
    static Requirement cashAtLeast(long dollars) { return new CashAtLeast(dollars); }
    static Requirement storyAlive(String storyId) { return new StoryAlive(storyId); }
    static Requirement beforeEnding() { return new PostEnding(false); }
    static Requirement afterEnding() { return new PostEnding(true); }
    static Requirement endingSeen(String ending) { return new EndingSeen(ending); }
    static Requirement all(Requirement... of) { return new All(List.of(of)); }
    static Requirement any(Requirement... of) { return new Any(List.of(of)); }
    static Requirement not(Requirement of) { return new Not(of); }
}
