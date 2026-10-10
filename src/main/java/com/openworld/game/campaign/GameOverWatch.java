package com.openworld.game.campaign;

import com.openworld.game.profile.PlayerProfile;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * Judges the {@link GameOverRule}s (PLAN.md 2.1 / CR4), about once a second, on the authority, per player:
 *
 * <ul>
 *   <li>a rule that starts to hold starts its grace timer and is WARNED once (told by the world);</li>
 *   <li>one that stops holding in time is CLEARED;</li>
 *   <li>one that outlasts its grace is that player's GAME OVER: their PROFILE goes back to its last campaign
 *       checkpoint (balance, career, story, cars). The world is not rolled back, nobody else is touched, the
 *       session goes on -- there is no permadeath.</li>
 * </ul>
 *
 * A checkpoint is only ever taken in a state no rule holds in ({@link #mayCheckpoint}), so a game over cannot land
 * the player in another one. A profile the watch first sees clean, with no checkpoint yet, gets one: the start of
 * the game is the first checkpoint. Engine-free; the caller does the telling and the respawn.
 */
public final class GameOverWatch {

    public enum Kind { WARNED, CLEARED, GAME_OVER }

    public record Notice(Kind kind, String playerId, GameOverRule rule) {}

    private final List<GameOverRule> rules;
    /** "player|rule" -> seconds the rule has held. */
    private final Map<String, Double> held = new LinkedHashMap<>();

    public GameOverWatch(List<GameOverRule> rules) { this.rules = List.copyOf(rules); }

    public List<GameOverRule> rules() { return rules; }

    /** Is the profile in a state no rule holds in (the only state a campaign checkpoint may be taken in)? */
    public boolean mayCheckpoint(PlayerProfile p, CampaignView story) {
        for (GameOverRule r : rules) if (r.breached(p, story)) return false;
        return true;
    }

    /** Seconds left before {@code rule} ends {@code playerId}'s game; -1 when it does not hold. */
    public double graceLeft(String playerId, GameOverRule rule) {
        Double h = held.get(playerId + "|" + rule.id());
        return h == null ? -1 : Math.max(0, rule.graceSeconds() - h);
    }

    /** {@code dt} seconds passed for these players (by player id). Applies each game over to its profile. */
    public List<Notice> step(double dt, Map<String, PlayerProfile> players, Function<String, CampaignView> story) {
        List<Notice> out = new ArrayList<>();
        held.keySet().removeIf(k -> !players.containsKey(k.substring(0, k.indexOf('|'))));
        for (Map.Entry<String, PlayerProfile> e : players.entrySet()) {
            String id = e.getKey();
            PlayerProfile p = e.getValue();
            CampaignView view = story.apply(id);
            if (p == null || view == null) continue;
            if (!p.hasCheckpoint() && mayCheckpoint(p, view)) p.takeCheckpoint();
            for (GameOverRule r : rules) {
                String key = id + "|" + r.id();
                if (!r.breached(p, view)) {
                    if (held.remove(key) != null) out.add(new Notice(Kind.CLEARED, id, r));
                    continue;
                }
                Double h = held.get(key);
                if (h == null) {
                    held.put(key, 0.0);
                    out.add(new Notice(Kind.WARNED, id, r));
                    continue;
                }
                if (h + dt < r.graceSeconds()) {
                    held.put(key, h + dt);
                    continue;
                }
                p.rollbackToCheckpoint();
                held.keySet().removeIf(k -> k.startsWith(id + "|"));
                out.add(new Notice(Kind.GAME_OVER, id, r));
                break;
            }
        }
        return out;
    }
}
