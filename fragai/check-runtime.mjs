import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const candidate = process.argv[2];
const baseline = 'ghcr.io/obot-platform/nanobot-agent@sha256:6c612bfcd18183c6ea22077ea8c0e690245a483d3accd392621c45e1fcab6ea0';
const runID = crypto.randomUUID();
const label = `ai.fragai.nanobot-review=${runID}`;
const volume = `fragai-agent-review-${runID}`;
const reportPath = process.env.FRAGAI_REPORT_PATH || path.join(root, 'bin', `fragai-agent-${candidate ? 'compatibility' : 'baseline'}-${runID}.json`);
const report = { runID, candidate, baseline, passed: false, customerDataUsed: false, stages: [], cleanupErrors: [] };
let created = false;

function command(args, timeout = 600000) {
  return new Promise((resolve, reject) => {
    const child = spawn('docker', args, { cwd: root, windowsHide: true });
    let stdout = '', stderr = '';
    child.stdout.on('data', b => { stdout += b; });
    child.stderr.on('data', b => { stderr += b; });
    const timer = setTimeout(() => { child.kill(); reject(new Error(`Timed out: docker ${args[0]}`)); }, timeout);
    child.once('error', reject);
    child.once('close', code => { clearTimeout(timer); resolve({ code, stdout, stderr }); });
  });
}

try {
  const before = await command(['ps', '--format', '{{.ID}}']);
  assert.equal(before.code, 0, before.stderr);
  report.existingContainers = before.stdout.trim().split(/\s+/).filter(Boolean).sort();
  let result = await command(['volume', 'create', '--label', label, volume]);
  assert.equal(result.code, 0, result.stderr);
  created = true;
  const markers = [];
  const stages = candidate ? [['baseline', baseline], ['candidate', candidate], ['restart', candidate], ['rollback', baseline]] : [['baseline', baseline]];
  for (const [stage, image] of stages) {
    const container = `fragai-agent-${runID}-${stage}`;
    console.log(`Checking ${stage} with synthetic state and no external network...`);
    result = await command(['run', '--rm', '--name', container, '--label', label,
      '--network', 'none', '--memory', '2g', '--cpus', '2', '--shm-size', '256m', '--entrypoint', 'python3',
      '--mount', `type=volume,source=${volume},target=/home/nanobot`,
      '--mount', `type=bind,source=${path.join(root, 'fragai/runtime-check.py')},target=/runtime-check.py,readonly`,
      '-e', `FRAGAI_STAGE=${stage}`, '-e', `FRAGAI_EXPECT_MARKERS=${JSON.stringify(markers)}`,
      image, '/runtime-check.py']);
    let detail;
    try { detail = JSON.parse(result.stdout); }
    catch { throw new Error(`No JSON report for ${stage}: ${result.stderr.slice(-3000)} ${result.stdout.slice(-3000)}`); }
    report.stages.push({ stage, image, ...detail });
    assert.equal(result.code, 0, `${stage}: ${detail.error || 'runtime checks failed'}`);
    assert.equal(detail.passed, true);
    markers.push(stage);
    if (report.stages.length > 1) {
      assert.deepEqual(detail.checks, report.stages[0].checks);
      assert.equal(detail.toolName, report.stages[0].toolName);
      assert.deepEqual(detail.stateTables, report.stages[0].stateTables);
    }
  }
  const after = await command(['ps', '--format', '{{.ID}}']);
  const remaining = new Set(after.stdout.trim().split(/\s+/).filter(Boolean));
  assert.ok(report.existingContainers.every(id => remaining.has(id)), 'Existing application containers must remain running.');
  report.passed = true;
} catch (error) {
  report.error = error.message;
} finally {
  const owned = await command(['ps', '-aq', '--filter', `label=${label}`]);
  for (const id of owned.stdout.trim().split(/\s+/).filter(Boolean)) {
    const result = await command(['rm', '-f', '-v', id]);
    if (result.code) report.cleanupErrors.push(result.stderr);
  }
  if (created) {
    const inspected = await command(['volume', 'inspect', volume]);
    try {
      assert.equal(JSON.parse(inspected.stdout)[0].Labels['ai.fragai.nanobot-review'], runID);
      const removed = await command(['volume', 'rm', volume]);
      assert.equal(removed.code, 0, removed.stderr);
    } catch (error) { report.cleanupErrors.push(error.message); }
  }
  report.passed &&= report.cleanupErrors.length === 0;
  await fs.mkdir(path.dirname(reportPath), { recursive: true });
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
}
if (!report.passed) process.exitCode = 1;
