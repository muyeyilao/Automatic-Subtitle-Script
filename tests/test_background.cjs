const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');
const source = readFileSync(join(__dirname, '../extension/background.js'), 'utf8');

function request(message, fetch) {
  return new Promise((resolve) => {
    let listener;
    vm.runInNewContext(source, {
      chrome: {runtime: {onMessage: {addListener: (fn) => { listener = fn; }}}},
      fetch, AbortController, setTimeout, clearTimeout,
    });
    listener(message, {}, resolve);
  });
}

test('ready captions use a lightweight health request to detect shutdown', async () => {
  let call;
  const reply = await request({type: 'health'}, async (url, options) => {
    call = {url, options};
    return {ok: true, json: async () => ({status: 'ok'})};
  });
  assert.equal(call.url, 'http://127.0.0.1:8765/health');
  assert.equal(call.options.body, undefined);
  assert.equal(reply.ok, true);
});

test('caption requests preserve the selected video URL', async () => {
  const url = 'https://www.bilibili.com/video/BV123abc4567/?p=2';
  await request({type: 'captions', url}, async (_endpoint, options) => {
    assert.equal(options.method, 'POST');
    assert.equal(JSON.parse(options.body).url, url);
    return {ok: true, json: async () => ({status: 'queued'})};
  });
});

test('a stopped server is marked unavailable so the page can stay silent', async () => {
  const reply = await request({type: 'health'}, async () => { throw new Error('connection refused'); });
  assert.equal(reply.ok, false);
  assert.equal(reply.unavailable, true);
});

test('an online server error remains distinguishable from an offline service', async () => {
  const reply = await request({type: 'captions', url: 'invalid'}, async () => ({
    ok: false, status: 400, json: async () => ({error: 'Invalid video URL'}),
  }));
  assert.equal(reply.unavailable, false);
  assert.equal(reply.error, 'Invalid video URL');
});
