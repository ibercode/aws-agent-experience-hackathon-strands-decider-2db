import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/executionTime.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { executionElapsedMs } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
const startedAt = '2026-01-01T10:00:00Z';
const start = Date.parse(startedAt);

test('live elapsed time continues beyond the finished scripted timeline', () => {
  const session = { status: 'running', startedAt, endedAt: null, simulationTimeMs: 34000, durationMs: 34000, simulationFinished: true };
  assert.equal(executionElapsedMs(session, start + 52000), 52000);
  assert.equal(executionElapsedMs(session, start + 71000), 71000);
});

test('completed and reopened sessions retain the actual server-recorded duration', () => {
  const session = { status: 'completed', startedAt, endedAt: '2026-01-01T10:01:07.381Z' };
  assert.equal(executionElapsedMs(session, start + 68000), 67381);
  assert.equal(executionElapsedMs(session, start + 86400000), 67381);
});

test('elapsed wall time includes pauses and resumes without resetting', () => {
  const session = { status: 'paused', startedAt, endedAt: null };
  assert.equal(executionElapsedMs(session, start + 40000), 40000);
  assert.equal(executionElapsedMs({ ...session, status: 'running' }, start + 45000), 45000);
});

test('unstarted, missing and invalid timestamps never invent a duration', () => {
  assert.equal(executionElapsedMs({ status: 'ready', startedAt: null, endedAt: null }, start), 0);
  assert.equal(executionElapsedMs({ status: 'running', startedAt: null, endedAt: null }, start), null);
  assert.equal(executionElapsedMs({ status: 'completed', startedAt, endedAt: null }, start), null);
  assert.equal(executionElapsedMs({ status: 'completed', startedAt, endedAt: 'invalid' }, start), null);
  assert.equal(executionElapsedMs({ status: 'running', startedAt: 'invalid', endedAt: null }, start), null);
  assert.equal(executionElapsedMs({ status: 'running', startedAt, endedAt: null }, start - 1000), 0);
});
