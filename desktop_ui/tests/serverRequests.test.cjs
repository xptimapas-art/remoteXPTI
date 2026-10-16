const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const source = path.join(__dirname, '../src/components/serverRequests.ts');
const compiled = new Module(source, module);
compiled._compile(ts.transpileModule(fs.readFileSync(source, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, source);
const { toggleServerFavorite } = compiled.exports;

test('favorite only returns the boolean confirmed by the persistent API', async t => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/servers/a%2Fb/favorite');
    assert.equal(options.method, 'POST');
    assert.ok(options.signal instanceof AbortSignal);
    return new Response(JSON.stringify({status:'ok',favorite:false}));
  });
  assert.equal(await toggleServerFavorite('a/b'), false);
});

test('disk failure and HTTP errors cannot become a favorite success', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({detail:'Não foi possível salvar os dados.'}),{status:507}));
  await assert.rejects(toggleServerFavorite('a'), /Não foi possível salvar os dados/);
});

test('invalid successful response cannot be mistaken for a saved favorite', async t => {
  for (const value of [{status:'ok'}, {status:'ok',favorite:'true'}, {status:'failed',favorite:true}]) {
    t.mock.method(globalThis,'fetch', async () => new Response(JSON.stringify(value)));
    await assert.rejects(toggleServerFavorite('a'), /não confirmou/);
    t.mock.restoreAll();
  }
});

test('network interruption leaves the action unconfirmed', async t => {
  t.mock.method(globalThis,'fetch', async () => {throw new TypeError('Network error');});
  await assert.rejects(toggleServerFavorite('a'), /Network error/);
});
