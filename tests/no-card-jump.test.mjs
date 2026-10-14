import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

test('hydrated cards retain the existing DOM positions instead of resorting when API data arrives',async()=>{
  const [dining,hotel]=await Promise.all(['app.js','special-features.js']
    .map(p=>readFile(new URL('../'+p,import.meta.url),'utf8')));
  assert.match(dining,/const stableOrder = new Map\(\[\.\.\.els\.chips\.querySelectorAll/);
  assert.match(hotel,/const stableOrder = new Map\(\[\.\.\.root\.querySelectorAll/);
  assert.match(dining,/a\.position != null && b\.position != null/);
  assert.match(hotel,/a\.position != null && b\.position != null/);
});
