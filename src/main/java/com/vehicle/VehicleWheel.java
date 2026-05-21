package com.vehicle;

import com.character.UserCommand;
import godot.annotation.Export;
import godot.annotation.RegisterClass;
import godot.annotation.RegisterFunction;
import godot.annotation.RegisterProperty;
import godot.api.*;
import godot.core.Vector3;
import godot.global.GD;

@RegisterClass(className = "VehicleWheel")
public class VehicleWheel extends RayCast3D {

    private static final float TWO_PI = (float)(2.0 * Math.PI);

    // ── Inspector exports ─────────────────────────────────────────────────────

    /** Visual scene for this wheel. Null = use Vehicle.defaultWheelScene. */
    @RegisterProperty @Export public PackedScene wheelScene;

    /** Override visual radius (metres); 0 = use Vehicle.wheelRadius. */
    @RegisterProperty @Export public float wheelRadius = 0.4f;

    @RegisterProperty @Export public float springStrength = 10000.0f;
    @RegisterProperty @Export public float springDamping = 4500.0f;
    @RegisterProperty @Export public float restDistance = 0.5f;
    @RegisterProperty @Export public float overExtend = 0.3f;
    @RegisterProperty @Export public float zTraction = 0.05f;
    @RegisterProperty @Export public float zBrakeTraction = 0.25f;


    @RegisterProperty @Export public boolean isMotor = false;

    @RegisterProperty @Export public boolean isSteer = false;

    @RegisterProperty @Export public Curve gripCurve;



    // ── Runtime state ─────────────────────────────────────────────────────────

    private Vehicle   vehicle;
    private Node3D wheelMesh;
    private GPUParticles3D skidMark;

    private float tireMaxTurnMinRad;
    private float tireMaxTurnMaxRad;
    private float gripFactor;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @RegisterFunction
    @Override
    public void _ready() {
        vehicle = (Vehicle) getOwner();
        wheelMesh = (Node3D) getNode("Wheel");
        skidMark = (GPUParticles3D) getNode("SkidMark");

        springStrength = vehicle.springStrength;
        springDamping = vehicle.springDamping;
        wheelRadius = vehicle.wheelRadius;
        restDistance = vehicle.restDistance;
        overExtend = vehicle.overExtend;
        zTraction = vehicle.zTraction;
        zBrakeTraction = vehicle.zBrakeTraction;
        tireMaxTurnMinRad = (float) GD.degToRad(-vehicle.tireMaxTurnDegrees);
        tireMaxTurnMaxRad = (float) GD.degToRad(vehicle.tireMaxTurnDegrees);

        Vector3 targetPosition = getTargetPosition();
        targetPosition.setY(-(restDistance + wheelRadius + overExtend));
        setTargetPosition(targetPosition);
    }

    private Vector3 getPointVelocity(Vector3 point) {
        return vehicle.getLinearVelocity().plus(vehicle.getAngularVelocity().cross(point.minus(vehicle.getGlobalPosition())));
    }

    public void applyWheelPhysics(float delta, float getPhysicsProcessDeltaTime, UserCommand cmd) {
        forceRaycastUpdate();
        Vector3 targetPosition = getTargetPosition();
        targetPosition.setY(-(restDistance + wheelRadius + overExtend));
        setTargetPosition(targetPosition);

        // Rotates wheel visuals
        Vector3 forwardDir = getGlobalBasis().getZ().times(-1);
        double speed = forwardDir.dot(vehicle.getLinearVelocity());
        wheelMesh.rotateX((float) ((-speed * getPhysicsProcessDeltaTime ) /wheelRadius));

        if (!isColliding()) {return;}

        // From here now, wheel is colliding
        Vector3 contact    = getCollisionPoint();
        double  springLen    = getGlobalPosition().distanceTo(contact) - wheelRadius;
        double springCompression =  restDistance - springLen;

        Vector3 wheelMeshPosition = wheelMesh.getPosition();
        wheelMeshPosition.setY(GD.moveToward(wheelMeshPosition.getY(), -springLen, 5 * getPhysicsProcessDeltaTime())); // Local y position of the wheel
        wheelMesh.setPosition(wheelMeshPosition);

        contact = wheelMesh.getGlobalPosition(); // Contact is now the wheel origin point
        Vector3 forcePosition = contact.minus(vehicle.getGlobalPosition());

        // Spring Suspension Force
        double springForceMagnitude = springStrength * springCompression;
        Vector3 tireVelocity = getPointVelocity(contact); // Center of the wheel
        double springDampForceMagnitude = springDamping * getGlobalBasis().getY().dot(tireVelocity);

        Vector3 yForce = getCollisionNormal().times(springForceMagnitude - springDampForceMagnitude);

        // Acceleration
        if(isMotor && cmd.motor != 0) {
            double speedRatio = speed / vehicle.maxSpeed;
            double accelerationRatio = vehicle.accelerationCurve.sampleBaked((float) speedRatio);
            Vector3 accelerationForce = forwardDir.times(vehicle.acceleration *  cmd.motor  * accelerationRatio);

            vehicle.applyForce(accelerationForce, forcePosition);
        }

        // Tire X traction
        float steeringXSpeed = (float) getGlobalBasis().getX().dot(tireVelocity);

        gripFactor = (float) GD.abs(steeringXSpeed/tireVelocity.length());
        double xTraction = gripCurve.sampleBaked(gripFactor);

        if(cmd.handbrake && gripFactor < 0.2f) {
            vehicle.setSlipping(false);
        }

        if(cmd.handbrake) {
            xTraction = 0.01f;
        }
        else if (vehicle.isSlipping()) {
            xTraction = 0.1;
        }

        double gravity =  -vehicle.getGravity().getY();
        Vector3 xForce = getGlobalBasis().getX().times(-1 * steeringXSpeed * xTraction * ((vehicle.getMass() *gravity)/4.0));

        // z force traction
        double forwardSpeed = forwardDir.dot(tireVelocity);
        float zFriction = zTraction;

        if (vehicle.isBraking()) {
            zFriction = zBrakeTraction;
        }

        Vector3 zForce = vehicle.getGlobalBasis().getZ().times(forwardSpeed * zFriction * ((vehicle.getMass() *gravity)/vehicle.getWheels().size()));


        vehicle.applyForce(xForce, forcePosition);
        vehicle.applyForce(yForce, forcePosition);
        vehicle.applyForce(zForce, forcePosition);
    }


    public void applySkidMark() {

        skidMark.setGlobalPosition(getCollisionPoint().plus(Vector3.Companion.getUP().times(0.01)));
        skidMark.lookAt(skidMark.getGlobalPosition().plus(vehicle.getGlobalBasis().getZ()));

        if(!vehicle.isHandbraking() && gripFactor < 0.2f) {
            vehicle.setSlipping(false);
            skidMark.setEmitting(false);
        }

        if(vehicle.isHandbraking() && !skidMark.isEmitting()) {
            skidMark.setEmitting(true);
        }

    }

/**
     * Applies an upward spring+damper force to the vehicle at this wheel's position.
     * Called from Vehicle._physicsProcess each frame.
     * Returns true when the wheel is within hoverHeight of the ground.
     */
    public void applyWheelSuspension(float delta) {
        if (vehicle == null) {return;}

        if (!isColliding()) {return;}
        Vector3 targetPosition = getTargetPosition();
        targetPosition.setY(-(restDistance + wheelRadius + overExtend));
        setTargetPosition(targetPosition);

        Vector3 contact    = getCollisionPoint();
        Vector3 springUpDir = getGlobalTransform().getBasis().getY().normalized();
        double  springLen    = getGlobalPosition().distanceTo(contact) - wheelRadius;
        double compression =  restDistance - springLen;

        Vector3 wheelMeshPosition = wheelMesh.getPosition();
        wheelMeshPosition.setY(-springLen);
        wheelMesh.setPosition(wheelMeshPosition);

        double springForceMagnitude = springStrength * compression;

        // damping force = damping * relative velocity
        Vector3 worldVelocity = getPointVelocity(contact);
        double relativeVelocity = springUpDir.dot(worldVelocity);
        double springDampForceMagnitude = springDamping * relativeVelocity;

        Vector3 springForce = getCollisionNormal().times(springForceMagnitude - springDampForceMagnitude);

        contact = wheelMesh.getGlobalPosition();
        Vector3 forcePosOffset = contact.minus(vehicle.getGlobalPosition());

        vehicle.applyForce(springForce, forcePosOffset);
    }

    public void applyWheelAcceleration(float processedDeltaTime, float motor) {
        Vector3 forwardDir = getGlobalBasis().getZ().times(-1);
        double velocity = forwardDir.dot(vehicle.getLinearVelocity());
        wheelMesh.rotateX((float) ((-velocity * processedDeltaTime ) /wheelRadius));

        if (!isColliding()) {return;}

        Vector3 contact    = getCollisionPoint();
        Vector3 forcePosition = contact.minus(vehicle.getGlobalPosition());

        if(isMotor && motor != 0) {
            double speedRatio = velocity / vehicle.maxSpeed;
            double accelerationRatio = vehicle.accelerationCurve.sampleBaked((float) speedRatio);
            Vector3 forceVector = forwardDir.times(vehicle.acceleration * motor * accelerationRatio);

            vehicle.applyForce(forceVector, forcePosition);
        }
    }

    public void applyWheelSteering(float delta, float steering) {
        if(!isSteer) {return;}

        Vector3 rotation = getRotation();

        if (steering != 0) {
            float rotationValue = (float) GD.clamp(getRotation().getY() + (steering * delta), tireMaxTurnMinRad, tireMaxTurnMaxRad);
            rotation.setY(rotationValue);
                   }
        else {
            rotation.setY((float) GD.moveToward(getRotation().getY(), 0, vehicle.tireMaxTurnSpeed * delta));
        }

        setRotation(rotation);
    }

    public void applyWheelTraction(boolean handbrake) {
        if (!isColliding()) {return;}

        Vector3 steerSideDir = getGlobalBasis().getX();
        Vector3 tireVelocity = getPointVelocity(wheelMesh.getGlobalPosition());
        float steeringXVelocity = (float) steerSideDir.dot(tireVelocity);

        float gripFactor = (float) GD.abs(steeringXVelocity/tireVelocity.length());
        double xTraction = gripCurve.sampleBaked(gripFactor);

        skidMark.setGlobalPosition(getCollisionPoint().plus(Vector3.Companion.getUP().times(0.01)));
        skidMark.lookAt(skidMark.getGlobalPosition().plus(vehicle.getGlobalBasis().getZ()));

        boolean isSlipping = true;

        if(!handbrake && gripFactor < 0.2f) {
            isSlipping = false;
            skidMark.setEmitting(false);
        }

        if(handbrake) {
           xTraction = 0.01f;
           if (!skidMark.isEmitting()) {
               skidMark.setEmitting(true);
           }
        }
        else if (isSlipping) {
            xTraction = 0.1;
        }

        float gravity = Float.parseFloat(String.valueOf(ProjectSettings.getSetting("physics/3d/default_gravity", 9.85)));
        Vector3 xForce = steerSideDir.times(-1 * steeringXVelocity * xTraction * ((vehicle.getMass() *gravity)/4.0));

        // z force tracktion
        float forwardVelocity = (float)-getGlobalBasis().getZ().dot(tireVelocity);
        float zTraction = 0.05f;
        Vector3 zForce = vehicle.getGlobalBasis().getZ().times(forwardVelocity * zTraction * ((vehicle.getMass() *gravity)/4.0));

        Vector3 forcePosition = getGlobalPosition().minus(vehicle.getGlobalPosition());

        vehicle.applyForce(xForce, forcePosition);
        vehicle.applyForce(zForce, forcePosition);

    }

}
