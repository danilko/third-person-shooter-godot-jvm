package com.openworld.weapon;

import godot.annotation.Script;

/**
 * Heavy axe melee weapon (MW2).
 * All stats set in MW2.tscn: 80 dmg, 2.5 m reach, 30° cone, 1.5/s.
 * Extends MeleeItem directly — no charge mechanic (contrast with KnifeItem).
 * Tradeoff vs MW1 knife: longer reach and higher per-swing damage at a slower rate.
 */
@Script(className = "AxeItem")
public class AxeItem extends MeleeItem {
}
