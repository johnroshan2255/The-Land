// Shared driving input: keyboard (WASD / arrows) and the on-screen pad both write here, the car reads it.
import { useEffect, useState } from 'react';

export type Control = 'fwd' | 'back' | 'left' | 'right' | 'brake' | 'reset';
export const controls: Record<Control, boolean> = { fwd: false, back: false, left: false, right: false, brake: false, reset: false };

const listeners = new Set<() => void>();
export function setControl(c: Control, on: boolean) {
  if (controls[c] === on) return;
  controls[c] = on;
  listeners.forEach((l) => l());
}

const BY_CODE: Record<string, Control> = {
  KeyW: 'fwd', ArrowUp: 'fwd', KeyS: 'back', ArrowDown: 'back', KeyA: 'left', ArrowLeft: 'left',
  KeyD: 'right', ArrowRight: 'right', Space: 'brake', KeyR: 'reset',
};
const BY_KEY: Record<string, Control> = { w: 'fwd', s: 'back', a: 'left', d: 'right', r: 'reset', ' ': 'brake' };

export function useKeyboardControls() {
  useEffect(() => {
    const handle = (on: boolean) => (e: KeyboardEvent) => {
      const c = BY_CODE[e.code] ?? BY_KEY[e.key.toLowerCase()];
      if (!c) return;
      setControl(c, on);
      e.preventDefault();
    };
    const down = handle(true);
    const up = handle(false);
    const release = () => (Object.keys(controls) as Control[]).forEach((c) => setControl(c, false));
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    window.addEventListener('blur', release);   // don't keep driving after alt-tab
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
      window.removeEventListener('blur', release);
    };
  }, []);
}

/** Re-renders when any control changes (for the on-screen pad highlight). */
export function useControlsSnapshot() {
  const [, bump] = useState(0);
  useEffect(() => {
    const l = () => bump((n) => n + 1);
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, []);
  return controls;
}
