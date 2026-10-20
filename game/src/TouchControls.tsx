// Phone controls in the style of Mini Militia: a floating DRIVE stick for the left thumb (appears where you touch:
// up = gas, down = reverse, sideways = steer, all analog) and a LOOK stick for the right thumb that turns the chase
// camera. Brake and reset sit above the right stick. Writes to `analog` / `controls`, which the car reads every step.
import { useRef, useState, type CSSProperties, type PointerEvent as RPointerEvent } from 'react';
import { analog, setControl, useControlsSnapshot } from './controls';

const R = 58;   // stick travel radius (px)

type Stick = { id: number; ox: number; oy: number; x: number; y: number } | null;

function useStick(onMove: (x: number, y: number) => void) {
  const [s, setS] = useState<Stick>(null);
  const ref = useRef<Stick>(null);
  const set = (v: Stick) => { ref.current = v; setS(v); };
  const down = (e: RPointerEvent) => {
    if (ref.current) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    set({ id: e.pointerId, ox: e.clientX, oy: e.clientY, x: 0, y: 0 });
  };
  const move = (e: RPointerEvent) => {
    const c = ref.current;
    if (!c || c.id !== e.pointerId) return;
    let x = e.clientX - c.ox, y = e.clientY - c.oy;
    const l = Math.hypot(x, y);
    if (l > R) { x *= R / l; y *= R / l; }
    set({ ...c, x, y });
    // small dead zone, then a soft curve for finer control near the centre
    const curve = (v: number) => { const a = Math.max(0, Math.abs(v) - 0.12) / 0.88; return Math.sign(v) * a * a * (3 - 2 * a); };
    onMove(curve(x / R), curve(-y / R));
  };
  const up = (e: RPointerEvent) => {
    if (ref.current?.id !== e.pointerId) return;
    set(null);
    onMove(0, 0);
  };
  return { s, handlers: { onPointerDown: down, onPointerMove: move, onPointerUp: up, onPointerCancel: up } };
}

export function TouchControls() {
  const drive = useStick((x, y) => { analog.steer = -x; analog.throttle = y; });
  const look = useStick((x, y) => { analog.lookX = x; analog.lookY = -y; });
  const c = useControlsSnapshot();
  return (
    <>
      {/* left 45% of the screen: drive stick; right side: look stick */}
      <div style={{ ...zone, left: 0, width: '45%', top: 90 }} {...drive.handlers}>
        <StickView s={drive.s} hint="DRIVE" side="left" />
      </div>
      <div style={{ ...zone, right: 0, width: '45%', top: 140 }} {...look.handlers}>
        <StickView s={look.s} hint="LOOK" side="right" />
      </div>
      <div style={{ position: 'absolute', right: 24, bottom: 170, display: 'flex', gap: 12 }}>
        {(['brake', 'reset'] as const).map((ctl) => (
          <div
            key={ctl}
            onPointerDown={(e) => { e.stopPropagation(); e.currentTarget.setPointerCapture(e.pointerId); setControl(ctl, true); }}
            onPointerUp={() => setControl(ctl, false)}
            onPointerCancel={() => setControl(ctl, false)}
            style={{ ...button, background: c[ctl] ? 'rgba(216, 58, 44, 0.9)' : 'rgba(40, 30, 20, 0.55)' }}
          >
            {ctl === 'brake' ? 'BRAKE' : '↺'}
          </div>
        ))}
      </div>
    </>
  );
}

function StickView({ s, hint, side }: { s: Stick; hint: string; side: 'left' | 'right' }) {
  // idle: a faint stick in the corner shows where to put the thumb; active: base under the thumb, knob follows it
  const rest: CSSProperties = side === 'left' ? { left: 40, bottom: 40 } : { right: 40, bottom: 40 };
  const base: CSSProperties = s
    ? { left: s.ox - R - 8, top: s.oy - R - 8 }
    : rest;
  return (
    <div style={{ position: 'fixed', width: 2 * R + 16, height: 2 * R + 16, borderRadius: '50%', ...base, ...ring, opacity: s ? 0.9 : 0.45 }}>
      <div style={{ ...knob, transform: `translate(${s?.x ?? 0}px, ${s?.y ?? 0}px)` }} />
      {!s && <div style={label}>{hint}</div>}
    </div>
  );
}

const zone: CSSProperties = { position: 'absolute', bottom: 0, touchAction: 'none', userSelect: 'none' };   // below the HUD / minimap
const ring: CSSProperties = { background: 'rgba(40, 30, 20, 0.35)', border: '2px solid rgba(255, 255, 255, 0.55)', pointerEvents: 'none' };
const knob: CSSProperties = {
  position: 'absolute', left: R - 20, top: R - 20, width: 56, height: 56, borderRadius: '50%',
  background: 'rgba(255, 255, 255, 0.85)', boxShadow: '0 2px 8px rgba(0,0,0,0.35)',
};
const label: CSSProperties = { position: 'absolute', width: '100%', bottom: -22, textAlign: 'center', color: '#fff', font: '600 12px system-ui, sans-serif', textShadow: '0 1px 2px #000' };
const button: CSSProperties = {
  width: 72, height: 48, borderRadius: 12, display: 'grid', placeItems: 'center', color: '#fff',
  font: '700 14px system-ui, sans-serif', touchAction: 'none', userSelect: 'none', cursor: 'pointer',
};
