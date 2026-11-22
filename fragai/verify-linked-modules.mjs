import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const image = process.argv[2];
assert.ok(image, 'Supply the candidate image.');
function parse(text) {
  const modules = new Map();
  let current;
  for (const line of text.split('\n')) {
    const parts = line.trim().split(/\s+/);
    if (parts[0] === 'dep') {
      current = { version: parts[2], checksum: parts[3] || '' };
      modules.set(parts[1], current);
    } else if (parts[0] === '=>' && current) {
      current.replacement = parts.slice(1).join(' ');
    }
  }
  return modules;
}
const baseline = parse(fs.readFileSync(path.join(root, 'fragai/baselines/go-build-info.txt'), 'utf8'));
const actualText = execFileSync('docker', ['run', '--rm', '--network', 'none', '--entrypoint', 'cat', image, '/usr/local/share/fragai/build-info.txt'], { encoding: 'utf8' });
const actual = parse(actualText);
assert.equal(actual.size, baseline.size, 'The linked dependency set must remain identical.');
for (const [name, expected] of baseline) {
  const selected = actual.get(name);
  assert.ok(selected, `Missing linked module: ${name}`);
  if (name === 'github.com/obot-platform/mcp-oauth-proxy') {
    assert.equal(selected.version, expected.version);
    assert.equal(selected.replacement, './third_party/mcp-oauth-proxy (devel)');
    assert.equal(expected.checksum, 'h1:oDaNI7vV7UJcX0yNFXcIYZhzv7Onz+/EfQLIgmQ0Ckw=');
  } else assert.deepEqual(selected, expected, `Linked dependency drift: ${name}`);
}
const inputs = JSON.parse(fs.readFileSync(path.join(root, 'fragai/build-inputs.lock.json')));
// Go's trimmed build metadata omits linker flags. Inspect the packaged ELF,
// where the linker-injected runtime reference must actually be present.
const binary = execFileSync('docker', ['run', '--rm', '--network', 'none', '--entrypoint', 'cat', image, '/usr/local/libexec/nanobot'], { maxBuffer: 128 * 1024 * 1024 });
assert.equal(binary.subarray(0, 4).toString('hex'), '7f454c46');
assert.ok(binary.includes(Buffer.from(`${inputs.cliImage}:${inputs.version}`)), 'The packaged executable must contain the owned sandbox image reference.');
console.log(`Verified all ${baseline.size} linked Go dependency identities against the actual original binary; only the checksum-proven local OAuth replacement changes resolution.`);
