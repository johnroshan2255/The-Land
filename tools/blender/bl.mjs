// Client for the Blender MCP extension socket (localhost:9876).
// Protocol: JSON {"type":"execute","code":...,"strict_json":bool} terminated by a NUL byte;
// the code may assign `result` to return a value.
//
//   node bl.mjs a.py b.py [KEY=VALUE ...]   -> run Python files concatenated (KEY=VALUE become globals first)
//   node bl.mjs -e "<python code>"          -> run inline code
import net from 'node:net';
import fs from 'node:fs';

const args = process.argv.slice(2);
let code;
if (args[0] === '-e') code = args[1];
else {
  const header = args.filter((a) => a.includes('=') && !a.endsWith('.py')).map((kv) => {
    const i = kv.indexOf('=');
    return `${kv.slice(0, i)} = ${JSON.stringify(kv.slice(i + 1))}`;
  }).join('\n');
  code = header + '\n' + args.filter((a) => a.endsWith('.py')).map((f) => fs.readFileSync(f, 'utf8').replace(/^﻿/, '')).join('\n');
}

const socket = net.createConnection({ host: '127.0.0.1', port: 9876 });
const chunks = [];
socket.on('connect', () => {
  socket.write(JSON.stringify({ type: 'execute', code, strict_json: false }));
  socket.write(Buffer.from([0]));
});
socket.on('data', (d) => chunks.push(d));
socket.on('close', () => {
  const text = Buffer.concat(chunks).toString('utf8').replace(/\0+$/, '');
  try {
    const reply = JSON.parse(text);
    if (reply.stdout) process.stdout.write(reply.stdout.split('\n').filter((l) => l.trim() && !/\| INFO: |^INFO /.test(l)).join('\n') + '\n');
    if (reply.stderr) process.stderr.write(reply.stderr);
    if (reply.status !== 'ok') { console.error('ERROR:', reply.message); process.exitCode = 1; }
    else if (reply.result !== undefined && reply.result !== null) console.log(typeof reply.result === 'string' ? reply.result : JSON.stringify(reply.result, null, 1));
  } catch {
    console.log(text);
  }
});
socket.on('error', (e) => { console.error('socket error:', e.message); process.exitCode = 1; });
