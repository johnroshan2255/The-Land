import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame, useThree } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import { CuboidCollider, RigidBody, useBeforePhysicsStep, useRapier, type RapierRigidBody } from '@react-three/rapier';
import type { Collider, DynamicRayCastVehicleController } from '@dimforge/rapier3d-compat';
import { DRACO, PRESET, telemetry } from './state';
import { controls, setControl, useKeyboardControls } from './controls';
import { emitPuff } from './Smoke';
import { isNight } from './DayNight';
import { groundColorAt, isAsphalt, isGrass } from './groundColor';

// Spawn on the forest stretch of the road loop (Blender (450, -330) -> three.js (450, y, 330)), facing along the road.
const SPAWN = new THREE.Vector3(450, 0, 330);
const SPAWN_YAW = Math.atan2(350, -230);   // local -Z (car forward) toward road direction (-350, 0, +230)

const WHEELS = ['wheel_FL', 'wheel_FR', 'wheel_RL', 'wheel_RR'] as const;
const REST = 0.45;           // suspension rest length (m)
const RADIUS = 0.64;
const ENGINE = 260;          // per driven wheel
const BRAKE = 6;
const MAX_STEER = 0.55;

// chase camera
const CAM_DIST = 10.5;
const CAM_PITCH = 0.55;            // radians above the horizon
const LOOK_AHEAD = 10;              // aim this far ahead of the car so the horizon stays in frame (like the refs)
const AUTO_FOCUS_KMH = 15;         // above this the camera swings back behind the car
const AUTO_FOCUS_IDLE = 0.6;       // seconds after the last mouse input

// scratch objects (no allocations in the frame loop)
const V = { a: new THREE.Vector3(), b: new THREE.Vector3(), c: new THREE.Vector3(), p: new THREE.Vector3(), look: new THREE.Vector3() };
const Q = new THREE.Quaternion();
const EXHAUST = new THREE.Vector3(0.55, 0.85, 2.15);
const SMOKE_COL = new THREE.Color('#eceae6');
const GROUND = new THREE.Color();
const DUST = new THREE.Color();
const WHITE = new THREE.Color('#ffffff');

export function Car() {
  const { nodes } = useGLTF('/models/red_jeep_game.glb', DRACO);
  const { world, rapier } = useRapier();
  const { gl, camera } = useThree();
  const body = useRef<RapierRigidBody>(null);
  const vehicle = useRef<DynamicRayCastVehicleController | null>(null);
  const wheelRefs = useRef<(THREE.Object3D | null)[]>([]);
  const placed = useRef(false);
  const steer = useRef(0);
  const glow = useRef<THREE.Group>(null);
  const blob = useRef<THREE.Mesh>(null);
  useKeyboardControls();

  const parts = useMemo(() => {
    const shade = (o: THREE.Object3D) => {
      const c = o.clone();
      c.traverse((m) => {
        m.castShadow = PRESET.shadows === 'directional';
        m.receiveShadow = PRESET.shadows === 'directional';
      });
      return c;
    };
    const wheels = WHEELS.map((n) => {
      const w = shade(nodes[n]);
      const hub = nodes[n].position.clone();
      w.position.set(0, 0, 0);
      return { obj: w, hub };
    });
    const chassis = shade(nodes.car_body);
    chassis.position.set(0, 0, 0);
    return { chassis, wheels };
  }, [nodes]);

  useEffect(() => {
    if (!body.current) return;
    const v = world.createVehicleController(body.current);
    v.indexUpAxis = 1;
    v.setIndexForwardAxis = 2;
    for (const { hub } of parts.wheels) {
      v.addWheel({ x: hub.x, y: hub.y + REST, z: hub.z }, { x: 0, y: -1, z: 0 }, { x: -1, y: 0, z: 0 }, REST, RADIUS);
    }
    for (let i = 0; i < parts.wheels.length; i++) {
      v.setWheelSuspensionStiffness(i, 30);
      v.setWheelSuspensionCompression(i, 4.4);
      v.setWheelSuspensionRelaxation(i, 2.6);
      v.setWheelMaxSuspensionTravel(i, 0.4);
      v.setWheelFrictionSlip(i, 3);
      v.setWheelSideFrictionStiffness(i, 1);
    }
    vehicle.current = v;
    if (import.meta.env.DEV) Object.assign(window, { __car: { body: body.current, vehicle: v, world, camera, orbit: orbit.current, camFloor } });   // debugging hook
    return () => {
      world.removeVehicleController(v);
      vehicle.current = null;
    };
  }, [world, parts]);

  // ------------------------------------------------------------------ mouse orbit camera
  const orbit = useRef({ yaw: 0, pitch: CAM_PITCH, dist: CAM_DIST, dragging: false, lastInput: -10, px: 0, py: 0 });
  const camFloor = useRef(-1e9);
  useEffect(() => {
    const el = gl.domElement;
    const o = orbit.current;
    const down = (e: PointerEvent) => {
      o.dragging = true;
      o.px = e.clientX;
      o.py = e.clientY;
      el.setPointerCapture(e.pointerId);
    };
    const move = (e: PointerEvent) => {
      if (!o.dragging) return;
      o.yaw -= (e.clientX - o.px) * 0.006;
      o.pitch = THREE.MathUtils.clamp(o.pitch + (e.clientY - o.py) * 0.004, 0.05, 1.25);
      o.px = e.clientX;
      o.py = e.clientY;
      o.lastInput = performance.now() / 1000;
    };
    const up = (e: PointerEvent) => {
      o.dragging = false;
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
    };
    const wheel = (e: WheelEvent) => {
      o.dist = THREE.MathUtils.clamp(o.dist * (1 + Math.sign(e.deltaY) * 0.1), 6, 45);
      e.preventDefault();
    };
    const menu = (e: Event) => e.preventDefault();
    el.addEventListener('pointerdown', down);
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
    el.addEventListener('wheel', wheel, { passive: false });
    el.addEventListener('contextmenu', menu);
    return () => {
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
      el.removeEventListener('wheel', wheel);
      el.removeEventListener('contextmenu', menu);
    };
  }, [gl]);

  const groundRay = useMemo(() => new rapier.Ray({ x: 0, y: 0, z: 0 }, { x: 0, y: -1, z: 0 }), [rapier]);
  const terrainOnly = useMemo(() => (c: Collider) => c.shapeType() === rapier.ShapeType.TriMesh, [rapier]);
  const groundY = (x: number, y: number, z: number, maxDist = 200) => {
    groundRay.origin = { x, y, z };
    // terrain only: tree trunks and rocks must not lift the camera or the blob shadow
    const hit = world.castRay(groundRay, maxDist, true, undefined, undefined, undefined, body.current ?? undefined, terrainOnly);
    return hit ? y - hit.timeOfImpact : null;
  };

  const place = (x: number, z: number, yaw: number) => {
    const b = body.current;
    if (!b) return false;
    const gy = groundY(x, 800, z, 1000);
    if (gy === null) return false;
    Q.setFromAxisAngle(V.a.set(0, 1, 0), yaw);
    b.setTranslation({ x, y: gy + 1.2, z }, true);
    b.setRotation(Q, true);
    b.setLinvel({ x: 0, y: 0, z: 0 }, true);
    b.setAngvel({ x: 0, y: 0, z: 0 }, true);
    return true;
  };

  useBeforePhysicsStep((w) => {
    const v = vehicle.current;
    const b = body.current;
    if (!v || !b) return;
    if (!placed.current) {
      placed.current = place(SPAWN.x, SPAWN.z, SPAWN_YAW);
      return;
    }
    const k = controls;
    if (k.reset) {
      const p = b.translation();
      V.a.set(0, 0, -1).applyQuaternion(Q.copy(b.rotation() as THREE.Quaternion));
      place(p.x, p.z, Math.atan2(-V.a.x, -V.a.z));
      setControl('reset', false);
    }
    const throttle = (k.fwd ? 1 : 0) - (k.back ? 1 : 0);
    const target = ((k.left ? 1 : 0) - (k.right ? 1 : 0)) * MAX_STEER;
    steer.current += (target - steer.current) * 0.15;
    for (let i = 0; i < 4; i++) {
      v.setWheelEngineForce(i, -throttle * ENGINE);   // forward is -Z
      v.setWheelBrake(i, k.brake ? BRAKE : 0);
      v.setWheelSteering(i, i < 2 ? steer.current : 0);
    }
    v.updateVehicle(w.timestep);
  });

  const smokeAcc = useRef({ exhaust: 0, dust: 0 });

  useFrame((_, dtRaw) => {
    const v = vehicle.current;
    const b = body.current;
    if (!v || !b) return;
    const dt = Math.min(dtRaw, 0.05);
    // wheels: suspension travel, steering, spin
    for (let i = 0; i < parts.wheels.length; i++) {
      const w = wheelRefs.current[i];
      if (!w) continue;
      const c = v.wheelChassisConnectionPointCs(i)!;
      const len = v.wheelSuspensionLength(i) ?? REST;
      w.position.set(c.x, c.y - len, c.z);
      w.rotation.set(v.wheelRotation(i) ?? 0, v.wheelSteering(i) ?? 0, 0, 'YXZ');
    }
    const speed = v.currentVehicleSpeed();
    const kmh = Math.abs(speed) * 3.6;

    // Follow the *rendered* (interpolated) chassis, not the raw physics pose: reading the raw pose made the camera
    // and the world jitter against the smoothly drawn car.
    const p = parts.chassis.getWorldPosition(V.p);
    parts.chassis.getWorldQuaternion(Q);
    const fwd = V.a.set(0, 0, -1).applyQuaternion(Q);
    telemetry.x = p.x;
    telemetry.y = p.y;
    telemetry.z = p.z;
    telemetry.speed = speed;
    telemetry.heading = Math.atan2(fwd.x, -fwd.z);

    // ---- smoke: exhaust always, more on throttle; dust from the rear wheels when moving fast on loose ground
    const acc = smokeAcc.current;
    const throttle = controls.fwd || controls.back;
    acc.exhaust += dt * (throttle ? 16 : 3);
    while (acc.exhaust >= 1) {
      acc.exhaust -= 1;
      V.b.copy(EXHAUST).applyQuaternion(Q).add(p as THREE.Vector3);
      V.c.set(0, 0, 1).applyQuaternion(Q);
      emitPuff(V.b.x, V.b.y, V.b.z, V.c.x * 1.5 + (Math.random() - 0.5), 1.2 + Math.random() * 0.6, V.c.z * 1.5 + (Math.random() - 0.5), throttle ? 0.24 : 0.16, SMOKE_COL, 1.1);
    }
    acc.dust += dt * (kmh > 12 ? Math.min(kmh, 60) * 0.5 : 0);
    while (acc.dust >= 1) {
      acc.dust -= 1;
      const wi = Math.random() < 0.5 ? 2 : 3;
      if (!v.wheelIsInContact(wi)) continue;
      const cp = v.wheelContactPoint(wi);
      if (!cp) continue;
      // dust only on loose ground (sand, dirt, snow), tinted like the ground under the wheel; none on grass or asphalt
      if (!groundColorAt(cp.x, cp.z, GROUND) || isGrass(GROUND) || isAsphalt(GROUND)) continue;
      DUST.copy(GROUND).lerp(WHITE, 0.45);
      emitPuff(cp.x, cp.y + 0.25, cp.z, (Math.random() - 0.5) * 1.6, 0.6 + Math.random() * 0.8, (Math.random() - 0.5) * 1.6, 0.24, DUST, 1.2);
    }

    // ---- headlight eyes glow at night; blob shadow on the low tier
    if (glow.current) glow.current.visible = isNight();
    if (blob.current) {
      const gy = groundY(p.x, p.y + 1, p.z);
      blob.current.visible = gy !== null;
      if (gy !== null) blob.current.position.set(p.x, gy + 0.06, p.z);
    }

    // ---- chase camera with mouse orbit + auto focus above 15 km/h
    const o = orbit.current;
    const now = performance.now() / 1000;
    if (kmh > AUTO_FOCUS_KMH && !o.dragging && now - o.lastInput > AUTO_FOCUS_IDLE) {
      o.yaw = Math.atan2(Math.sin(o.yaw), Math.cos(o.yaw));   // wrap, then ease back behind the car
      const k = 1 - Math.exp(-2.5 * dt);
      o.yaw += (0 - o.yaw) * k;
      o.pitch += (CAM_PITCH - o.pitch) * k;
    }
    const carYaw = Math.atan2(-fwd.x, -fwd.z);   // yaw whose +Z points behind the car
    const yaw = carYaw + o.yaw;
    const desired = V.b.set(
      p.x + Math.sin(yaw) * Math.cos(o.pitch) * o.dist,
      p.y + 1.6 + Math.sin(o.pitch) * o.dist,
      p.z + Math.cos(yaw) * Math.cos(o.pitch) * o.dist,
    );
    const gy = groundY(desired.x, desired.y + 50, desired.z);
    // keep the camera out of hills, easing the lift in instead of snapping
    if (gy !== null) {
      const floor = gy + 1.8;
      camFloor.current = camFloor.current < -1e8 ? floor : camFloor.current + (floor - camFloor.current) * (1 - Math.exp(-6 * dt));
    }
    if (desired.y < camFloor.current) desired.y = camFloor.current;
    const a = 1 - Math.exp(-(o.dragging ? 14 : 5) * dt);
    camera.position.lerp(desired, a);
    V.b.set(p.x - Math.sin(carYaw) * LOOK_AHEAD, p.y + 1.4, p.z - Math.cos(carYaw) * LOOK_AHEAD);
    V.look.lerp(V.b, 1 - Math.exp(-14 * dt));   // smoothed look target (no per-frame snapping)
    camera.lookAt(V.look);
  });

  const glowMat = useMemo(() => new THREE.MeshBasicMaterial({ color: '#fff3c4' }), []);
  const beamMat = useMemo(() => new THREE.MeshBasicMaterial({ color: '#fff1b8', transparent: true, opacity: 0.1, depthWrite: false, blending: THREE.AdditiveBlending }), []);
  const blobTex = useMemo(() => {
    const cv = document.createElement('canvas');
    cv.width = cv.height = 64;
    const ctx = cv.getContext('2d')!;
    const g = ctx.createRadialGradient(32, 32, 4, 32, 32, 32);
    g.addColorStop(0, 'rgba(0,0,0,0.55)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(cv);
  }, []);

  return (
    <>
      <RigidBody ref={body} colliders={false} position={[SPAWN.x, 400, SPAWN.z]} canSleep={false} linearDamping={0.05} angularDamping={0.4} ccd>
        <CuboidCollider args={[0.95, 0.45, 1.95]} position={[0, 1.5, 0]} mass={150} />
        <primitive object={parts.chassis} />
        {parts.wheels.map((w, i) => (
          <group key={i} ref={(el) => { wheelRefs.current[i] = el; }}>
            <primitive object={w.obj} />
          </group>
        ))}
        {/* cartoon eyes double as headlights at night */}
        <group ref={glow} visible={false}>
          {[-0.62, 0.62].map((x) => (
            <group key={x} position={[x, 1.47, -1.95]}>
              <mesh material={glowMat}>
                <circleGeometry args={[0.2, 16]} />
              </mesh>
              {/* cone apex at the eye, opening forward (-Z) */}
              <mesh material={beamMat} position={[0, -0.4, -7]} rotation-x={Math.PI / 2}>
                <coneGeometry args={[2.6, 14, 16, 1, true]} />
              </mesh>
            </group>
          ))}
        </group>
      </RigidBody>
      {PRESET.shadows === 'blob' && (
        <mesh ref={blob} rotation-x={-Math.PI / 2}>
          <planeGeometry args={[3.2, 5]} />
          <meshBasicMaterial map={blobTex} transparent depthWrite={false} polygonOffset polygonOffsetFactor={-2} />
        </mesh>
      )}
    </>
  );
}

useGLTF.preload('/models/red_jeep_game.glb', DRACO);
