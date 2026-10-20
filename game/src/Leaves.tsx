// Fallen leaves around the car, after Bruno Simon's folio-2025 Leaves.js (MIT licence, github.com/brunosimon/folio-2025).
// His runs as a WebGPU compute shader; phones on WebGL can't, so a few hundred leaves are simulated on the CPU instead
// (same rules: the car's velocity and a sideways push fling leaves near it up and away, wind drifts them, damping is
// high in the air, gravity pulls them down) and drawn as one instanced mesh. Their height above the ground is
// simulated; the ground itself comes from the grass ground capture in the vertex shader. They live on grass only (not
// on snow or sand) and wrap around the car as it drives.
import { useMemo } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { PRESET, telemetry } from './state';
import { groundGLSL, groundUniforms } from './Grass';
import { groundColorAt, isGrass } from './groundColor';
import { windUniforms } from './wind';

const COUNT = { low: 160, medium: 320, high: 640 }[PRESET.tier];
const HALF_FIELD = 32;
const C = new THREE.Color();

export function Leaves() {
  const sim = useMemo(() => {
    const n = COUNT;
    const pos = new Float32Array(n * 3), vel = new Float32Array(n * 3), w = new Float32Array(n), on = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 2 * HALF_FIELD;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 2 * HALF_FIELD;
      w[i] = Math.random() * 0.1 + 0.1;   // Bruno: weight 0.1 .. 0.2
    }
    return { pos, vel, w, on, checked: new Uint8Array(n) };
  }, []);

  const mesh = useMemo(() => {
    const quad = new THREE.PlaneGeometry(1, 1);
    const p = quad.getAttribute('position').array as Float32Array;
    p[0] += 0.15; p[3] += 0.15; p[6] -= 0.15; p[9] -= 0.15;   // Bruno's skewed leaf quad
    quad.rotateX(-Math.PI / 2);
    const g = new THREE.InstancedBufferGeometry();
    g.index = quad.index;
    for (const k of ['position', 'normal', 'uv']) g.setAttribute(k, quad.getAttribute(k));
    g.instanceCount = COUNT;
    const leaf = new THREE.InstancedBufferAttribute(new Float32Array(COUNT * 4), 4);   // x, height, z, rotation seed
    leaf.setUsage(THREE.DynamicDrawUsage);
    g.setAttribute('leaf', leaf);
    const colors = new Float32Array(COUNT * 3);
    const a = new THREE.Color(0x95513a), b = new THREE.Color(0xf56a3a);
    for (let i = 0; i < COUNT; i++) C.copy(a).lerp(b, Math.random()).toArray(colors, i * 3);   // Bruno's leaf colours
    g.setAttribute('tint', new THREE.InstancedBufferAttribute(colors, 3));
    const m = new THREE.MeshLambertMaterial({ side: THREE.DoubleSide });
    m.customProgramCacheKey = () => 'leaves';
    m.onBeforeCompile = (s) => {
      Object.assign(s.uniforms, groundUniforms, windUniforms);
      s.vertexShader = s.vertexShader
        .replace('#include <common>', `#include <common>\n${groundGLSL}\nattribute vec4 leaf; attribute vec3 tint; varying vec3 vTint;`)
        .replace('#include <beginnormal_vertex>', 'vec3 objectNormal = vec3(0.0, 1.0, 0.0);')
        .replace('#include <begin_vertex>', /* glsl */ `
          vec3 transformed = position * 0.38 * (0.5 + 0.5 * fract(leaf.w * 3.7));
          // tumble while airborne (Bruno: rotation from position x elevation), spin about up by a seed
          float air = max(leaf.y, 0.0);
          float rz = sin(leaf.x * 3.0) * air, rx = sin(leaf.z * 3.0) * air, ry = leaf.w * 6.2832;
          transformed.xy = mat2(cos(rz), -sin(rz), sin(rz), cos(rz)) * transformed.xy;
          transformed.yz = mat2(cos(rx), -sin(rx), sin(rx), cos(rx)) * transformed.yz;
          transformed.xz = mat2(cos(ry), -sin(ry), sin(ry), cos(ry)) * transformed.xz;
          float ground = groundHeight(groundSample(leaf.xz));
          transformed += vec3(leaf.x, ground + 0.04 + leaf.y, leaf.z);
          vTint = tint;`)
        .replace('#include <project_vertex>', 'vec4 mvPosition = viewMatrix * vec4(transformed, 1.0);\ngl_Position = projectionMatrix * mvPosition;');
      s.fragmentShader = s.fragmentShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vTint;')
        .replace('#include <color_fragment>', '#include <color_fragment>\ndiffuseColor.rgb = vTint;');
    };
    const mesh = new THREE.Mesh(g, m);
    mesh.frustumCulled = false;
    return mesh;
  }, []);

  const prevCar = useMemo(() => new THREE.Vector3(1e9, 0, 0), []);
  const carV = useMemo(() => new THREE.Vector3(), []);
  useFrame((_, dtRaw) => {
    const dt = Math.min(dtRaw, 0.05);
    const cx = telemetry.x, cz = telemetry.z;
    if (prevCar.x > 1e8) carV.set(0, 0, 0);
    else carV.set((cx - prevCar.x) / Math.max(dt, 1e-3), 0, (cz - prevCar.z) / Math.max(dt, 1e-3));
    if (carV.lengthSq() > 2500) carV.set(0, 0, 0);   // a teleport / reset, not driving
    prevCar.set(cx, 0, cz);
    const speed = Math.min(carV.length(), 40);
    const wd = windUniforms.uWindDir.value, ws = windUniforms.uWindStrength.value;
    const { pos, vel, w, on, checked } = sim;
    const attr = mesh.geometry.getAttribute('leaf') as THREE.InstancedBufferAttribute;
    const a = attr.array as Float32Array;
    for (let i = 0; i < COUNT; i++) {
      const k = i * 3;
      // wrap around the car; a leaf landing in a new spot only shows on grass / dirt
      let wx = pos[k] - cx, wz = pos[k + 2] - cz, moved = false;
      if (wx > HALF_FIELD) { pos[k] -= 2 * HALF_FIELD; moved = true; } else if (wx < -HALF_FIELD) { pos[k] += 2 * HALF_FIELD; moved = true; }
      if (wz > HALF_FIELD) { pos[k + 2] -= 2 * HALF_FIELD; moved = true; } else if (wz < -HALF_FIELD) { pos[k + 2] += 2 * HALF_FIELD; moved = true; }
      if (moved || !checked[i]) {
        checked[i] = groundColorAt(pos[k], pos[k + 2], C) ? 1 : 0;
        on[i] = checked[i] && isGrass(C) ? 1 : 0;   // only on grass (where the trees are), not on sand or snow
        vel[k] = vel[k + 1] = vel[k + 2] = 0;
        pos[k + 1] = 0;
      }
      wx = pos[k] - cx; wz = pos[k + 2] - cz;
      const d = Math.hypot(wx, wz);
      // car push (Bruno: velocity push + sideways push, x speed, within 0.5 .. 2 m -> ours 1 .. 4 m for the bigger jeep)
      const near = Math.min(1, Math.max(0, (4 - d) / 3));
      if (near > 0 && speed > 1) {
        const sx = wx / (d || 1), sz = wz / (d || 1);
        vel[k] += (carV.x * 0.08 + sx * 1.5) * near * speed * dt * 6;
        vel[k + 2] += (carV.z * 0.08 + sz * 1.5) * near * speed * dt * 6;
      }
      // wind drift
      const gust = Math.max(0, ws - 0.25) * w[i] * 2;
      vel[k] += wd.x * gust * dt * 4;
      vel[k + 2] += wd.y * gust * dt * 4;
      // lift from horizontal speed, damping (high in the air), gravity
      const h = Math.hypot(vel[k], vel[k + 2]);
      vel[k + 1] = Math.min(h, 2) * Math.max(0, 1 - pos[k + 1] / 6) * 1.2 + (vel[k + 1] < 0 ? vel[k + 1] : 0);
      const damp = Math.min(1, (pos[k + 1] > 0.05 ? 1.5 : 3) * dt);
      vel[k] *= 1 - damp; vel[k + 2] *= 1 - damp;
      vel[k + 1] -= 9.807 * w[i] * dt * 4;
      pos[k] += vel[k] * dt; pos[k + 1] = Math.max(0, pos[k + 1] + vel[k + 1] * dt); pos[k + 2] += vel[k + 2] * dt;
      if (pos[k + 1] === 0 && vel[k + 1] < 0) vel[k + 1] = 0;
      a[i * 4] = pos[k];
      a[i * 4 + 1] = on[i] ? pos[k + 1] : -50;   // hidden: sunk below the ground
      a[i * 4 + 2] = pos[k + 2];
      if (a[i * 4 + 3] === 0) a[i * 4 + 3] = Math.random();
    }
    attr.needsUpdate = true;
  });

  return <primitive object={mesh} />;
}
