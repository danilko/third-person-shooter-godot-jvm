package com.openworld.game.profile;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

/**
 * The ONE door money goes through (PLAN.md 1.4: AR2 + CR4). Before, cash was a field on the BODY, mutated in four
 * systems and hand-copied across a respawn. Now every change is {@code transfer(from, to, amount, reason)} between
 * two profiles, either of which may be the world (null): a shop sale is player -> world, a robbed till world ->
 * player. Engine-free ({@code EconomyTest}); it runs where the money is decided -- the host in co-op.
 *
 * <p><b>Who may go below zero (CR4):</b> only a reason that {@link Reason#allowsDebt} -- a bill (hospital, bail), a
 * fine, a loan. A purchase, a fee or a ransom is REFUSED when the balance does not cover it. The shortfall of a bill
 * is simply a negative balance: what the player owes, paid back by the next income.
 *
 * <p>Every applied transfer is told to the listeners (the save's dirty flag, the host's profile send, and AR3's
 * GameplayEvents when they exist) -- money changes can be reacted to without each caller remembering to.
 */
public final class Economy {
    private Economy() {}

    public enum Reason {
        PURCHASE(false), SALE(false), REWARD(false), ROBBERY(false), GANG_FEE(false), RANSOM(false),
        BILL_HOSPITAL(true), BILL_BAIL(true), FINE(true), LOAN(true), REPAYMENT(false), GRANT(false), REFUND(false);

        public final boolean allowsDebt;
        Reason(boolean allowsDebt) { this.allowsDebt = allowsDebt; }
    }

    /** An applied transfer: {@code from} / {@code to} null = the world. */
    public record Transfer(PlayerProfile from, PlayerProfile to, long amount, Reason reason) {}

    private static final List<Consumer<Transfer>> LISTENERS = new ArrayList<>();
    private static long applied, refused;

    public static void listen(Consumer<Transfer> l) { if (l != null && !LISTENERS.contains(l)) LISTENERS.add(l); }
    public static void unlisten(Consumer<Transfer> l) { LISTENERS.remove(l); }

    /** Whether {@code from} can pay {@code amount} for {@code reason} (the world always can). */
    public static boolean canPay(PlayerProfile from, long amount, Reason reason) {
        return from == null || reason.allowsDebt || from.balance >= amount;
    }

    /**
     * Move {@code amount} (> 0) dollars. False -- and nothing changes -- when the amount is not positive, both sides are
     * the world, or {@code from} cannot cover it and the reason does not allow debt.
     */
    public static boolean transfer(PlayerProfile from, PlayerProfile to, long amount, Reason reason) {
        if (amount <= 0 || reason == null || (from == null && to == null) || from == to) return false;
        if (!canPay(from, amount, reason)) { refused++; return false; }
        if (from != null) { from.balance -= amount; from.touch(); }
        if (to != null) { to.balance += amount; to.touch(); }
        applied++;
        Transfer t = new Transfer(from, to, amount, reason);
        for (Consumer<Transfer> l : List.copyOf(LISTENERS)) l.accept(t);
        return true;
    }

    /** A bill: takes all of it, into debt if need be. Returns the amount taken (== bill). */
    public static long bill(PlayerProfile who, long amount, Reason reason) {
        return transfer(who, null, amount, reason) ? amount : 0;
    }

    public static long appliedCount() { return applied; }
    public static long refusedCount() { return refused; }
}
