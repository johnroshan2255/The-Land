import { Suspense, useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import './toonShading';   // patches the Lambert shader: must run before any material compiles
import { Canvas, addAfterEffect, addEffect, useFrame, useThree } from '@react-three/fiber';
import { Physics } from '@react-three/rapier';
import { World } from './World';
import { Car } from './Car';
import { Smoke } from './Smoke';
import { DayNight } from './DayNight';
import { Hud } from './Hud';
import { PRESET, TIER, telemetry } from './state';
import { QualityManager } from './vendor/QualityManager';

// Note: nothing here holds per-frame React state. Speed/FPS live in `telemetry` and the HUD polls it,
// so the <Canvas> tree is never re-rendered while driving (that used to happen 60x a second).
export function App() {
  return (
    <>
      <Canvas
        frameloop={PRESET.targetFps < 60 ? 'never' : 'always'}
        dpr={Math.min(window.devicePixelRatio, PRESET.maxPixelRatio)}
        gl={{ antialias: PRESET.antialias, powerPreference: 'high-performance', stencil: false, alpha: false }}
        camera={{ fov: 55, near: 0.5, far: PRESET.fogFar + 50, position: [450, 120, 450] }}
        onCreated={({ gl }) => {
          // low tier: no tone mapping (skill); medium/high: Neutral keeps the warm stylized colors saturated
          gl.toneMapping = TIER === 'low' ? THREE.NoToneMapping : THREE.NeutralToneMapping;
          gl.toneMappingExposure = 1.0;
        }}
      >
        <Suspense fallback={null}>
          <Runtime />
          <DayNight />
          <Physics gravity={[0, -9.81, 0]} timeStep={1 / 60}>
            <World />
            <Car />
          </Physics>
          <Smoke />
        </Suspense>
      </Canvas>
      <Hud tier={TIER} />
    </>
  );
}

/**
 * Frame pacing + quality (lowend-webgl-optimization skill): adaptive pixel ratio from QualityManager,
 * a 30 fps lock on the low tier, pause while the tab is hidden, shader precompile, FPS / draw-call readout.
 */
function Runtime() {
  const { gl, scene, camera, setDpr, advance, set } = useThree();
  const quality = useMemo(
    () => new QualityManager({ getContext: () => gl.getContext(), setPixelRatio: (v: number) => setDpr(v) }, TIER),
    [gl, setDpr],
  );

  useEffect(() => {
    gl.info.autoReset = false;
    gl.compileAsync?.(scene, camera).catch(() => {});
    const vis = () => set({ frameloop: document.hidden ? 'never' : PRESET.targetFps < 60 ? 'never' : 'always' });
    document.addEventListener('visibilitychange', vis);
    // low tier: drive the loop ourselves at 30 fps
    let raf = 0;
    if (PRESET.targetFps < 60) {
      const tick = (t: number) => {
        raf = requestAnimationFrame(tick);
        if (!document.hidden && !quality.shouldSkipFrame(t)) advance(t);
      };
      raf = requestAnimationFrame(tick);
    }
    return () => {
      document.removeEventListener('visibilitychange', vis);
      cancelAnimationFrame(raf);
    };
  }, [gl, scene, camera, set, advance, quality]);

  const acc = useRef({ frames: 0, time: 0 });
  useFrame((_, dt) => {
    // frames > 250 ms only happen when the browser throttles a background/occluded tab: never let those
    // downgrade (and persist) the quality tier
    if (dt < 0.25) quality.update(performance.now());
    acc.current.frames++;
    acc.current.time += dt;
    if (acc.current.time >= 0.5) {
      telemetry.fps = Math.round(acc.current.frames / acc.current.time);
      telemetry.drawCalls = gl.info.render.calls;
      telemetry.triangles = gl.info.render.triangles;
      telemetry.dpr = quality.pixelRatio;
      acc.current.frames = 0;
      acc.current.time = 0;
    }
    gl.info.reset();
  });
  return null;
}

// Dev-only frame timer: whole-frame CPU cost (physics + game logic + render submission), read via window.__frames.
if (import.meta.env.DEV) {
  const frames: number[] = [];
  let start = 0;
  addEffect(() => {
    start = performance.now();
  });
  addAfterEffect(() => {
    frames.push(performance.now() - start);
    if (frames.length > 5000) frames.shift();
  });
  Object.assign(window, { __frames: frames });
}
