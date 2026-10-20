// Dense grass field around the car, after Bruno Simon's folio-2025 Grass.js (MIT licence): one triangle per blade on
// a jittered grid that wraps around the car as it drives, turned to face the camera, swaying in the wind, dark at the
// root (toon shade) and bright at the tip. All placement happens in the vertex shader, so it costs one draw call.
//
// His world is flat; ours is not. So every ~30 m of driving the terrain chunks under the car are rendered once from
// above into a small "ground" texture: R,G = height (16 bit), B = how much grass grows there (green ground; roads,
// sand, snow and rock read as 0). The blades read it in the vertex shader to stand on the ground, and only on grass.
import { useEffect, useMemo } from 'react';
import * as THREE from 'three';
import { useFrame, useThree } from '@react-three/fiber';
import { PRESET, telemetry } from './state';
import { updateWind, windGLSL, windUniforms } from './wind';

const TIERS = { low: { side: 110, half: 24 }, medium: { side: 170, half: 32 }, high: { side: 240, half: 40 } };
const { side: SIDE, half: HALF_FIELD } = TIERS[PRESET.tier];
const WIN = 160;          // ground capture window (m), re-captured when the car is RECAPTURE m from its centre
const RECAPTURE = 30;
const RES = PRESET.tier === 'low' ? 256 : 512;
const RANGE = 160;        // height range encoded in the capture (m), centred on the car

const captureMaterial = new THREE.ShaderMaterial({
  vertexColors: true,
  uniforms: { uBase: { value: 0 } },
  vertexShader: /* glsl */ `
    varying float vH; varying vec3 vCol;
    void main() {
      vec4 wp = modelMatrix * vec4(position, 1.0);
      vH = wp.y; vCol = color.rgb;
      gl_Position = projectionMatrix * viewMatrix * wp;
    }`,
  fragmentShader: /* glsl */ `
    uniform float uBase;
    varying float vH; varying vec3 vCol;
    void main() {
      float h = floor(clamp((vH - uBase) / ${RANGE.toFixed(1)}, 0.0, 1.0) * 65535.0);
      float hi = floor(h / 256.0);
      float green = smoothstep(0.03, 0.12, vCol.g - max(vCol.r, vCol.b));   // grass is green-dominant (linear colours)
      gl_FragColor = vec4(hi / 255.0, (h - hi * 256.0) / 255.0, green, 1.0);
    }`,
});

function bladeGeometry() {
  const n = SIDE * SIDE, cell = (2 * HALF_FIELD) / SIDE;
  const pos = new Float32Array(n * 9), rnd = new Float32Array(n * 3);
  for (let i = 0; i < SIDE; i++) {
    for (let j = 0; j < SIDE; j++) {
      const k = i * SIDE + j;
      const x = -HALF_FIELD + (i + Math.random()) * cell, z = -HALF_FIELD + (j + Math.random()) * cell;
      const r = Math.random();
      for (let c = 0; c < 3; c++) {   // x, corner (0 tip, 1 left, 2 right), z
        pos.set([x, c, z], k * 9 + c * 3);
        rnd[k * 3 + c] = r;
      }
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('rnd', new THREE.BufferAttribute(rnd, 1));
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e6);
  return g;
}

/** The ground capture, shared with other shaders that need to stand on the terrain near the car (leaves). */
export const groundUniforms = {
  uGround: { value: null as THREE.Texture | null }, uWinC: { value: new THREE.Vector2(1e9, 1e9) }, uBase: { value: 0 },
};
export const groundGLSL = /* glsl */ `
uniform sampler2D uGround; uniform vec2 uWinC; uniform float uBase;
vec4 groundSample(vec2 wp) { return texture2D(uGround, vec2((wp.x - uWinC.x) / ${WIN.toFixed(1)} + 0.5, 0.5 - (wp.y - uWinC.y) / ${WIN.toFixed(1)})); }
float groundHeight(vec4 g) { return uBase + (g.r * 65280.0 + g.g * 255.0) / 65535.0 * ${RANGE.toFixed(1)}; }`;

export function Grass({ chunks }: { chunks: { lod0: THREE.Mesh }[] }) {
  const { gl } = useThree();
  const rt = useMemo(() => new THREE.WebGLRenderTarget(RES, RES, { minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: true }), []);
  const cap = useMemo(() => {
    const scene = new THREE.Scene();
    for (const c of chunks) {
      const m = new THREE.Mesh(c.lod0.geometry, captureMaterial);
      m.position.copy(c.lod0.position);
      m.updateMatrixWorld();
      scene.add(m);
    }
    const cam = new THREE.OrthographicCamera(-WIN / 2, WIN / 2, WIN / 2, -WIN / 2, 1, 2000);
    cam.up.set(0, 0, -1);   // screen up = north (-z): texture v grows toward -z
    return { scene, cam, centre: new THREE.Vector2(1e9, 1e9) };
  }, [chunks]);

  const uniforms = useMemo(() => {
    groundUniforms.uGround.value = rt.texture;
    return { ...groundUniforms, ...windUniforms, uCenter: { value: new THREE.Vector2() }, uTime: { value: 0 } };
  }, [rt]);

  const mesh = useMemo(() => {
    const mat = new THREE.MeshLambertMaterial({ color: '#ffffff', side: THREE.DoubleSide });
    mat.onBeforeCompile = (s) => {
      Object.assign(s.uniforms, uniforms);
      s.vertexShader = s.vertexShader
        .replace('#include <common>', /* glsl */ `#include <common>
          ${groundGLSL} ${windGLSL}
          uniform vec2 uCenter; uniform float uTime;
          attribute float rnd; varying float vTip; varying vec3 vTint;`)
        .replace('#include <beginnormal_vertex>', 'vec3 objectNormal = vec3(0.0, 1.0, 0.0);')
        .replace('#include <begin_vertex>', /* glsl */ `
          float hf = ${HALF_FIELD.toFixed(1)};
          vec2 loopPos = mod(position.xz - uCenter + hf, 2.0 * hf) - hf;   // wrap the field around the car
          vec2 wp = uCenter + loopPos;
          vec4 g = groundSample(wp);
          float ground = groundHeight(g);
          float patchN = sin(wp.x * 0.11 + sin(wp.y * 0.07) * 2.0) * sin(wp.y * 0.09 + 1.3) * 0.5 + 0.5;   // tall / short patches
          float fade = smoothstep(hf, hf * 0.6, length(loopPos));
          float h = (0.75 - 0.3 * step(0.97, fract(rnd * 37.13))) * (0.45 + 0.55 * rnd) * (0.6 + 0.8 * patchN) * smoothstep(0.35, 0.8, g.b) * fade;
          float corner = position.y;
          float tip = step(corner, 0.5);
          vec2 dir = normalize(wp - cameraPosition.xz + 1e-4);
          vec2 sideV = vec2(-dir.y, dir.x) * 0.11 * (corner < 1.5 ? 1.0 : -1.0) * (1.0 - tip) * step(0.001, h);
          vec2 wind = windOffset(wp) * tip * h * 2.0;   // Bruno: wind x tipness x height x 2
          vec3 transformed = vec3(wp.x + sideV.x + wind.x, ground + tip * h, wp.y + sideV.y + wind.y);
          vTip = tip;
          vTint = mix(vec3(0.20, 0.42, 0.07), vec3(0.36, 0.50, 0.06), patchN * 0.7 + rnd * 0.3);   // linear: deep meadow green .. sunny yellow-green
          // ~3% of blades are short flowers: pink, white or yellow tips scattered through the meadow
          float flower = step(0.97, fract(rnd * 37.13));
          vec3 petal = fract(rnd * 91.7) < 0.4 ? vec3(0.95, 0.22, 0.42) : (fract(rnd * 91.7) < 0.7 ? vec3(0.95, 0.92, 0.88) : vec3(1.0, 0.72, 0.08));
          vTint = mix(vTint, petal, flower * tip);`)
        .replace('#include <project_vertex>', 'vec4 mvPosition = viewMatrix * vec4(transformed, 1.0);\ngl_Position = projectionMatrix * mvPosition;');
      s.fragmentShader = s.fragmentShader
        .replace('#include <common>', '#include <common>\nvarying float vTip; varying vec3 vTint;')
        .replace('#include <color_fragment>', '#include <color_fragment>\ndiffuseColor.rgb *= vTint;')
        // blades are lit as if they were the ground (always "up"), on both faces
        .replace('#include <normal_fragment_maps>', '#include <normal_fragment_maps>\nnormal = normalize((viewMatrix * vec4(0.0, 1.0, 0.0, 0.0)).xyz);')
        .replace('#include <aomap_fragment>', '#include <aomap_fragment>\ntoonDrop = max(toonDrop, (1.0 - vTip) * 0.85);   // dark root');
    };
    const m = new THREE.Mesh(bladeGeometry(), mat);
    m.frustumCulled = false;
    return m;
  }, [uniforms]);

  useEffect(() => {
    if (import.meta.env.DEV) Object.assign(window, { __grass: { rt, gl, mesh, uniforms, cap } });   // debugging hook
  }, [rt, gl, mesh, uniforms, cap]);

  useEffect(() => () => {
    rt.dispose();
    mesh.geometry.dispose();
    (mesh.material as THREE.Material).dispose();
  }, [rt, mesh]);

  useFrame((_, dt) => {
    const x = telemetry.x, z = telemetry.z;
    uniforms.uCenter.value.set(x, z);
    uniforms.uTime.value += dt;
    updateWind(dt);   // the one shared wind clock (grass, foliage, leaves)
    const midH = captureMaterial.uniforms.uBase.value + RANGE / 2;
    if (Math.hypot(x - cap.centre.x, z - cap.centre.y) > RECAPTURE || Math.abs(telemetry.y - midH) > RANGE * 0.3) {
      cap.centre.set(x, z);
      const base = telemetry.y - RANGE / 2;
      captureMaterial.uniforms.uBase.value = base;
      cap.cam.position.set(x, 1000, z);
      cap.cam.lookAt(x, 0, z);
      cap.cam.updateMatrixWorld();
      const prev = gl.getRenderTarget();
      gl.setRenderTarget(rt);
      gl.setClearColor(0x000000, 0);
      gl.clear();
      gl.render(cap.scene, cap.cam);
      gl.setRenderTarget(prev);
      groundUniforms.uWinC.value.set(x, z);
      groundUniforms.uBase.value = base;
    }
  });

  return <primitive object={mesh} />;
}
