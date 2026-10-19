// Day/night cycle: one directional light (sun by day, moon by night) that follows the car with a tight shadow frustum,
// a hemisphere light, a cheap gradient sky dome and fog matched to the horizon (skill: 1 hemi + 1 directional,
// sky = MeshBasic-style dome with fog off and depthWrite off, fog color = horizon color).
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame, useThree } from '@react-three/fiber';
import { PRESET, telemetry } from './state';

export const DAY_SECONDS = 720;   // one full day in real seconds at normal speed

// Palette keyed by sun elevation (-1..1), tuned to the warm golden-hour reference shots.
type Key = { e: number; horizon: string; zenith: string; hemiSky: string; hemiGround: string; sun: string; sunI: number; hemiI: number };
const KEYS: Key[] = [
  { e: -0.35, horizon: '#1d2a50', zenith: '#0a1029', hemiSky: '#5a72b4', hemiGround: '#232a3a', sun: '#a9c0ff', sunI: 0.75, hemiI: 0.75 },   // night
  { e: -0.05, horizon: '#7a5f8c', zenith: '#2c3566', hemiSky: '#8a7bb0', hemiGround: '#3e2f36', sun: '#d0a8ff', sunI: 0.25, hemiI: 0.6 },    // dusk
  { e: 0.08, horizon: '#ffcf9a', zenith: '#7db3e3', hemiSky: '#ffe2bd', hemiGround: '#b8956a', sun: '#ffc98a', sunI: 2.2, hemiI: 1.0 },      // sunrise / sunset
  { e: 0.35, horizon: '#f8e2bc', zenith: '#86c1ee', hemiSky: '#fff3e0', hemiGround: '#c8ad85', sun: '#ffe6c0', sunI: 2.6, hemiI: 1.15 },     // golden afternoon
  { e: 1.0, horizon: '#e6eef3', zenith: '#78b6ea', hemiSky: '#f3f8ff', hemiGround: '#c0aa88', sun: '#fff3de', sunI: 2.7, hemiI: 1.1 },       // noon
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
function num(elev: number, f: 'sunI' | 'hemiI') {
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
    const l = light.current, h = hemi.current;
    if (l) {
      color(elev, 'sun', l.color);
      l.intensity = num(elev, 'sunI');
      l.position.set(telemetry.x + dir.x * 120, telemetry.y + dir.y * 120, telemetry.z + dir.z * 120);
      l.target.position.set(telemetry.x, telemetry.y, telemetry.z);
      l.target.updateMatrixWorld();
    }
    if (h) {
      color(elev, 'hemiSky', h.color);
      color(elev, 'hemiGround', h.groundColor);
      h.intensity = num(elev, 'hemiI');
    }
  });

  const size = PRESET.shadowMapSize || 512;
  return (
    <>
      <mesh ref={dome} material={skyMat} renderOrder={-1} frustumCulled={false}>
        <sphereGeometry args={[PRESET.fogFar * 0.9, 24, 12]} />
      </mesh>
      <hemisphereLight ref={hemi} />
      <directionalLight
        ref={light}
        castShadow={PRESET.shadows === 'directional'}
        shadow-mapSize={[size, size]}
        shadow-camera-left={-45}
        shadow-camera-right={45}
        shadow-camera-top={45}
        shadow-camera-bottom={-45}
        shadow-camera-near={1}
        shadow-camera-far={300}
        shadow-bias={-0.0006}
        shadow-normalBias={0.04}
      />
    </>
  );
}

export function isNight() {
  const a = ((telemetry.timeOfDay - 6) / 24) * Math.PI * 2;
  return Math.sin(a) < 0.02;
}
