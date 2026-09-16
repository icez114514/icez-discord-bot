// Check the actual service route, not the browser fixture's permissive server.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.POKER_ASSET_BASE_URL || 'http://127.0.0.1:8765';
(async () => {
  for (const name of [...Array.from({length:52}, (_, i) => `${i}.png`), 'back.png']) {
    const response = await fetch(`${base}/assets/cards/casino/${name}`, {signal:AbortSignal.timeout(10000)});
    assert.equal(response.status, 200, name);
    assert.match(response.headers.get('content-type') || '', /^image\/png/, name);
    assert.deepEqual(Buffer.from(await response.arrayBuffer()), fs.readFileSync(path.join(__dirname, '../public/assets/cards/casino', name)), name);
  }
  console.log('PASS: actual service serves all 52 casino faces and the back as identical PNG assets.');
})().catch(error => { console.error(error); process.exitCode = 1; });
