import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const readJSON = async p => JSON.parse(await fs.readFile(path.join(root, p), 'utf8'));
const source = await readJSON('fragai/upstream-source.lock.json');
const cli = await readJSON('fragai/mcp-cli-source.lock.json');
const inputs = await readJSON('fragai/build-inputs.lock.json');
function hash(buffer, normalize = false) {
  // Git for Windows may check text out as CRLF; imported binary files retain their bytes.
  const text = buffer.toString('utf8');
  const normalized = normalize && Buffer.from(text).equals(buffer) ? Buffer.from(text.replace(/\r\n/g, '\n')) : buffer;
  return crypto.createHash('sha256').update(normalized).digest('hex');
}
for (const record of source.files) {
  let target = record.path;
  if (source.originalFiles?.[target]) target = source.originalFiles[target];
  else if (target.startsWith('.github/workflows/')) target = `${source.workflowArchive}/${path.basename(target)}`;
  else if (['Dockerfile', 'Dockerfile.agent', 'Dockerfile.agent-runtime', '.goreleaser.yml'].includes(target)) target = `${inputs.upstreamPackagingArchive}/${target}`;
  const data = await fs.readFile(path.join(root, target));
  assert.ok(hash(data) === record.sha256 || hash(data, true) === record.lfSha256, `Upstream source drift: ${target}`);
}
for (const record of cli.files) {
  const data = await fs.readFile(path.join(root, 'third_party/mcp-cli', record.path));
  assert.ok(hash(data) === record.sha256 || hash(data, true) === record.lfSha256, `MCP CLI source drift: ${record.path}`);
}
const dockerfile = await fs.readFile(path.join(root, 'Dockerfile'), 'utf8');
const oauth = await readJSON('fragai/oauth-source.lock.json');
for (const record of oauth.files) {
  const data = await fs.readFile(path.join(root, 'third_party/mcp-oauth-proxy', record.path));
  assert.ok(hash(data) === record.sha256 || hash(data, true) === record.lfSha256, `OAuth source drift: ${record.path}`);
}
assert.equal(oauth.moduleChecksum, 'h1:oDaNI7vV7UJcX0yNFXcIYZhzv7Onz+/EfQLIgmQ0Ckw=');
for (const [file, checksum] of Object.entries(inputs.ownedMetadata)) assert.equal(hash(await fs.readFile(path.join(root, file)), true), checksum, `Owned metadata drift: ${file}`);
for (const image of Object.values(inputs.images)) assert.ok(dockerfile.includes(image), `Missing pinned input: ${image}`);
assert.ok(!dockerfile.includes('ghcr.io/obot-platform/'), 'Production Dockerfile must not import an Obot image.');
assert.ok(dockerfile.includes(`${inputs.cliImage}`));
assert.equal(source.revision, '00a40e47b82581ffdf52860eae08ec500d76dd7b');
const baseline = await readJSON('fragai/baselines/amd64.json');
for (const [name, packages] of Object.entries(baseline.pythonEnvironments)) {
  const requirement = (await fs.readFile(path.join(root, `fragai/${name}-requirements.txt`), 'utf8')).trim().split(/\r?\n/);
  assert.deepEqual(Object.fromEntries(requirement.map(l => l.split('=='))), packages);
}
console.log(`Verified ${source.files.length} Nanobot files, ${cli.files.length} MCP CLI files, ${oauth.files.length} OAuth files, image locks and both Python dependency inventories.`);
