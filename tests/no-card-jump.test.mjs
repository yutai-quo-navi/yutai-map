import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

test('dining reconciles deadline order while reusing mounted logo cards',async()=>{
  const [dining,hotel]=await Promise.all(['app.js','special-features.js']
    .map(p=>readFile(new URL('../'+p,import.meta.url),'utf8')));
  assert.match(dining,/compareDiningPriority\(/);
  assert.match(dining,/existingGroups.get\(c.id\)/);
  assert.match(dining,/els.chips.insertBefore\(group/);
  assert.match(hotel,/const stableOrder = new Map\(\[\.\.\.root\.querySelectorAll/);
  assert.doesNotMatch(dining,/a\.position != null && b\.position != null/);
  assert.match(hotel,/a\.position != null && b\.position != null/);
});

