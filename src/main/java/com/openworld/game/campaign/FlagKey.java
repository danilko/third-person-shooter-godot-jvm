package com.openworld.game.campaign;

import java.util.List;

/**
 * A campaign flag's declaration (PLAN.md 2.1 / CR1): a stable id, WHOSE it is, and the values it may take. Every flag
 * the campaign reads or writes is declared once in a {@link CampaignModule}; a requirement or an effect naming one
 * that is not declared, or a value it cannot take, is a lint error -- there is no untyped flag soup.
 *
 * <p><b>Scope</b> (the co-op model, rule 2): WORLD = a fact about the place ("the bridge is open") -- the host's, in
 * the {@code WorldLedger}; PERSONAL = a player's own story (a choice, trust earned) -- in that player's profile.
 * Never both.
 *
 * <p>A flag is a BOOL (unset / set) or a CHOICE among declared values (unset / one of them); the finite domain is
 * what lets {@link CampaignLint} walk every reachable state.
 */
public record FlagKey(String id, Scope scope, List<String> values) {

    public enum Scope { WORLD, PERSONAL }

    /** The stored value of a set BOOL. */
    public static final String ON = "1";

    public FlagKey {
        values = List.copyOf(values);
    }

    public static FlagKey bool(String id, Scope scope) { return new FlagKey(id, scope, List.of(ON)); }

    public static FlagKey choice(String id, Scope scope, String... values) { return new FlagKey(id, scope, List.of(values)); }

    public boolean isBool() { return values.size() == 1 && values.get(0).equals(ON); }

    public boolean allows(String value) { return values.contains(value); }
}
