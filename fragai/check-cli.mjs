import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const inputs = JSON.parse(fs.readFileSync(path.join(root, 'fragai/build-inputs.lock.json')));
const image = process.argv[2];
assert.ok(image, 'Supply the owned CLI image.');
const docker = (...args) => execFileSync('docker', args, { encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 });
const run = (ref, ...args) => docker('run', '--rm', '--network', 'none', '--entrypoint', 'sh', ref, '-c', args.join(' '));
const baseline = inputs.cliBaseline;
const oldConfig = JSON.parse(docker('image', 'inspect', baseline))[0].Config;
const newConfig = JSON.parse(docker('image', 'inspect', image))[0].Config;
for (const key of ['Entrypoint', 'Cmd', 'WorkingDir', 'User', 'ExposedPorts', 'Volumes']) assert.deepEqual(newConfig[key], oldConfig[key], key);
assert.ok(run(image, 'cat /etc/os-release').includes('wolfi'));
assert.ok(run(baseline, 'cat /etc/os-release').includes('wolfi'));
for (const ref of [baseline, image]) {
  assert.equal(run(ref, 'id -u').trim(), '1000');
  run(ref, 'command -v apk');
  run(ref, 'nanobot run --help');
}
assert.equal(run(image, 'mcp-cli --version'), run(baseline, 'mcp-cli --version'));
assert.equal(run(image, 'uv --version').split(' (')[0].trim(), run(baseline, 'uv --version').split(' (')[0].trim());
assert.equal(run(image, 'cd /var/cache/tiktoken && sha256sum *'), run(baseline, 'cd /var/cache/tiktoken && sha256sum *'));
console.log('Verified CLI/sandbox OS, package manager, UID, image contract, flags, MCP CLI, UV and tokenizer parity.');
