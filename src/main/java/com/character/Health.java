package com.character;

import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.annotation.RegisterSignal;
import godot.api.Node;
import godot.core.Signal0;
import godot.core.Signal1;
import godot.core.StringName;

@RegisterClass(className = "Health")
public class Health extends Node {

    @Export
    @RegisterProperty
    public float maxHealth = 100.0f;

    private float currentHealth;

    @RegisterSignal
    public final Signal1<Float> damaged = new Signal1<>(this, new StringName("damaged"));

    @RegisterSignal
    public final Signal0 died = new Signal0(this, new StringName("died"));

    @RegisterFunction
    @Override
    public void _ready() {
        currentHealth = maxHealth;
    }

    @RegisterFunction
    public void takeDamage(float amount) {
        if (currentHealth <= 0) return;
        currentHealth = Math.max(0.0f, currentHealth - amount);
        damaged.emit(amount);
        if (currentHealth <= 0) {
            died.emit();
        }
    }

    @RegisterFunction
    public void heal(float amount) {
        currentHealth = Math.min(maxHealth, currentHealth + amount);
    }

    public float getCurrentHealth() {
        return currentHealth;
    }

    public boolean isDead() {
        return currentHealth <= 0;
    }
}
