package com.openworld.net;

import godot.api.StreamPeerBuffer;
import godot.core.PackedByteArray;
import godot.core.Quaternion;
import godot.core.Vector3;
import com.openworld.character.Character;
import com.openworld.character.CharacterInfo;
import com.openworld.character.Health;
import com.openworld.control.Controller;
import com.openworld.game.EventBus;
import com.openworld.game.GameManager;
import com.openworld.item.Pickup;
import com.openworld.movement.character.MovementController;
import com.openworld.movement.character.MovementType;
import com.openworld.movement.character.StanceName;
import com.openworld.weapon.WeaponController;

/**
 * Wire-format encode/decode for {@code MSG_*} payloads — isolates the
 * {@link StreamPeerBuffer} byte layout from {@link NetworkManager}. Every
 * {@code encode*} prefixes the message with its {@code MSG_*} tag byte; every
 * {@code decode*} assumes the tag byte has already been consumed by the caller's
 * dispatch switch. Each message type gets an immutable {@code Decoded*} record
 * carrier so handlers receive plain values, never a live buffer.
 */
public final class NetMessageCodec {

    private NetMessageCodec() { }

    // ── MSG_SNAPSHOT / MSG_SNAPSHOT_BATCH ─────────────────────────────────────
    //
    // Per-entry body (shared by the singular and batched forms):
    // [characterId utf8][tick i64][position 3×float][velocity 3×float][aimTarget 3×float]
    // [flags u8][yaw float][currentHealth float][senderTimeMs i32]
    //
    // MSG_SNAPSHOT:       [tag u8][entry]
    // MSG_SNAPSHOT_BATCH: [tag u8][count u16][entry]*
    //
    // The flags field (u16) packs the four small enums that used to be replicated as
    // separate MultiplayerSynchronizer properties — bit0 = combat, bits1-3 =
    // stanceOrdinal (3 bits, 0-7 — fits StanceName's 5 values incl. SWIM), bits4-6 =
    // activeSlotIndex (0-6, fits WeaponController's 7 slots), bits7-8 = movementTypeOrdinal
    // (0-2, fits MovementType's IDLE/WALK/SPRINT). Widened from a u8 to a u16 when SWIM was
    // added (5 stances no longer fit the old 2-bit field) — see SNAPSHOT_ENTRY_FIXED_BYTES.
    //
    // aimTarget is the world-space spine-IK look point (a far point along the owner's
    // aim direction). Without it a remote puppet's aimTarget node never moves, so its
    // upper body keeps a stale look direction (the host/AI "180° / aims wrong" bug);
    // it is interpolated like position so the spine tracks smoothly. senderTimeMs is
    // the sender's wall clock — the interpolation timeline (see DecodedSnapshot).
    //
    // yaw is the body mesh's Y rotation in radians (MovementController.meshRoot) —
    // a third-person body never needs pitch/roll replicated, only facing, so one
    // float is enough. Without it every replicated body keeps whatever rotation it
    // had when its local controller was swapped out (round 5 "wrong direction" bug).
    //
    // MSG_SNAPSHOT_BATCH exists because broadcasting one MSG_SNAPSHOT per character
    // per physics tick (round 5 "rate limit exceeded" bug) sends O(characters)
    // messages/sec straight into a per-sender rate limiter sized for O(1) — batching
    // every character into a single count-prefixed frame decouples message *count*
    // from character count, the standard "world-state" broadcast pattern.

    private static final int SNAPSHOT_FLAG_COMBAT       = 1;
    private static final int SNAPSHOT_STANCE_SHIFT      = 1;
    private static final int SNAPSHOT_STANCE_MASK       = 0b111;
    private static final int SNAPSHOT_WEAPON_SLOT_SHIFT = 4;
    private static final int SNAPSHOT_WEAPON_SLOT_MASK  = 0b111;
    // MovementType (IDLE/WALK/SPRINT — 3 values) packs into bits 7-8 of the u16 flags field,
    // so the puppet's locomotion blend gets the exact movement state.
    private static final int SNAPSHOT_MOVE_TYPE_SHIFT   = 7;
    private static final int SNAPSHOT_MOVE_TYPE_MASK    = 0b11;
    // Which swing of a melee weapon's chain this shot was (MeleeItem.attackSteps index). Fire is
    // replicated as STATE, and fireSeq says only THAT a weapon fired -- a puppet reconstructing the
    // step from its own chain cursor guesses, and cannot guess at all for a knife, whose tap/hold is
    // not a chain position. Carried in the SPARE BITS of the existing u16 flags word (combat 1 +
    // stance 3 + slot 3 + move 2 = 9 of 16), so the entry is the same size and
    // NetworkManager.SNAPSHOT_ENTRY_FIXED_BYTES does not move -- the constant and
    // putSnapshotEntry have to agree byte for byte or MTU chunking mis-sizes every frame.
    private static final int SNAPSHOT_FIRE_STEP_SHIFT   = 9;
    private static final int SNAPSHOT_FIRE_STEP_MASK    = 0b111;

    /**
     * The flags word, packed and unpacked in ONE place so a new field cannot silently overlap an
     * existing one — a collision here corrupts a stance or a weapon slot rather than failing.
     * Engine-free (plain ints), which is what lets {@code SnapshotFlagsTest} sweep every combination.
     */
    public static int packSnapshotFlags(boolean combat, int stanceOrdinal, int activeSlotIndex,
            int movementTypeOrdinal, int fireStep) {
        return (combat ? SNAPSHOT_FLAG_COMBAT : 0)
                | ((stanceOrdinal & SNAPSHOT_STANCE_MASK) << SNAPSHOT_STANCE_SHIFT)
                | ((activeSlotIndex & SNAPSHOT_WEAPON_SLOT_MASK) << SNAPSHOT_WEAPON_SLOT_SHIFT)
                | ((movementTypeOrdinal & SNAPSHOT_MOVE_TYPE_MASK) << SNAPSHOT_MOVE_TYPE_SHIFT)
                | ((fireStep & SNAPSHOT_FIRE_STEP_MASK) << SNAPSHOT_FIRE_STEP_SHIFT);
    }

    public static boolean unpackCombat(int flags)    { return (flags & SNAPSHOT_FLAG_COMBAT) != 0; }
    public static int unpackStance(int flags)        { return (flags >> SNAPSHOT_STANCE_SHIFT) & SNAPSHOT_STANCE_MASK; }
    public static int unpackActiveSlot(int flags)    { return (flags >> SNAPSHOT_WEAPON_SLOT_SHIFT) & SNAPSHOT_WEAPON_SLOT_MASK; }
    public static int unpackMovementType(int flags)  { return (flags >> SNAPSHOT_MOVE_TYPE_SHIFT) & SNAPSHOT_MOVE_TYPE_MASK; }
    public static int unpackFireStep(int flags)      { return (flags >> SNAPSHOT_FIRE_STEP_SHIFT) & SNAPSHOT_FIRE_STEP_MASK; }

    public static PackedByteArray encodeSnapshot(int msgType, String characterId, long tick, Vector3 position,
            Vector3 velocity, Vector3 aimTarget, boolean combat, int stanceOrdinal, int activeSlotIndex,
            int movementTypeOrdinal, float yaw, float currentHealth, int senderTimeMs, int fireSeq,
            int activeMagazine, int reloadSeq, int fireStep) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        putSnapshotEntry(buf, characterId, tick, position, velocity, aimTarget, combat, stanceOrdinal,
                activeSlotIndex, movementTypeOrdinal, yaw, currentHealth, senderTimeMs, fireSeq, activeMagazine,
                reloadSeq, fireStep);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedSnapshot decodeSnapshot(StreamPeerBuffer buf) {
        return getSnapshotEntry(buf);
    }

    /**
     * Carrier for a decoded MSG_SNAPSHOT body — replaces the old MultiplayerSynchronizer-replicated
     * field set 1:1. {@code senderTimeMs} is the sender's monotonic wall-clock (milliseconds) at
     * encode time — the interpolation timeline (see {@link com.openworld.net.SnapshotInterpolator}).
     * Using a real timestamp instead of {@code tick/tickRateHz} keeps playback locked to real time
     * even when the sender's physics runs below 60 Hz (two instances on one CPU), which otherwise
     * made the host→client delay grow by seconds. Only differences between a single sender's
     * timestamps are used, so any cross-machine clock offset cancels.
     *
     * <p>{@code fireSeq} is a rolling per-character shot counter (u8 on the wire). Fire is replicated
     * as STATE, not a separate cosmetic message: a receiver plays the muzzle/tracer cue whenever the
     * counter changes between snapshots. This rides the reliable-cadence snapshot stream instead of a
     * droppable one-shot MSG_WEAPON_FIRE, so remote shots stay visible. {@code reloadSeq} is the
     * identical pattern for reloads — a u8 rolling counter so every peer plays the reload animation
     * (a visible "this character is reloading and can't fire yet" tell), drop-resilient because the
     * new value persists across snapshots until the next reload.
     */
    public record DecodedSnapshot(String characterId, long tick, Vector3 position, Vector3 velocity,
            Vector3 aimTarget, boolean combat, int stanceOrdinal, int activeSlotIndex,
            int movementTypeOrdinal, float yaw, float currentHealth, int senderTimeMs, int fireSeq,
            int activeMagazine, int reloadSeq, int fireStep) { }

    /** One tick's worth of every replicated character's state, sent as a single broadcast frame. */
    public static PackedByteArray encodeSnapshotBatch(int msgType, java.util.List<DecodedSnapshot> entries) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.put16(entries.size());
        for (DecodedSnapshot e : entries) {
            putSnapshotEntry(buf, e.characterId(), e.tick(), e.position(), e.velocity(), e.aimTarget(),
                    e.combat(), e.stanceOrdinal(), e.activeSlotIndex(), e.movementTypeOrdinal(),
                    e.yaw(), e.currentHealth(), e.senderTimeMs(), e.fireSeq(), e.activeMagazine(), e.reloadSeq(),
                    e.fireStep());
        }
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static java.util.List<DecodedSnapshot> decodeSnapshotBatch(StreamPeerBuffer buf) {
        int count = buf.getU16();
        java.util.List<DecodedSnapshot> entries = new java.util.ArrayList<>(count);
        for (int i = 0; i < count; i++) entries.add(getSnapshotEntry(buf));
        return entries;
    }

    private static void putSnapshotEntry(StreamPeerBuffer buf, String characterId, long tick, Vector3 position,
            Vector3 velocity, Vector3 aimTarget, boolean combat, int stanceOrdinal, int activeSlotIndex,
            int movementTypeOrdinal, float yaw, float currentHealth, int senderTimeMs, int fireSeq,
            int activeMagazine, int reloadSeq, int fireStep) {
        buf.putUtf8String(characterId);
        buf.put64(tick);
        putVector3(buf, position);
        putVector3(buf, velocity);
        putVector3(buf, aimTarget);
        buf.put16(packSnapshotFlags(combat, stanceOrdinal, activeSlotIndex, movementTypeOrdinal, fireStep));
        buf.putFloat(yaw);
        buf.putFloat(currentHealth);
        buf.put32(senderTimeMs);
        buf.put8(fireSeq & 0xFF);
        // Active-slot magazine (Round 11 fix): lets a puppet track the owner's ammo
        // consumption that no other message carries — notably a thrown grenade, which is
        // neither a hitscan (MSG_SHOT) nor a pickup/drop event. Applied only to puppets
        // (NetworkController), never the owner's own echo, so the owner stays authoritative.
        buf.put16(Math.max(0, Math.min(0xFFFF, activeMagazine)));
        buf.put8(reloadSeq & 0xFF);   // rolling reload counter — puppets play the reload anim on change
    }

    private static DecodedSnapshot getSnapshotEntry(StreamPeerBuffer buf) {
        String characterId = buf.getUtf8String();
        long tick = buf.get64();
        Vector3 position = getVector3(buf);
        Vector3 velocity = getVector3(buf);
        Vector3 aimTarget = getVector3(buf);
        int flags = buf.getU16();
        boolean combat = unpackCombat(flags);
        int stanceOrdinal = unpackStance(flags);
        int activeSlotIndex = unpackActiveSlot(flags);
        int movementTypeOrdinal = unpackMovementType(flags);
        int fireStep = unpackFireStep(flags);
        float yaw = buf.getFloat();
        float currentHealth = buf.getFloat();
        int senderTimeMs = buf.get32();
        int fireSeq = buf.getU8();
        int activeMagazine = buf.getU16();
        int reloadSeq = buf.getU8();
        return new DecodedSnapshot(characterId, tick, position, velocity, aimTarget, combat, stanceOrdinal,
                activeSlotIndex, movementTypeOrdinal, yaw, currentHealth, senderTimeMs, fireSeq, activeMagazine,
                reloadSeq, fireStep);
    }

    // ── MSG_IDENTIFY ──────────────────────────────────────────────────────────
    //
    // [tag u8][persistentPlayerId utf8][assignedPeerId i32]
    //
    // Bidirectional, one shared shape. Client→server sends (persistentPlayerId, 0);
    // server→client replies ("", assignedPeerId). The handler picks the relevant
    // field by isServer().

    public static PackedByteArray encodeIdentify(int msgType, String persistentPlayerId, int assignedPeerId) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(persistentPlayerId);
        buf.put32(assignedPeerId);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedIdentify decodeIdentify(StreamPeerBuffer buf) {
        String persistentPlayerId = buf.getUtf8String();
        int assignedPeerId = buf.get32();
        return new DecodedIdentify(persistentPlayerId, assignedPeerId);
    }

    /** Carrier for a decoded MSG_IDENTIFY body — serves both the client→server request and the server→client reply. */
    public record DecodedIdentify(String persistentPlayerId, int assignedPeerId) { }

    // ── MSG_DAMAGE_REQUEST ────────────────────────────────────────────────────
    //
    // [tag u8][victimCharacterId utf8][finalDamage float][headshot u8]
    // [weaponName utf8][attackerName utf8][attackerFaction utf8]

    public static PackedByteArray encodeDamageRequest(int msgType, String victimCharacterId, String attackerCharacterId,
            int kind, float finalDamage, boolean headshot, String weaponName, String attackerName, String attackerFaction) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(victimCharacterId);
        buf.putUtf8String(attackerCharacterId);
        buf.put8(kind);
        buf.putFloat(finalDamage);
        buf.put8(headshot ? 1 : 0);
        buf.putUtf8String(weaponName);
        buf.putUtf8String(attackerName);
        buf.putUtf8String(attackerFaction);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedDamageRequest decodeDamageRequest(StreamPeerBuffer buf) {
        String victimCharacterId = buf.getUtf8String();
        String attackerCharacterId = buf.getUtf8String();
        int kind = buf.getU8();
        float finalDamage = buf.getFloat();
        boolean headshot = buf.getU8() != 0;
        String weaponName = buf.getUtf8String();
        String attackerName = buf.getUtf8String();
        String attackerFaction = buf.getUtf8String();
        return new DecodedDamageRequest(victimCharacterId, attackerCharacterId, kind, finalDamage, headshot,
                weaponName, attackerName, attackerFaction);
    }

    /**
     * Carrier for a decoded MSG_DAMAGE_REQUEST body. {@code attackerCharacterId} names the entity RESPONSIBLE
     * (the host checks the sender owns it) and {@code kind} is {@code DamageRequestPolicy.Kind}'s ordinal
     * (PLAN.md N2 — the request used to name nobody).
     */
    public record DecodedDamageRequest(String victimCharacterId, String attackerCharacterId, int kind, float finalDamage,
            boolean headshot, String weaponName, String attackerName, String attackerFaction) { }

    // ── MSG_MELEE (client → host, reliable channel 1) ─────────────────────────
    //
    // [tag u8][attackerCharacterId utf8][weaponSlot u8][swingSeq u32][stepIndex u8][origin 3×float][aim 3×float]
    //
    // PLAN.md N2: a client's swing as its INPUTS, sent when the swing's active window opens — where it started
    // (the chest), where it was aimed, which step of the chain. The host runs the sweep on its own copy.

    public static PackedByteArray encodeMelee(int msgType, String attackerCharacterId, int weaponSlot, long swingSeq,
            int stepIndex, Vector3 origin, Vector3 aim) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(attackerCharacterId);
        buf.put8(weaponSlot);
        buf.put32((int) swingSeq);
        buf.put8(stepIndex);
        putVector3(buf, origin);
        putVector3(buf, aim);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedMelee decodeMelee(StreamPeerBuffer buf) {
        String attackerCharacterId = buf.getUtf8String();
        int weaponSlot = buf.getU8();
        long swingSeq = buf.getU32();
        int stepIndex = buf.getU8();
        Vector3 origin = getVector3(buf);
        Vector3 aim = getVector3(buf);
        return new DecodedMelee(attackerCharacterId, weaponSlot, swingSeq, stepIndex, origin, aim);
    }

    /** Carrier for a decoded MSG_MELEE body — one host-resolved swing. */
    public record DecodedMelee(String attackerCharacterId, int weaponSlot, long swingSeq, int stepIndex,
            Vector3 origin, Vector3 aim) { }

    // ── MSG_LAUNCH (client → host, reliable channel 1) ────────────────────────
    //
    // [tag u8][attackerCharacterId utf8][weaponSlot u8][launchSeq u32][origin 3×float][aim 3×float]
    //
    // PLAN.md N4: a client's rocket or grenade as its INPUTS — where it leaves and where it is aimed (a
    // grenade's arc is the weapon's, applied by the host). The host spawns the only projectile that damages.

    public static PackedByteArray encodeLaunch(int msgType, String attackerCharacterId, int weaponSlot, long launchSeq,
            Vector3 origin, Vector3 aim) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(attackerCharacterId);
        buf.put8(weaponSlot);
        buf.put32((int) launchSeq);
        putVector3(buf, origin);
        putVector3(buf, aim);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedLaunch decodeLaunch(StreamPeerBuffer buf) {
        String attackerCharacterId = buf.getUtf8String();
        int weaponSlot = buf.getU8();
        long launchSeq = buf.getU32();
        Vector3 origin = getVector3(buf);
        Vector3 aim = getVector3(buf);
        return new DecodedLaunch(attackerCharacterId, weaponSlot, launchSeq, origin, aim);
    }

    /** Carrier for a decoded MSG_LAUNCH body — one host-spawned projectile. */
    public record DecodedLaunch(String attackerCharacterId, int weaponSlot, long launchSeq, Vector3 origin, Vector3 aim) { }

    // ── MSG_DETONATION (host → all, reliable channel 0) ───────────────────────
    //
    // [tag u8][attackerCharacterId utf8][point 3×float]
    //
    // PLAN.md N4: where the host's projectile exploded. Every peer's cosmetic copy of that attacker's oldest
    // live projectile explodes THERE, so the blast players see is the blast that dealt the damage.

    public static PackedByteArray encodeDetonation(int msgType, String attackerCharacterId, Vector3 point) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(attackerCharacterId);
        putVector3(buf, point);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedDetonation decodeDetonation(StreamPeerBuffer buf) {
        String attackerCharacterId = buf.getUtf8String();
        Vector3 point = getVector3(buf);
        return new DecodedDetonation(attackerCharacterId, point);
    }

    public record DecodedDetonation(String attackerCharacterId, Vector3 point) { }

    // ── MSG_DAMAGE_BROADCAST ──────────────────────────────────────────────────
    //
    // [tag u8][victimCharacterId utf8][damage float][hasSource u8][source 3×float]
    //
    // source = the attacker's world position (shooter / blast center), so the victim's peer can drive
    // the HUD damage-direction indicator. hasSource = 0 for sourceless damage (fall/world); the three
    // floats are still present (zero) to keep the layout fixed.

    public static PackedByteArray encodeDamageBroadcast(int msgType, String victimCharacterId, float damage,
            boolean hasSource, Vector3 source, String attackerCharacterId, boolean headshot, boolean killed) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(victimCharacterId);
        buf.putFloat(damage);
        buf.put8(hasSource ? 1 : 0);
        putVector3(buf, hasSource && source != null ? source : Vector3.Companion.getZERO());
        // 2.8 item 9: who dealt it, so that player's peer can draw a confirmed hit marker.
        buf.putUtf8String(attackerCharacterId == null ? "" : attackerCharacterId);
        buf.put8((headshot ? 1 : 0) | (killed ? 2 : 0));
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedDamageBroadcast decodeDamageBroadcast(StreamPeerBuffer buf) {
        String victimCharacterId = buf.getUtf8String();
        float damage = buf.getFloat();
        boolean hasSource = buf.getU8() != 0;
        Vector3 source = getVector3(buf);
        String attacker = buf.getUtf8String();
        int flags = buf.getU8();
        return new DecodedDamageBroadcast(victimCharacterId, damage, hasSource, source, attacker,
                (flags & 1) != 0, (flags & 2) != 0);
    }

    /** Carrier for a decoded MSG_DAMAGE_BROADCAST body — the cosmetic "you got hit" cue (+ attacker source) for non-authority peers. */
    public record DecodedDamageBroadcast(String victimCharacterId, float damage, boolean hasSource, Vector3 source,
            String attackerCharacterId, boolean headshot, boolean killed) { }

    // ── MSG_SHOT (client → host, host-resolved bullets) ───────────────────────
    //
    // [tag u8][shooterCharacterId utf8][weaponSlot u8][shotSeq u32][origin 3×float][aim 3×float][spreadDeg float]
    //
    // ONE message per trigger pull (PLAN.md N1). The owning client predicts the cosmetic shot locally
    // but applies no damage; it sends the pull's INPUTS — the origin (muzzle), the PRE-spread aim, the
    // full cone angle and its shot counter — and the host validates them (ShotValidationPolicy) and
    // regenerates every pellet from seed(shooterId, shotSeq) with SpreadPattern, exactly as the client
    // did. The slot picks the host copy's weapon, whose damage and pellet count are used — never the
    // client's. Reliable on channel 1, so a lost shot neither vanishes nor head-of-line-blocks the
    // damage/pickup/spawn traffic on channel 0.

    public static PackedByteArray encodeShot(int msgType, String shooterCharacterId, int weaponSlot, long shotSeq,
            Vector3 origin, Vector3 aim, float spreadDeg) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(shooterCharacterId);
        buf.put8(weaponSlot);
        buf.put32((int) shotSeq);
        putVector3(buf, origin);
        putVector3(buf, aim);
        buf.putFloat(spreadDeg);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedShot decodeShot(StreamPeerBuffer buf) {
        String shooterCharacterId = buf.getUtf8String();
        int weaponSlot = buf.getU8();
        long shotSeq = buf.getU32();
        Vector3 origin = getVector3(buf);
        Vector3 aim = getVector3(buf);
        float spreadDeg = buf.getFloat();
        return new DecodedShot(shooterCharacterId, weaponSlot, shotSeq, origin, aim, spreadDeg);
    }

    /** Carrier for a decoded MSG_SHOT body — one host-resolved trigger pull. */
    public record DecodedShot(String shooterCharacterId, int weaponSlot, long shotSeq, Vector3 origin, Vector3 aim,
            float spreadDeg) { }

    // ── MSG_SHOT_RESULT_BATCH (host → peers, cosmetic, unreliable) ────────────
    //
    // [tag u8][count u16] then per entry:
    //   [shooterCharacterId utf8][weaponSlot u8][shotSeq u32][pellets u8]
    //   per pellet: [kind u8][end 3×float] and, when kind > 0, [normal 3×float]
    //   kind 0 = miss (end = where the tracer stops), kind k > 0 = hit on SurfaceType ordinal k-1.
    //
    // PLAN.md N1b: what a host-resolved pull actually hit, so peers other than the shooter draw the
    // real tracers and impacts instead of one tracer toward the replicated aim point. Cosmetic only —
    // damage never rides it — so it is unreliable on channel 3 and a lost one falls back to the
    // puppet's aim tracer (FirearmItem.playRemoteFireCue).

    /** One pellet of a resolved pull: {@code kind} 0 = miss, else SurfaceType ordinal + 1. */
    public record PelletResult(int kind, Vector3 end, Vector3 normal) { }

    /** One resolved pull. */
    public record ShotResult(String shooterCharacterId, int weaponSlot, long shotSeq, java.util.List<PelletResult> pellets) {
        /** Encoded size, for MTU chunking. */
        public int wireBytes() {
            int b = 4 + shooterCharacterId.getBytes(java.nio.charset.StandardCharsets.UTF_8).length + 1 + 4 + 1;
            for (PelletResult p : pellets) b += 1 + 12 + (p.kind() > 0 ? 12 : 0);
            return b;
        }
    }

    public static PackedByteArray encodeShotResultBatch(int msgType, java.util.List<ShotResult> results) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.put16(results.size());
        for (ShotResult r : results) {
            buf.putUtf8String(r.shooterCharacterId());
            buf.put8(r.weaponSlot());
            buf.put32((int) r.shotSeq());
            buf.put8(Math.min(255, r.pellets().size()));
            int n = 0;
            for (PelletResult p : r.pellets()) {
                if (n++ >= 255) break;
                buf.put8(p.kind());
                putVector3(buf, p.end());
                if (p.kind() > 0) putVector3(buf, p.normal());
            }
        }
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static java.util.List<ShotResult> decodeShotResultBatch(StreamPeerBuffer buf) {
        int count = buf.getU16();
        java.util.List<ShotResult> out = new java.util.ArrayList<>(Math.min(count, 64));
        for (int i = 0; i < count; i++) {
            String id = buf.getUtf8String();
            int slot = buf.getU8();
            long seq = buf.getU32();
            int pellets = buf.getU8();
            java.util.List<PelletResult> ps = new java.util.ArrayList<>(pellets);
            for (int k = 0; k < pellets; k++) {
                int kind = buf.getU8();
                Vector3 end = getVector3(buf);
                Vector3 normal = kind > 0 ? getVector3(buf) : null;
                ps.add(new PelletResult(kind, end, normal));
            }
            out.add(new ShotResult(id, slot, seq, ps));
        }
        return out;
    }

    // ── MSG_OWNERSHIP (ownership migration, reliable) ─────────────────────────
    //
    // [tag u8][characterId utf8][newOwnerPeerId i32]
    //
    // Reassigns which peer is authoritative for an entity (Round 8 Step 3 — vehicle driver-authority).
    // Bidirectional: a client sends it to the host to request ownership (e.g. on entering a vehicle);
    // the host validates, applies, and re-broadcasts the authoritative result to every peer so all
    // copies agree on who simulates the entity. ownerPeerId lives on the shared CharacterInfo that
    // Controller.isAuthority() already keys off, so once it migrates the existing sim/replication
    // split follows automatically.

    public static PackedByteArray encodeOwnership(int msgType, String characterId, int newOwnerPeerId) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(characterId);
        buf.put32(newOwnerPeerId);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedOwnership decodeOwnership(StreamPeerBuffer buf) {
        String characterId = buf.getUtf8String();
        int newOwnerPeerId = buf.get32();
        return new DecodedOwnership(characterId, newOwnerPeerId);
    }

    /** Carrier for a decoded MSG_OWNERSHIP body — the entity whose authority is migrating + its new owner peer. */
    public record DecodedOwnership(String characterId, int newOwnerPeerId) { }

    // ── MSG_WAYPOINT (I5 — owner→host→all reliable GPS waypoint set/clear) ────────────────────────
    public static PackedByteArray encodeWaypoint(int msgType, String characterId, boolean hasWaypoint,
            Vector3 pos) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(characterId);
        buf.put8(hasWaypoint ? 1 : 0);
        putVector3(buf, hasWaypoint && pos != null ? pos : Vector3.Companion.getZERO());
        return buf.getDataArray();
    }

    public static DecodedWaypoint decodeWaypoint(StreamPeerBuffer buf) {
        String characterId = buf.getUtf8String();
        boolean hasWaypoint = buf.getU8() != 0;
        Vector3 pos = getVector3(buf);
        return new DecodedWaypoint(characterId, hasWaypoint, pos);
    }

    /** Carrier for a decoded MSG_WAYPOINT body — whose waypoint, whether it's set, and where. */
    public record DecodedWaypoint(String characterId, boolean hasWaypoint, Vector3 position) { }

    // ── MSG_WORLD_EVENT (host → all, reliable world-state seam) ───────────────
    //
    // [tag u8][eventType u8][key utf8][value float][argCount u8][arg utf8]...
    //
    // The host-authoritative seam for discrete, reliable world state the snapshot stream isn't
    // suited to — doors opening, mission/story beats, pickup spawns/consumption, the spawn director.
    // Generic on purpose: {@code eventType} selects the meaning, {@code key} names the target (a door
    // id, mission id, pickup id…), {@code value} carries an optional scalar (a state, an amount), and
    // the trailing {@code args} string list carries any extra textual payload an event needs (e.g. a
    // mission's objectiveType / winningFaction / outcomeVariant / fail reason) without minting a new
    // message type per feature. The host owns the truth and broadcasts; clients apply. Specific events
    // are added by GameManager as features need them — the scaffold (Round 7/8 Step 4).

    /** Hard cap on the args string list — bounds isValidWorldEvent against a hostile/garbage frame. */
    public static final int MAX_WORLD_EVENT_ARGS = 8;

    public static PackedByteArray encodeWorldEvent(int msgType, int eventType, String key, float value,
            java.util.List<String> args) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.put8(eventType);
        buf.putUtf8String(key);
        buf.putFloat(value);
        buf.put8(args.size());
        for (String a : args) buf.putUtf8String(a == null ? "" : a);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedWorldEvent decodeWorldEvent(StreamPeerBuffer buf) {
        int eventType = buf.getU8();
        String key = buf.getUtf8String();
        float value = buf.getFloat();
        int count = buf.getU8();
        java.util.List<String> args = new java.util.ArrayList<>(count);
        for (int i = 0; i < count; i++) args.add(buf.getUtf8String());
        return new DecodedWorldEvent(eventType, key, value, args);
    }

    /** Carrier for a decoded MSG_WORLD_EVENT body — the generic host-authoritative world-state event. */
    public record DecodedWorldEvent(int eventType, String key, float value, java.util.List<String> args) { }

    // ── MSG_SPAWN ─────────────────────────────────────────────────────────────
    //
    // [tag u8][characterId utf8][displayName utf8][faction utf8][sceneSelector u8]
    // [position 3×float][ownerPeerId i32]
    //
    // sceneSelector is a small bounded enum (SCENE_PLAYER/SCENE_AI) rather than an
    // arbitrary res:// path string — the wire payload never carries a scene path, so
    // a malicious/buggy peer can never make a client load an attacker-chosen resource.
    // Folds in the previously-approved G3 MultiplayerSpawner follow-up — see
    // NETWORK_REWRITE_PLAN.md Phase 7.

    public static final int SCENE_PLAYER = 0;
    public static final int SCENE_AI     = 1;

    public static PackedByteArray encodeSpawn(int msgType, String characterId, String displayName,
            String faction, int sceneSelector, Vector3 position, int ownerPeerId) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(characterId);
        buf.putUtf8String(displayName);
        buf.putUtf8String(faction);
        buf.put8(sceneSelector);
        putVector3(buf, position);
        buf.put32(ownerPeerId);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedSpawn decodeSpawn(StreamPeerBuffer buf) {
        String characterId = buf.getUtf8String();
        String displayName = buf.getUtf8String();
        String faction = buf.getUtf8String();
        int sceneSelector = buf.getU8();
        Vector3 position = getVector3(buf);
        int ownerPeerId = buf.get32();
        return new DecodedSpawn(characterId, displayName, faction, sceneSelector, position, ownerPeerId);
    }

    /** Carrier for a decoded MSG_SPAWN body — matches GameManager.spawnReplicatedCharacter's reconstruction shape. */
    public record DecodedSpawn(String characterId, String displayName, String faction,
            int sceneSelector, Vector3 position, int ownerPeerId) { }

    // ── MSG_PICKUP_REQUEST (client → host) / MSG_PICKUP_TAKEN (host → all) ────
    //
    // REQUEST: [tag u8][pickupId utf8][characterId utf8]
    // TAKEN:   [tag u8][pickupId utf8][characterId utf8][magazine i32][reserve i32]
    //
    // Host-arbitrated world pickups: the peer that OWNS a character detects the overlap
    // (Pickup's owner-gate) and either collects locally + broadcasts TAKEN (host-owned
    // bodies) or sends REQUEST and waits for the TAKEN echo (client-owned bodies). Every
    // peer executes the same collect path on TAKEN, so all WeaponController inventories
    // stay mirrored and snapshot activeSlotIndex always references a weapon that exists.
    // TAKEN carries the item's magazine/reserve at take time so the mirrored item state
    // is exact on every peer. Reliable channel 0 — a dropped pickup event would desync
    // inventories permanently.

    public static PackedByteArray encodePickupRequest(int msgType, String pickupId, String characterId) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(pickupId);
        buf.putUtf8String(characterId);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedPickupRequest decodePickupRequest(StreamPeerBuffer buf) {
        String pickupId = buf.getUtf8String();
        String characterId = buf.getUtf8String();
        return new DecodedPickupRequest(pickupId, characterId);
    }

    /** Carrier for a decoded MSG_PICKUP_REQUEST body — a client asking the host to grant a pickup. */
    public record DecodedPickupRequest(String pickupId, String characterId) { }

    public static PackedByteArray encodePickupTaken(int msgType, String pickupId, String characterId,
            int magazine, int reserve) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(pickupId);
        buf.putUtf8String(characterId);
        buf.put32(magazine);
        buf.put32(reserve);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedPickupTaken decodePickupTaken(StreamPeerBuffer buf) {
        String pickupId = buf.getUtf8String();
        String characterId = buf.getUtf8String();
        int magazine = buf.get32();
        int reserve = buf.get32();
        return new DecodedPickupTaken(pickupId, characterId, magazine, reserve);
    }

    /** Carrier for a decoded MSG_PICKUP_TAKEN body — the host-confirmed pickup every peer applies. */
    public record DecodedPickupTaken(String pickupId, String characterId, int magazine, int reserve) { }

    // ── MSG_WEAPON_SWITCH (owner → host → all) ────────────────────────────────
    //
    // [tag u8][characterId utf8][targetSlot u8]
    //
    // The ordered equip event (G4-1): emitted the instant the owner *begins* a weapon switch,
    // not the post-animation slot value. Puppets snap to targetSlot and time-align their cosmetic
    // draw immediately, so a remote switch lands as promptly as the owner's — no extra draw-animation
    // of lag. Reliable channel 0; the per-tick snapshot slot (now the *target* during a transition)
    // is the drop-heal backstop. No fire timing rides here — the puppet gates its own fire cue on the
    // local draw window (see WeaponController.applyReplicatedWeaponSlot / playRemoteFireCue).

    public static PackedByteArray encodeWeaponSwitch(int msgType, String characterId, int targetSlot) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(characterId);
        buf.put8(targetSlot & 0xFF);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedWeaponSwitch decodeWeaponSwitch(StreamPeerBuffer buf) {
        String characterId = buf.getUtf8String();
        int targetSlot = buf.getU8();
        return new DecodedWeaponSwitch(characterId, targetSlot);
    }

    /** Carrier for a decoded MSG_WEAPON_SWITCH body — the ordered equip-start event every peer applies. */
    public record DecodedWeaponSwitch(String characterId, int targetSlot) { }

    // ── MSG_WEAPON_DROPPED (owner → host → all) ───────────────────────────────
    //
    // [tag u8][characterId utf8][slot u8][oldPickupId utf8][newPickupId utf8]
    // [position 3×float][impulse 3×float][magazine i32][reserve i32]
    //
    // A drop is owner-originated (manual drop / equip displacement) or host-originated
    // (death scatter — Character.onDied only runs where health is authoritative). The event
    // carries the originator's computed spawn position AND impulse because the death scatter
    // is randomized (GD.randf) — peers must apply the rolled result, never re-roll. Every
    // peer takes the item out of the character's slot and returns it to the world at the
    // carried transform; all peers ADOPT newPickupId so item identities converge even for
    // weapons whose path-derived ids differed per peer (e.g. AI scene loadouts). oldPickupId
    // is the fallback key for the displacement race, where the applying peer's own equip
    // already self-dropped the item before this event arrived (see
    // WeaponController.applyReplicatedDrop / GameManager.applyReplicatedDrop).

    public static PackedByteArray encodeWeaponDropped(int msgType, String characterId, int slot,
            String oldPickupId, String newPickupId, Vector3 position, Vector3 impulse,
            int magazine, int reserve) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(characterId);
        buf.put8(slot);
        buf.putUtf8String(oldPickupId);
        buf.putUtf8String(newPickupId);
        putVector3(buf, position);
        putVector3(buf, impulse);
        buf.put32(magazine);
        buf.put32(reserve);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedWeaponDropped decodeWeaponDropped(StreamPeerBuffer buf) {
        String characterId = buf.getUtf8String();
        int slot = buf.getU8();
        String oldPickupId = buf.getUtf8String();
        String newPickupId = buf.getUtf8String();
        Vector3 position = getVector3(buf);
        Vector3 impulse = getVector3(buf);
        int magazine = buf.get32();
        int reserve = buf.get32();
        return new DecodedWeaponDropped(characterId, slot, oldPickupId, newPickupId, position, impulse, magazine, reserve);
    }

    /** Carrier for a decoded MSG_WEAPON_DROPPED body — the replicated weapon-to-world event. */
    public record DecodedWeaponDropped(String characterId, int slot, String oldPickupId,
            String newPickupId, Vector3 position, Vector3 impulse, int magazine, int reserve) { }

    // ── MSG_ELIMINATION (host → all, reliable death/kill event — Round 11 N2) ──
    //
    // [tag u8][victimCharacterId utf8][victimName utf8][victimFaction utf8]
    // [attackerName utf8][attackerFaction utf8][weaponName utf8][headshot u8]
    //
    // Death was previously only inferable by non-authority peers from the unreliable
    // health==0 snapshot stream (DeathLatch). This is the reliable, ordered complement the
    // authority broadcasts from Health.applyDamage: receivers force the victim's death
    // (latch + visuals) and re-emit characterEliminated/characterDied on their local
    // EventBus so the kill feed, mission progress, and a client's own death sequence work
    // off-host. No weaponIcon — HUD-local concern, never crosses the wire (same rule as
    // MSG_DAMAGE_REQUEST).

    public static PackedByteArray encodeElimination(int msgType, String victimCharacterId, String victimName,
            String victimFaction, String attackerName, String attackerFaction, String weaponName, boolean headshot) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(victimCharacterId);
        buf.putUtf8String(victimName);
        buf.putUtf8String(victimFaction);
        buf.putUtf8String(attackerName);
        buf.putUtf8String(attackerFaction);
        buf.putUtf8String(weaponName);
        buf.put8(headshot ? 1 : 0);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedElimination decodeElimination(StreamPeerBuffer buf) {
        String victimCharacterId = buf.getUtf8String();
        String victimName = buf.getUtf8String();
        String victimFaction = buf.getUtf8String();
        String attackerName = buf.getUtf8String();
        String attackerFaction = buf.getUtf8String();
        String weaponName = buf.getUtf8String();
        boolean headshot = buf.getU8() != 0;
        return new DecodedElimination(victimCharacterId, victimName, victimFaction,
                attackerName, attackerFaction, weaponName, headshot);
    }

    /** Carrier for a decoded MSG_ELIMINATION body — the authoritative kill event every peer applies. */
    public record DecodedElimination(String victimCharacterId, String victimName, String victimFaction,
            String attackerName, String attackerFaction, String weaponName, boolean headshot) { }

    // ── MSG_INVENTORY (host → all, per-character slot manifest — Round 11 N2) ──
    //
    // [tag u8][characterId utf8][entryCount u8]
    //   per entry: [slot u8][weaponId utf8][scenePath utf8][pickupId utf8][magazine i32][reserve i32]
    //
    // The state-sync backstop for the event-replicated inventory: only OCCUPIED slots are
    // listed (slot 0/fist never replicates — it is permanent scene furniture); the receiver
    // clears any slot not listed. scenePath lets a receiver materialise a weapon it never
    // saw an event for (e.g. an AI's runtime-equipped rifle); pickupId lets it adopt the
    // host's identity for that item — preferring to consume a matching local world pickup
    // over instantiating a duplicate. Receivers must validate scenePath against the
    // res://…tscn shape before loading (see NetworkManager.isValidInventory).

    public static PackedByteArray encodeInventory(int msgType, String characterId,
            java.util.List<InventorySlotEntry> entries) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(characterId);
        buf.put8(entries.size());
        for (InventorySlotEntry e : entries) {
            buf.put8(e.slot());
            buf.putUtf8String(e.weaponId());
            buf.putUtf8String(e.scenePath());
            buf.putUtf8String(e.pickupId());
            buf.put32(e.magazine());
            buf.put32(e.reserve());
        }
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedInventory decodeInventory(StreamPeerBuffer buf) {
        String characterId = buf.getUtf8String();
        int count = buf.getU8();
        java.util.List<InventorySlotEntry> entries = new java.util.ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            int slot = buf.getU8();
            String weaponId = buf.getUtf8String();
            String scenePath = buf.getUtf8String();
            String pickupId = buf.getUtf8String();
            int magazine = buf.get32();
            int reserve = buf.get32();
            entries.add(new InventorySlotEntry(slot, weaponId, scenePath, pickupId, magazine, reserve));
        }
        return new DecodedInventory(characterId, entries);
    }

    /** One occupied weapon slot inside a MSG_INVENTORY manifest. */
    public record InventorySlotEntry(int slot, String weaponId, String scenePath, String pickupId,
            int magazine, int reserve) { }

    /** Carrier for a decoded MSG_INVENTORY body — one character's authoritative slot manifest. */
    public record DecodedInventory(String characterId, java.util.List<InventorySlotEntry> entries) { }

    // ── MSG_DESPAWN ───────────────────────────────────────────────────────────
    //
    // [tag u8][characterId utf8]

    public static PackedByteArray encodeDespawn(int msgType, String characterId) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(characterId);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedDespawn decodeDespawn(StreamPeerBuffer buf) {
        return new DecodedDespawn(buf.getUtf8String());
    }

    /** Carrier for a decoded MSG_DESPAWN body — characterId to queueFree() on receipt. */
    public record DecodedDespawn(String characterId) { }

    // ── MSG_VEHICLE_SNAPSHOT / MSG_VEHICLE_SNAPSHOT_BATCH (Round 11 N3) ──────
    //
    // Entry: [vehicleId utf8][senderTimeMs i32][pos 3f][orientation quat 4f]
    //        [linVel 3f][angVel 3f][steerAngle f][throttle f]
    //        [flags u8: bit0 handbrake, bit1 brake, bit2 slipping, bits3-6 flatMask][health f][fireSeq u8]
    //
    // A parallel entry shape to the character snapshot rather than a kind-byte inside it:
    // vehicles need the FULL orientation (they roll and pitch — the character entry's one
    // yaw float can't represent a car on a ramp) plus angular velocity for orientation
    // dead-reckoning, and wheel-appearance state so puppets replay what the authority
    // shows; they have none of the character's stance/combat/aim fields. No tick —
    // vehicles carry no tick counter, and the near-time interpolator orders/projects on
    // senderTimeMs alone. Same single-vs-batch split as MSG_SNAPSHOT/MSG_SNAPSHOT_BATCH:
    // the driving client reports its one vehicle upstream as a single, the host
    // re-broadcasts everything as a batch.
    //
    // steerAngle is the ACTUAL steer-wheel Y rotation in radians (not the raw ±1 input
    // rate): replicating the input would make puppets re-integrate it and drift from the
    // authority's wheel pose; the angle replays exactly. slipping mirrors the authority's
    // drift/skid state so puppets emit the same skid marks.

    private static final int VEHICLE_FLAG_HANDBRAKE = 1;
    private static final int VEHICLE_FLAG_BRAKE     = 2;
    private static final int VEHICLE_FLAG_SLIPPING  = 4;
    // Bits 3–6: per-wheel flat-tire mask (wheel index = scene child order, peer-identical).
    // Spare bits in the existing flags u8 — the entry byte count is unchanged.
    private static final int VEHICLE_FLAG_FLAT_SHIFT = 3;
    private static final int VEHICLE_FLAG_FLAT_MASK  = 0xF;

    /** Fixed bytes per vehicle entry beyond the vehicleId text: u32 string length + i32 time + 13 floats + flags u8 + health float + fireSeq u8 — see putVehicleSnapshotEntry. */
    public static final int VEHICLE_SNAPSHOT_ENTRY_FIXED_BYTES = 4 + 4 + 13 * 4 + 1 + 4 + 1;

    public static PackedByteArray encodeVehicleSnapshot(int msgType, DecodedVehicleSnapshot entry) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        putVehicleSnapshotEntry(buf, entry);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedVehicleSnapshot decodeVehicleSnapshot(StreamPeerBuffer buf) {
        return getVehicleSnapshotEntry(buf);
    }

    public static PackedByteArray encodeVehicleSnapshotBatch(int msgType, java.util.List<DecodedVehicleSnapshot> entries) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.put16(entries.size());
        for (DecodedVehicleSnapshot e : entries) putVehicleSnapshotEntry(buf, e);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static java.util.List<DecodedVehicleSnapshot> decodeVehicleSnapshotBatch(StreamPeerBuffer buf) {
        int count = buf.getU16();
        java.util.List<DecodedVehicleSnapshot> entries = new java.util.ArrayList<>(count);
        for (int i = 0; i < count; i++) entries.add(getVehicleSnapshotEntry(buf));
        return entries;
    }

    private static void putVehicleSnapshotEntry(StreamPeerBuffer buf, DecodedVehicleSnapshot e) {
        buf.putUtf8String(e.vehicleId());
        buf.put32(e.senderTimeMs());
        putVector3(buf, e.position());
        Quaternion q = e.orientation() != null ? e.orientation() : new Quaternion();
        buf.putFloat((float) q.getX());
        buf.putFloat((float) q.getY());
        buf.putFloat((float) q.getZ());
        buf.putFloat((float) q.getW());
        putVector3(buf, e.linearVelocity());
        putVector3(buf, e.angularVelocity());
        buf.putFloat(e.steerAngle());
        buf.putFloat(e.throttle());
        buf.put8((e.handbrake() ? VEHICLE_FLAG_HANDBRAKE : 0)
                | (e.brake() ? VEHICLE_FLAG_BRAKE : 0)
                | (e.slipping() ? VEHICLE_FLAG_SLIPPING : 0)
                | ((e.flatMask() & VEHICLE_FLAG_FLAT_MASK) << VEHICLE_FLAG_FLAT_SHIFT));
        buf.putFloat(e.health());
        buf.put8(e.fireSeq() & 0xFF);
    }

    private static DecodedVehicleSnapshot getVehicleSnapshotEntry(StreamPeerBuffer buf) {
        String vehicleId = buf.getUtf8String();
        int senderTimeMs = buf.get32();
        Vector3 position = getVector3(buf);
        float qx = buf.getFloat();
        float qy = buf.getFloat();
        float qz = buf.getFloat();
        float qw = buf.getFloat();
        Vector3 linearVelocity = getVector3(buf);
        Vector3 angularVelocity = getVector3(buf);
        float steerAngle = buf.getFloat();
        float throttle = buf.getFloat();
        int flags = buf.getU8();
        float health = buf.getFloat();
        int fireSeq = buf.getU8();
        return new DecodedVehicleSnapshot(vehicleId, senderTimeMs, position,
                new Quaternion(qx, qy, qz, qw), linearVelocity, angularVelocity, steerAngle, throttle,
                (flags & VEHICLE_FLAG_HANDBRAKE) != 0, (flags & VEHICLE_FLAG_BRAKE) != 0,
                (flags & VEHICLE_FLAG_SLIPPING) != 0,
                (flags >> VEHICLE_FLAG_FLAT_SHIFT) & VEHICLE_FLAG_FLAT_MASK, health, fireSeq);
    }

    /** Carrier for one vehicle's replicated state — see the wire-layout comment above. */
    public record DecodedVehicleSnapshot(String vehicleId, int senderTimeMs, Vector3 position,
            Quaternion orientation, Vector3 linearVelocity, Vector3 angularVelocity,
            float steerAngle, float throttle, boolean handbrake, boolean brake, boolean slipping,
            int flatMask, float health, int fireSeq) { }

    // ── MSG_VEHICLE_SEAT_REQUEST / MSG_VEHICLE_OCCUPANCY (Round 11 N3) ────────
    //
    // Request:   [tag u8][vehicleId utf8][characterId utf8][entering u8][seatIndex u8]   client → host
    // Occupancy: [tag u8][vehicleId utf8][occupantCharacterId utf8][ownerPeerId i32][entering u8][seatIndex u8]   host → all
    //
    // seatIndex (multi-seat): 255 = SEAT_AUTO on a request ("host picks" — the one enter key);
    // occupancy always carries the host-resolved concrete seat. One seat per message — the
    // ~1 Hz sweep and the late-join baseline iterate every seat.
    //
    // Host-arbitrated enter/exit, mirroring the pickup grant: the client only REQUESTS;
    // the host validates (VehicleSeatPolicy) and broadcasts the authoritative occupancy,
    // which every peer (including the requester) applies by running tryEnter/tryExit
    // locally. ownerPeerId rides INSIDE the occupancy event so the locomotion-authority
    // migration is atomic with the seat change — no cross-message ordering hazard.
    // occupantCharacterId is empty on an exit broadcast (seat now vacant).

    public static PackedByteArray encodeVehicleSeatRequest(int msgType, String vehicleId,
            String characterId, boolean entering, int seatIndex) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(vehicleId);
        buf.putUtf8String(characterId);
        buf.put8(entering ? 1 : 0);
        buf.put8(seatIndex & 0xFF);   // 255 = SEAT_AUTO (host picks); exit resolves by characterId
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedVehicleSeatRequest decodeVehicleSeatRequest(StreamPeerBuffer buf) {
        String vehicleId = buf.getUtf8String();
        String characterId = buf.getUtf8String();
        boolean entering = buf.getU8() != 0;
        int seatIndex = buf.getU8();
        return new DecodedVehicleSeatRequest(vehicleId, characterId, entering, seatIndex);
    }

    /** Carrier for a decoded MSG_VEHICLE_SEAT_REQUEST — a client asking to (un)seat its character. */
    public record DecodedVehicleSeatRequest(String vehicleId, String characterId, boolean entering,
            int seatIndex) { }

    public static PackedByteArray encodeVehicleOccupancy(int msgType, String vehicleId,
            String occupantCharacterId, int ownerPeerId, boolean entering, int seatIndex) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(vehicleId);
        buf.putUtf8String(occupantCharacterId);
        buf.put32(ownerPeerId);
        buf.put8(entering ? 1 : 0);
        buf.put8(seatIndex & 0xFF);   // concrete seat (host-resolved), one seat per message
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedVehicleOccupancy decodeVehicleOccupancy(StreamPeerBuffer buf) {
        String vehicleId = buf.getUtf8String();
        String occupantCharacterId = buf.getUtf8String();
        int ownerPeerId = buf.get32();
        boolean entering = buf.getU8() != 0;
        int seatIndex = buf.getU8();
        return new DecodedVehicleOccupancy(vehicleId, occupantCharacterId, ownerPeerId, entering, seatIndex);
    }

    /** Carrier for a decoded MSG_VEHICLE_OCCUPANCY — the host's authoritative seat state (occupant empty = vacant). */
    public record DecodedVehicleOccupancy(String vehicleId, String occupantCharacterId,
            int ownerPeerId, boolean entering, int seatIndex) { }

    // ── MSG_VEHICLE_SPAWN (host → all, reliable — streamed ambient traffic, I3b) ──
    //
    // [tag u8][vehicleId utf8][faction utf8][position 3×float][yaw float][ownerPeerId i32][ephemeral u8]
    //
    // The counterpart of MSG_SPAWN for replicated vehicles. ownerPeerId is the host (for ambient
    // traffic and idle scene cars), so a client resolves isAuthorityFor=false and attaches a
    // VehicleNetworkController; the existing MSG_VEHICLE_SNAPSHOT_BATCH then drives it. yaw is the
    // initial facing (the snapshot corrects orientation within a tick).
    //
    // `ephemeral` is the persistent/ephemeral split (PLAN.md netcode WS3 fix): true ONLY for
    // runtime-streamed ambient traffic (ZoneManager), which the client tags into STREAMED_GROUP
    // so the ghost-reconcile may free it on a snapshot-timeout (missed despawn cleanup). Scene-placed
    // / player-driven vehicles re-supplied via the late-join baseline are ephemeral=false: they are
    // NEVER reconcile-eligible, so a momentary snapshot gap (e.g. traffic-volume pressure) can never
    // despawn a persistent car out from under a non-driving peer. The scene is the single bounded
    // Vehicle.tscn (no wire path, same anti-arbitrary-resource rationale as MSG_SPAWN's sceneSelector).

    public static PackedByteArray encodeVehicleSpawn(int msgType, String vehicleId, String faction,
            Vector3 position, float yaw, int ownerPeerId, boolean ephemeral) {
        StreamPeerBuffer buf = new StreamPeerBuffer();
        buf.put8(msgType);
        buf.putUtf8String(vehicleId);
        buf.putUtf8String(faction);
        putVector3(buf, position);
        buf.putFloat(yaw);
        buf.put32(ownerPeerId);
        buf.put8(ephemeral ? 1 : 0);
        return buf.getDataArray();
    }

    /** Decodes the body following the tag byte. Caller must have already consumed it. */
    public static DecodedVehicleSpawn decodeVehicleSpawn(StreamPeerBuffer buf) {
        String vehicleId = buf.getUtf8String();
        String faction = buf.getUtf8String();
        Vector3 position = getVector3(buf);
        float yaw = buf.getFloat();
        int ownerPeerId = buf.get32();
        boolean ephemeral = buf.get8() != 0;
        return new DecodedVehicleSpawn(vehicleId, faction, position, yaw, ownerPeerId, ephemeral);
    }

    /** Carrier for a decoded MSG_VEHICLE_SPAWN — matches GameManager.spawnReplicatedVehicle's reconstruction shape. */
    public record DecodedVehicleSpawn(String vehicleId, String faction, Vector3 position,
            float yaw, int ownerPeerId, boolean ephemeral) { }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static void putVector3(StreamPeerBuffer buf, Vector3 v) {
        buf.putFloat(v != null ? (float) v.getX() : 0f);
        buf.putFloat(v != null ? (float) v.getY() : 0f);
        buf.putFloat(v != null ? (float) v.getZ() : 0f);
    }

    private static Vector3 getVector3(StreamPeerBuffer buf) {
        float x = buf.getFloat();
        float y = buf.getFloat();
        float z = buf.getFloat();
        return new Vector3(x, y, z);
    }
}
