// HTML overlay: info box, on-screen WASD, minimap (top-right) and the full map (click minimap or press M).
// The car marker is moved from telemetry at 10 Hz through refs - no React re-render per frame.
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { HALF, telemetry } from './state';
import { setControl, useControlsSnapshot, type Control } from './controls';
import type { Tier } from './vendor/QualityManager';

const MAP = '/models/terrain/map.png';

export function Hud({ tier }: { tier: Tier }) {
  const [bigMap, setBigMap] = useState(false);
  const [clock, setClock] = useState('');
  const [readout, setReadout] = useState('');
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.code === 'KeyM') setBigMap((b) => !b);
      if (e.code === 'Escape') setBigMap(false);
    };
    window.addEventListener('keydown', key);
    const id = setInterval(() => {
      const h = Math.floor(telemetry.timeOfDay);
      const m = Math.floor((telemetry.timeOfDay - h) * 60);
      setClock(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}${telemetry.timeScale > 1 ? ' ⏩' : ''}`);
      const t = telemetry;
      setReadout(`${Math.round(Math.abs(t.speed) * 3.6)} km/h · ${t.fps} FPS · ${t.drawCalls} draws · ${Math.round(t.triangles / 1000)}k tris · ${tier} @ ${t.dpr.toFixed(2)}x`);
    }, 200);
    return () => {
      window.removeEventListener('keydown', key);
      clearInterval(id);
    };
  }, [tier]);

  return (
    <>
      <div style={info}>
        <b>Island Drive</b> · {clock}
        <br />W / S drive · A / D steer · Space brake · R reset · drag mouse to look, wheel to zoom · M map · T fast time
        <br />
        {readout}
      </div>
      <MapView size={190} style={{ position: 'absolute', right: 16, top: 16, cursor: 'pointer' }} onClick={() => setBigMap(true)} />
      {bigMap && (
        <div style={overlay} onClick={() => setBigMap(false)}>
          <MapView size={Math.min(window.innerWidth, window.innerHeight) * 0.86} style={{}} />
          <div style={{ position: 'absolute', bottom: 18, color: '#fff', font: '14px system-ui, sans-serif' }}>Click anywhere or press M / Esc to close</div>
        </div>
      )}
      <WasdPad />
    </>
  );
}

/** The whole island map with a live car arrow (north up). */
function MapView({ size, style, onClick }: { size: number; style: CSSProperties; onClick?: () => void }) {
  const marker = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const id = setInterval(() => {
      const m = marker.current;
      if (!m) return;
      const u = (telemetry.x + HALF) / (2 * HALF);
      const v = (telemetry.z + HALF) / (2 * HALF);   // map top = north = -z
      m.style.transform = `translate(${u * size - 9}px, ${v * size - 9}px) rotate(${telemetry.heading}rad)`;
    }, 100);
    return () => clearInterval(id);
  }, [size]);
  return (
    <div onClick={onClick} style={{ position: 'relative', ...style, width: size, height: size, borderRadius: 12, overflow: 'hidden', boxShadow: '0 4px 16px rgba(0,0,0,0.35)', border: '3px solid rgba(255,255,255,0.85)', background: `url(${MAP}) center / cover`, flex: 'none' }}>
      <div ref={marker} style={{ position: 'absolute', width: 18, height: 18, transformOrigin: '9px 9px' }}>
        <svg viewBox="0 0 18 18" width="18" height="18"><path d="M9 1 L16 16 L9 12 L2 16 Z" fill="#d83a2c" stroke="#fff" strokeWidth="1.5" /></svg>
      </div>
    </div>
  );
}

const PAD: [Control, string, number, number][] = [['fwd', 'W', 1, 0], ['left', 'A', 0, 1], ['back', 'S', 1, 1], ['right', 'D', 2, 1]];

// On-screen WASD: lights up with the keyboard, and can be pressed with mouse or touch.
function WasdPad() {
  const c = useControlsSnapshot();
  return (
    <div style={{ position: 'absolute', right: 20, bottom: 20, display: 'grid', gridTemplateColumns: 'repeat(3, 56px)', gap: 6, touchAction: 'none', userSelect: 'none' }}>
      {PAD.map(([ctl, label, col, row]) => (
        <div
          key={ctl}
          onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); setControl(ctl, true); }}
          onPointerUp={() => setControl(ctl, false)}
          onPointerCancel={() => setControl(ctl, false)}
          style={{
            gridColumn: col + 1, gridRow: row + 1, height: 56, borderRadius: 10, display: 'grid', placeItems: 'center',
            font: '600 20px system-ui, sans-serif', color: '#fff', cursor: 'pointer',
            background: c[ctl] ? 'rgba(216, 58, 44, 0.9)' : 'rgba(40, 30, 20, 0.55)',
          }}
        >
          {label}
        </div>
      ))}
    </div>
  );
}

const info: CSSProperties = {
  position: 'absolute', left: 16, top: 16, padding: '10px 14px', borderRadius: 10, maxWidth: 'calc(100vw - 260px)',
  background: 'rgba(40, 30, 20, 0.55)', color: '#fff', font: '13px/1.6 system-ui, sans-serif', pointerEvents: 'none',
};
const overlay: CSSProperties = {
  position: 'absolute', inset: 0, background: 'rgba(10, 12, 20, 0.6)', display: 'grid', placeItems: 'center', cursor: 'pointer',
};
