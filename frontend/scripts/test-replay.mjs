import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import ts from 'typescript';

// Exercise the actual dependency-free playback code, without adding a browser
// test framework or loading API/auth modules.
const source = await readFile(new URL('../src/replay.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { frameAt, validateRecording, fetchRecording } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
const directory = new URL('../../recordings/public/v3/', import.meta.url);
const manifest = JSON.parse(await readFile(new URL('manifest.json', directory), 'utf8'));

test('all nine catalogue entries have matching hashes and valid original live timelines', async () => {
  assert.equal(manifest.recordings.length, 9);
  assert.equal(new Set(manifest.recordings.map(item => `${item.scenarioId}/${item.preset}`)).size, 9);
  for (const entry of manifest.recordings) {
    const bytes = await readFile(new URL(entry.file, directory));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), entry.sha256);
    const recording = validateRecording(JSON.parse(bytes), entry);
    assert.equal(frameAt(recording.frames, 0), recording.frames[0]);
    assert.equal(frameAt(recording.frames, entry.recordingDurationMs), recording.frames.at(-1));
    for (let i = 1; i < recording.frames.length; i++) {
      const transition = recording.frames[i];
      if (transition.elapsedMs > recording.frames[i - 1].elapsedMs) {
        assert.ok(frameAt(recording.frames, transition.elapsedMs - 0.0001).elapsedMs < transition.elapsedMs);
      }
    }
  }
});

test('wall time controls output visibility even when scenario time has stopped', () => {
  const frames = [
    { elapsedMs: 0, view: { simulationTimeMs: 0, result: null } },
    { elapsedMs: 10000, view: { simulationTimeMs: 10000, result: null } },
    { elapsedMs: 15555.55, view: { simulationTimeMs: 10000, result: 'completed' } },
  ];
  assert.equal(frameAt(frames, 15555.54).view.result, null);
  assert.equal(frameAt(frames, 15555.55).view.result, 'completed');
  assert.equal(frameAt(frames, 0).view.result, null);
  assert.throws(() => frameAt([], 0));
});

test('mismatched recordings and malformed frame ordering are rejected', async () => {
  const entry = manifest.recordings[0];
  const recording = JSON.parse(await readFile(new URL(entry.file, directory), 'utf8'));
  assert.throws(() => validateRecording({ ...recording, recordingId: 'different-run' }, entry));
  assert.throws(() => validateRecording({ ...recording, frames: [recording.frames[1], recording.frames[0]] }, entry));
  assert.throws(() => validateRecording({ ...recording, frames: [{ elapsedMs: 0, view: { ...recording.frames[0].view, providerMode: 'fixture' } }] }, entry));
});

test('static fetch omits credentials and auth headers, and verifies integrity', async () => {
  const entry = manifest.recordings[0];
  const bytes = await readFile(new URL(entry.file, directory));
  const oldFetch = globalThis.fetch;
  const oldLocation = globalThis.location;
  globalThis.location = { origin: 'https://recorded.example' };
  globalThis.crypto ??= webcrypto;
  let requests = 0;
  const controller = new AbortController();
  globalThis.fetch = async (url, options) => {
    requests++;
    assert.equal(url.origin, 'https://recorded.example');
    assert.equal(options.credentials, 'omit');
    assert.equal(options.headers, undefined);
    assert.equal(options.signal, controller.signal);
    return new Response(bytes);
  };
  try {
    const recording = await fetchRecording('/assets/example.json', entry, controller.signal);
    assert.equal(recording.recordingId, entry.recordingId);
    await assert.rejects(fetchRecording('https://external.example/recording.json', entry, controller.signal));
    await assert.rejects(fetchRecording('/api/sessions', entry, controller.signal));
    assert.equal(requests, 1);
    await assert.rejects(fetchRecording('/assets/example.json', { ...entry, sha256: '0'.repeat(64) }, controller.signal), /published catalogue/);
  } finally { globalThis.fetch = oldFetch; globalThis.location = oldLocation; }
});
