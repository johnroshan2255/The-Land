import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame, useThree } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import { CuboidCollider, RigidBody, useBeforePhysicsStep, useRapier, type RapierRigidBody } from '@react-three/rapier';
import type { Collider, DynamicRayCastVehicleController } from '@dimforge/rapier3d-compat';
import { DRACO, telemetry } from './state';
import { analog, controls, setControl, useKeyboardControls } from './controls';
import { emitPuff } from './Smoke';
import { isNight, sun } from './DayNight';
import { groundColorAt, isAsphalt, isGrass, isIce } from './groundColor';

// Spawn on the forest stretch of the road loop (Blender (450, -330) -> three.js (450, y, 330)), facing along the road.
const SPAWN = new THREE.Vector3(450, 0, 330);
const SPAWN_YAW = Math.atan2(350, -230);   // local -Z (car forward) toward road direction (-350, 0, +230)

const WHEELS = ['wheel_FL', 'wheel_FR', 'wheel_RL', 'wheel_RR'] as const;
// Suspension rays start at the chassis box centre, not just above its floor: when the box touched the ground (bump,
// landing, side slope) the old origin (4 cm above the box bottom) ended up under the terrain, the rays missed, and the
// car lay on its belly with the wheels sunk into the ground. Rest length is measured from here to the hub.
const SUSP_TOP = 1.5;
const RADIUS = 0.64;
const TRAVEL = 0.4;          // max suspension travel either side of rest (m)
// Chassis mass: box inertia (150 kg, 1.9 x 0.9 x 3.9 m) but the centre of mass near axle height. With it at the
// box centre (1.5 m up on a 2.08 m track) the jeep rolled over in ordinary turns and ended up stuck on its roof.
// centerOfMass is collider-local: the box sits at y = 1.5, so -0.7 puts the CoM at y = 0.8 on the body.
const MASS = { mass: 150, centerOfMass: { x: 0, y: -0.7, z: 0 }, principalAngularInertia: { x: 200, y: 235, z: 55 }, angularInertiaLocalFrame: { x: 0, y: 0, z: 0, w: 1 } };
const ENGINE = 260;          // per driven wheel
const BRAKE = 6;
const GRIP = 3, ICE_GRIP = 0.7;   // wheel friction slip on ground / on the frozen lake and ponds (drift on ice)
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
const ICE_COL = new THREE.Color();
const SH = { f: new THREE.Vector3(), b: new THREE.Vector3(), l: new THREE.Vector3(), r: new THREE.Vector3(), x: new THREE.Vector3(), n: new THREE.Vector3(), z: new THREE.Vector3(), m: new THREE.Matrix4() };

/**
 * The car's fake shadow (an image on a plane instead of a shadow map): the jeep's own top-down silhouette, body + wheels
 * at rest, rasterised once into a small canvas and blurred twice - a tight blur for the shadow itself plus a wide one for
 * the soft contact darkening around it. Returns the texture and the plane it covers in car space (x, z centre and size).
 */
function makeCarShadow(chassis: THREE.Object3D, wheels: { obj: THREE.Object3D; hub: THREE.Vector3 }[]) {
  const tris: number[] = [];   // x, z pairs, 3 per triangle, car space
  const v = new THREE.Vector3();
  const rel = new THREE.Matrix4();
  const add = (root: THREE.Object3D, offset: THREE.Vector3) => {
    root.updateMatrixWorld(true);
    const inv = root.matrixWorld.clone().invert();
    root.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      rel.multiplyMatrices(inv, mesh.matrixWorld);
      const pos = mesh.geometry.getAttribute('position');
      const idx = mesh.geometry.index;
      const n = idx ? idx.count : pos.count;
      for (let k = 0; k < n; k++) {
        v.fromBufferAttribute(pos, idx ? idx.getX(k) : k).applyMatrix4(rel).add(offset);
        tris.push(v.x, v.z);
      }
    });
  };
  add(chassis, new THREE.Vector3());
  for (const w of wheels) add(w.obj, w.hub);

  const PAD = 0.6;   // metres of room for the blur
  let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
  for (let k = 0; k < tris.length; k += 2) {
    x0 = Math.min(x0, tris[k]); x1 = Math.max(x1, tris[k]);
    z0 = Math.min(z0, tris[k + 1]); z1 = Math.max(z1, tris[k + 1]);
  }
  x0 -= PAD; x1 += PAD; z0 -= PAD; z1 += PAD;
  const PX = 24;   // texels per metre
  const w = Math.ceil((x1 - x0) * PX), h = Math.ceil((z1 - z0) * PX);
  const cv = document.createElement('canvas');
  cv.width = w;
  cv.height = h;
  const ctx = cv.getContext('2d', { willReadFrequently: true })!;
  ctx.fillStyle = '#fff';
  // one fill per triangle: as a single path, up- and down-facing triangles (opposite winding) would cancel into holes
  for (let k = 0; k < tris.length; k += 6) {   // row 0 = front (-z), column 0 = -x
    ctx.beginPath();
    ctx.moveTo((tris[k] - x0) * PX, (tris[k + 1] - z0) * PX);
    ctx.lineTo((tris[k + 2] - x0) * PX, (tris[k + 3] - z0) * PX);
    ctx.lineTo((tris[k + 4] - x0) * PX, (tris[k + 5] - z0) * PX);
    ctx.fill();
  }
  const img = ctx.getImageData(0, 0, w, h);
  const mask = new Float32Array(w * h);
  for (let k = 0; k < mask.length; k++) mask[k] = img.data[k * 4] / 255;
  const tight = boxBlur(mask, w, h, 3), wide = boxBlur(mask, w, h, 11);
  for (let k = 0; k < mask.length; k++) {
    const a = Math.min(1, tight[k] * 0.8 + wide[k] * 0.35) * 255;   // alphaMap reads green: write it to all channels
    img.data[k * 4] = img.data[k * 4 + 1] = img.data[k * 4 + 2] = a;
    img.data[k * 4 + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(cv);
  return { tex, cx: (x0 + x1) / 2, cz: (z0 + z1) / 2, sx: x1 - x0, sz: z1 - z0 };
}

/** Three passes of a separable box blur (close to a gaussian), radius r texels. */
function boxBlur(src: Float32Array, w: number, h: number, r: number) {
  let a = Float32Array.from(src), b = new Float32Array(src.length);
  const pass = (from: Float32Array, to: Float32Array, horizontal: boolean) => {
    const n = horizontal ? w : h, lines = horizontal ? h : w;
    for (let l = 0; l < lines; l++) {
      const at = (i: number) => (horizontal ? l * w + i : i * w + l);
      let sum = 0;
      for (let i = -r; i <= r; i++) sum += from[at(Math.min(n - 1, Math.max(0, i)))];
      for (let i = 0; i < n; i++) {
        to[at(i)] = sum / (2 * r + 1);
        sum += from[at(Math.min(n - 1, i + r + 1))] - from[at(Math.max(0, i - r))];
      }
    }
  };
  for (let k = 0; k < 3; k++) {
    pass(a, b, true);
    pass(b, a, false);
  }
  return a;
}

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
  const shadow = useRef<THREE.Mesh>(null);
  useKeyboardControls();

  const parts = useMemo(() => {
    const wheels = WHEELS.map((n) => {
      const w = nodes[n].clone();
      const hub = nodes[n].position.clone();
      w.position.set(0, 0, 0);
      return { obj: w, hub };
    });
    const chassis = nodes.car_body.clone();
    chassis.position.set(0, 0, 0);
    // toon-shade the car like the world (toonShading.ts): each PBR material -> Lambert of the same colour, shared
    const toon = new Map<THREE.Material, THREE.MeshLambertMaterial>();
    for (const root of [chassis, ...wheels.map((w) => w.obj)]) {
      root.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh) return;
        const swap = (src: THREE.Material) => {
          if (!toon.has(src)) toon.set(src, new THREE.MeshLambertMaterial({ color: (src as THREE.MeshStandardMaterial).color }));
          return toon.get(src)!;
        };
        m.material = Array.isArray(m.material) ? m.material.map(swap) : swap(m.material);
      });
    }
    const shadowImg = makeCarShadow(chassis, wheels);
    const shadowGeo = new THREE.PlaneGeometry(shadowImg.sx, shadowImg.sz).rotateX(-Math.PI / 2).translate(shadowImg.cx, 0, shadowImg.cz);
    const shadowMat = new THREE.MeshBasicMaterial({
      color: '#1c0a4a', alphaMap: shadowImg.tex, transparent: true, depthWrite: false, fog: false,   // violet, like the toon shade
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
    });
    return { chassis, wheels, shadowGeo, shadowMat };
  }, [nodes]);

  useEffect(() => {
    if (!body.current) return;
    const v = world.createVehicleController(body.current);
    v.indexUpAxis = 1;
    v.setIndexForwardAxis = 2;
    for (const { hub } of parts.wheels) {
      v.addWheel({ x: hub.x, y: SUSP_TOP, z: hub.z }, { x: 0, y: -1, z: 0 }, { x: -1, y: 0, z: 0 }, SUSP_TOP - hub.y, RADIUS);
    }
    for (let i = 0; i < parts.wheels.length; i++) {
      v.setWheelSuspensionStiffness(i, 30);
      v.setWheelSuspensionCompression(i, 4.4);
      v.setWheelSuspensionRelaxation(i, 2.6);
      v.setWheelMaxSuspensionTravel(i, TRAVEL);
      v.setWheelFrictionSlip(i, GRIP);
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
    // terrain only: tree trunks and rocks must not lift the camera or the shadow
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
    // keys are all-or-nothing; the touch drive stick is analog and simply adds on top
    const throttle = THREE.MathUtils.clamp((k.fwd ? 1 : 0) - (k.back ? 1 : 0) + analog.throttle, -1, 1);
    const target = THREE.MathUtils.clamp((k.left ? 1 : 0) - (k.right ? 1 : 0) + analog.steer, -1, 1) * MAX_STEER;
    steer.current += (target - steer.current) * 0.15;
    for (let i = 0; i < 4; i++) {
      v.setWheelEngineForce(i, -throttle * ENGINE);   // forward is -Z
      v.setWheelBrake(i, k.brake ? BRAKE : 0);
      v.setWheelSteering(i, i < 2 ? steer.current : 0);
    }
    for (let i = 0; i < 4; i++) {   // ice under a wheel = little grip
      const cp = v.wheelIsInContact(i) ? v.wheelContactPoint(i) : null;
      v.setWheelFrictionSlip(i, cp && groundColorAt(cp.x, cp.z, ICE_COL) && isIce(ICE_COL) ? ICE_GRIP : GRIP);
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
      const len = v.wheelSuspensionLength(i) ?? v.wheelSuspensionRestLength(i) ?? 0;
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
    const throttle = controls.fwd || controls.back || Math.abs(analog.throttle) > 0.2;
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

    // ---- headlight eyes glow at night
    if (glow.current) glow.current.visible = isNight();

    // ---- fake shadow: fit a plane to the ground under the car (4 short terrain rays), lay the shadow image on it,
    //      shift it away from the sun and fade it with daylight and with height (jumps)
    const sh = shadow.current;
    if (sh) {
      const fx = fwd.x, fz = fwd.z, fl = Math.hypot(fx, fz) || 1;
      const ux = fx / fl, uz = fz / fl;   // flat forward
      const yf = groundY(p.x + ux * 1.8, p.y + 2, p.z + uz * 1.8, 8);
      const yb = groundY(p.x - ux * 1.8, p.y + 2, p.z - uz * 1.8, 8);
      const yl = groundY(p.x + uz * 1.1, p.y + 2, p.z - ux * 1.1, 8);
      const yr = groundY(p.x - uz * 1.1, p.y + 2, p.z + ux * 1.1, 8);
      sh.visible = yf !== null && yb !== null && yl !== null && yr !== null;
      if (sh.visible) {
        SH.f.set(ux * 1.8, yf!, uz * 1.8);
        SH.b.set(-ux * 1.8, yb!, -uz * 1.8);
        SH.l.set(uz * 1.1, yl!, -ux * 1.1);
        SH.r.set(-uz * 1.1, yr!, ux * 1.1);
        SH.n.crossVectors(SH.x.subVectors(SH.l, SH.r), SH.z.subVectors(SH.f, SH.b)).normalize();
        if (SH.n.y < 0) SH.n.negate();
        const gy = (yf! + yb! + yl! + yr!) / 4;
        SH.z.set(-ux, 0, -uz).addScaledVector(SH.n, uz * SH.n.z + ux * SH.n.x).normalize();   // car back, in the plane
        SH.x.crossVectors(SH.n, SH.z);
        sh.quaternion.setFromRotationMatrix(SH.m.makeBasis(SH.x, SH.n, SH.z));
        const lean = Math.min(0.9, 0.35 / Math.max(sun.y, 0.3));   // longer offset when the sun is low
        sh.position.set(p.x - sun.x * lean, gy + 0.05, p.z - sun.z * lean);
        const lift = p.y - gy;   // ~0 on the ground (car origin = wheel bottoms)
        (sh.material as THREE.MeshBasicMaterial).opacity = 0.85 * sun.shadow * THREE.MathUtils.clamp(1 - (lift - 0.3) / 3, 0.15, 1);
      }
    }

    // ---- chase camera with mouse orbit (or the touch look stick) + auto focus above 15 km/h
    const o = orbit.current;
    const now = performance.now() / 1000;
    if (analog.lookX || analog.lookY) {
      o.yaw -= analog.lookX * 2.4 * dt;
      o.pitch = THREE.MathUtils.clamp(o.pitch + analog.lookY * 1.4 * dt, 0.05, 1.25);
      o.lastInput = now;
    }
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

  return (
    <>
      <RigidBody ref={body} colliders={false} position={[SPAWN.x, 400, SPAWN.z]} canSleep={false} linearDamping={0.05} angularDamping={0.4} ccd>
        <CuboidCollider args={[0.95, 0.45, 1.95]} position={[0, 1.5, 0]} massProperties={MASS} />
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
      <mesh ref={shadow} geometry={parts.shadowGeo} material={parts.shadowMat} renderOrder={-1} frustumCulled={false} />
    </>
  );
}

useGLTF.preload('/models/red_jeep_game.glb', DRACO);
