// Copy the Blender exports and the Draco decoder into public/ (run automatically before dev/build).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const game = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const models = path.resolve(game, '..', 'models');
const copies = [[path.join(models, 'red_jeep', 'red_jeep_game.glb'), 'public/models/red_jeep_game.glb']];
const terrain = path.join(models, 'terrain', 'game');
for (const f of fs.readdirSync(terrain)) copies.push([path.join(terrain, f), `public/models/terrain/${f}`]);
const bruno = path.join(models, 'bruno');   // Bruno Simon's folio-2025 assets (MIT, see models/bruno/LICENSE.md)
for (const f of fs.readdirSync(bruno)) if (!f.endsWith('.md')) copies.push([path.join(bruno, f), `public/models/bruno/${f}`]);
const draco = path.join(game, 'node_modules', 'three', 'examples', 'jsm', 'libs', 'draco', 'gltf');
for (const f of fs.readdirSync(draco)) copies.push([path.join(draco, f), `public/draco/${f}`]);
for (const [src, rel] of copies) {
  const dst = path.join(game, rel);
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.copyFileSync(src, dst);
}
fs.rmSync(path.join(game, 'public/models/island_master.glb'), { force: true });   // replaced by the chunked terrain
console.log(`synced ${copies.length} files into public/`);
