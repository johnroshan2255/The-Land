// Day/night cycle: one directional light (sun by day, moon by night), a hemisphere light, a cheap gradient sky dome and
// fog matched to the horizon (skill: 1 hemi + 1 directional, sky = MeshBasic-style dome with fog off and depthWrite off,
// fog color = horizon color). No shadow maps: `sun` below drives the fake shadows (baked terrain texture, car image).
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame, useThree } from '@react-three/fiber';
import { PRESET, telemetry } from './state';

export const DAY_SECONDS = 720;   // one full day in real seconds at normal speed

/** Light direction (unit vector toward the sun/moon) and how dark fake shadows should be right now (0..1). */
export const sun = { x: 0, y: 1, z: 0, shadow: 0.8 };

// Palette keyed by sun elevation (-1..1), tuned to the warm golden-hour reference shots.
type Key = { e: number; horizon: string; zenith: string; hemiSky: string; hemiGround: string; sun: string; sunI: number; hemiI: number; shadow: number };
const KEYS: Key[] = [
  // Toon shading (toonShading.ts, after Bruno Simon's folio-2025): `sun` x sunI is the lit tint, `hemiSky` x hemiI the
  // SHADOW tint (the colour a surface turns as it faces away from the sun). Intensities are x PI (three's Lambert / PI).
  { e: -0.35, horizon: '#1d2a50', zenith: '#0a1029', hemiSky: '#3a1ee0', hemiGround: '#000000', sun: '#6a78ff', sunI: 1.5 * Math.PI, hemiI: 0.55 * Math.PI, shadow: 0.35 },   // night
  { e: -0.05, horizon: '#7a5f8c', zenith: '#2c3566', hemiSky: '#5a14b0', hemiGround: '#000000', sun: '#ff8a8a', sunI: 1.0 * Math.PI, hemiI: 0.8 * Math.PI, shadow: 0.3 },    // dusk
  { e: 0.08, horizon: '#ffb98a', zenith: '#4f9be8', hemiSky: '#a8448c', hemiGround: '#000000', sun: '#ffb08a', sunI: 1.2 * Math.PI, hemiI: Math.PI, shadow: 0.75 },      // sunrise / sunset
  { e: 0.35, horizon: '#ffd9a8', zenith: '#3f96ee', hemiSky: '#7b5cff', hemiGround: '#000000', sun: '#ffd8c6', sunI: 1.2 * Math.PI, hemiI: Math.PI, shadow: 0.85 },     // golden afternoon
  { e: 1.0, horizon: '#cfe6f6', zenith: '#3a90ec', hemiSky: '#8068ff', hemiGround: '#000000', sun: '#ffeadc', sunI: 1.25 * Math.PI, hemiI: Math.PI, shadow: 0.88 },       // noon
];

const ca = new THREE.Color();
const cb = new THREE.Color();
function segment(elev: number) {
  let k = 0;
  while (k < KEYS.length - 2 && elev > KEYS[k + 1].e) k++;
  const a = KEYS[k], b = KEYS[k + 1];
  return { a, b, t: THREE.MathUtils.clamp((elev - a.e) / (b.e - a.e), 0, 1) };
}
function color(elev: number, f: 'horizon' | 'zenith' | 'hemiSky' | 'hemiGround' | 'sun', out: THREE.Color) {
  const { a, b, t } = segment(elev);
  return out.copy(ca.set(a[f])).lerp(cb.set(b[f]), t);
}
function num(elev: number, f: 'sunI' | 'hemiI' | 'shadow') {
  const { a, b, t } = segment(elev);
  return a[f] + (b[f] - a[f]) * t;
}

const skyVert = /* glsl */ `
varying vec3 vDir;
void main() {
  vDir = normalize(position);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;
const skyFrag = /* glsl */ `
uniform vec3 uHorizon;
uniform vec3 uZenith;
varying vec3 vDir;
void main() {
  float h = clamp(vDir.y, 0.0, 1.0);
  gl_FragColor = vec4(mix(uHorizon, uZenith, pow(h, 0.55)), 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

export function DayNight() {
  const { scene, camera } = useThree();
  const light = useRef<THREE.DirectionalLight>(null);
  const hemi = useRef<THREE.HemisphereLight>(null);
  const dome = useRef<THREE.Mesh>(null);
  const horizon = useMemo(() => new THREE.Color(), []);
  const dir = useMemo(() => new THREE.Vector3(), []);
  const skyMat = useMemo(
    () => new THREE.ShaderMaterial({
      uniforms: { uHorizon: { value: new THREE.Color() }, uZenith: { value: new THREE.Color() } },
      vertexShader: skyVert, fragmentShader: skyFrag, side: THREE.BackSide, depthWrite: false, fog: false,
    }),
    [],
  );

  useEffect(() => {
    scene.background = horizon;
    scene.fog = new THREE.Fog(horizon, PRESET.fogFar * 0.4, PRESET.fogFar);
    (camera as THREE.PerspectiveCamera).far = PRESET.fogFar + 50;   // everything past the fog is frustum-culled
    camera.updateProjectionMatrix();
    const keys = (e: KeyboardEvent) => {
      if (e.code === 'KeyT') telemetry.timeScale = telemetry.timeScale === 1 ? 24 : 1;
    };
    window.addEventListener('keydown', keys);
    return () => window.removeEventListener('keydown', keys);
  }, [scene, camera, horizon]);

  useFrame((_, dt) => {
    telemetry.timeOfDay = (telemetry.timeOfDay + (dt * telemetry.timeScale * 24) / DAY_SECONDS) % 24;
    // sun path: rises in the east (+x), high in the south (+z) at noon, sets in the west
    const a = ((telemetry.timeOfDay - 6) / 24) * Math.PI * 2;
    const elev = Math.sin(a);
    dir.set(Math.cos(a), Math.max(Math.sin(a), 0) * 0.9 + 0.12, 0.45).normalize();
    if (elev < -0.05) dir.set(-Math.cos(a), Math.max(-Math.sin(a), 0) * 0.9 + 0.25, 0.3).normalize();   // moon opposite the sun
    color(elev, 'horizon', horizon);
    if (scene.fog) (scene.fog as THREE.Fog).color.copy(horizon);
    skyMat.uniforms.uHorizon.value.copy(horizon);
    color(elev, 'zenith', skyMat.uniforms.uZenith.value);
    if (dome.current) dome.current.position.copy(camera.position);
    sun.x = dir.x;
    sun.y = dir.y;
    sun.z = dir.z;
    sun.shadow = num(elev, 'shadow');
    const l = light.current, h = hemi.current;
    if (l) {
      color(elev, 'sun', l.color);
      l.intensity = num(elev, 'sunI');
      l.position.copy(dir);   // a directional light only needs a direction (target stays at the origin)
    }
    if (h) {
      color(elev, 'hemiSky', h.color);
      color(elev, 'hemiGround', h.groundColor);
      h.intensity = num(elev, 'hemiI');
    }
  });

  return (
    <>
      {/* drawn after the opaque world (renderOrder 1) and depth-tested, so it only shades the pixels that are actually sky
          instead of the whole screen; radius just past the fog end, inside camera.far */}
      <mesh ref={dome} material={skyMat} renderOrder={1} frustumCulled={false}>
        <sphereGeometry args={[PRESET.fogFar + 30, 24, 12]} />
      </mesh>
      <hemisphereLight ref={hemi} />
      <directionalLight ref={light} />
    </>
  );
}

export function isNight() {
  const a = ((telemetry.timeOfDay - 6) / 24) * Math.PI * 2;
  return Math.sin(a) < 0.02;
}
