import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const candidate = process.argv[2];
assert.ok(candidate, 'Supply the candidate agent image.');
const baseline = 'ghcr.io/obot-platform/nanobot-agent@sha256:6c612bfcd18183c6ea22077ea8c0e690245a483d3accd392621c45e1fcab6ea0';
const docker = (...args) => execFileSync('docker', args, { cwd: root, maxBuffer: 16 * 1024 * 1024 });
const inventory = image => JSON.parse(docker('run', '--rm', '--network', 'none', '--entrypoint', 'python3', '--mount', `type=bind,source=${path.join(root, 'fragai/inventory.py')},target=/inventory.py,readonly`, image, '/inventory.py'));
const old = inventory(baseline), owned = inventory(candidate);
assert.deepEqual(owned.pythonEnvironments, old.pythonEnvironments, 'Both Python environments must match the actual baseline.');
assert.deepEqual(owned.tokenizerCache, old.tokenizerCache);
assert.equal(owned.tools['mcp-cli'].stdout, old.tools['mcp-cli'].stdout);
assert.equal(owned.tools.uv.stdout.split(' (')[0], old.tools.uv.stdout.split(' (')[0]);
assert.deepEqual(owned.browsers, old.browsers);
assert.equal(owned.files['/usr/local/bin/nanobot'], old.files['/usr/local/bin/nanobot'], 'Preserve the original root/bootstrap/non-root browser entrypoint.');
for (const key of Object.keys(owned.tools)) assert.equal(owned.tools[key].code, 0, `${key} must run.`);
const oldConfig = JSON.parse(docker('image', 'inspect', baseline))[0].Config;
const newConfig = JSON.parse(docker('image', 'inspect', candidate))[0].Config;
for (const key of ['Entrypoint', 'Cmd', 'WorkingDir', 'User', 'ExposedPorts', 'Volumes']) assert.deepEqual(newConfig[key], oldConfig[key], `Preserve image contract: ${key}`);
for (const variable of ['HOME', 'NANOBOT_STATE', 'NANOBOT_RUN_LISTEN_ADDRESS', 'DISPLAY', 'PLAYWRIGHT_BROWSERS_PATH', 'TIKTOKEN_CACHE_DIR']) {
  assert.equal(newConfig.Env.find(v => v.startsWith(`${variable}=`)), oldConfig.Env.find(v => v.startsWith(`${variable}=`)), variable);
}
assert.equal(newConfig.Labels['org.opencontainers.image.source'], 'https://github.com/yugantb24/Nanobot');
const report = { passed: true, baseline, candidate, architecture: owned.architecture.stdout, osPackagesIdentical: JSON.stringify(owned.packages) === JSON.stringify(old.packages), baselineInventory: old, candidateInventory: owned };
fs.mkdirSync(path.join(root, 'bin'), { recursive: true });
fs.writeFileSync(path.join(root, `bin/fragai-agent-inventory-${owned.architecture.stdout}.json`), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ passed: true, architecture: report.architecture, pythonEnvironments: Object.fromEntries(Object.entries(owned.pythonEnvironments).map(([k,v]) => [k,Object.keys(v).length])), browser: owned.browsers.chromium.stdout, osPackagesIdentical: report.osPackagesIdentical, tools: owned.tools }, null, 2));
