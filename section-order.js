const IDS = ['benefitSelection', 'specialFeatures', 'hotelFeatures'];
const KEY = 'yutai.sectionOrder.v1';

export function decorateSection(section) {
  section.classList.add('reorderable-section');
  if (section.querySelector('.section-drag-handle')) return;
  const handle = document.createElement('button');
  handle.type = 'button';
  handle.className = 'section-drag-handle';
  const name = section.id === 'benefitSelection' ? '優待を選ぶ' : section.getAttribute('aria-label');
  handle.setAttribute('aria-label', `${name}を並べ替え`);
  handle.title = 'ドラッグで並べ替え。キーボードでは上下キーで移動';
  handle.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><circle cx="8" cy="5" r="1.5"/><circle cx="16" cy="5" r="1.5"/><circle cx="8" cy="12" r="1.5"/><circle cx="16" cy="12" r="1.5"/><circle cx="8" cy="19" r="1.5"/><circle cx="16" cy="19" r="1.5"/></svg>';
  section.prepend(handle);
}

export function initSectionOrder(parent) {
  const sections = IDS.map(id => document.getElementById(id)).filter(Boolean);
  const anchor = parent.querySelector('.results-section');
  if (sections.length !== IDS.length || !anchor) return;
  const current = () => [...parent.children].filter(node => sections.includes(node));
  const apply = ordered => ordered.forEach(node => parent.insertBefore(node, anchor));
  try {
    const saved = JSON.parse(localStorage.getItem(KEY));
    if (Array.isArray(saved) && saved.length === IDS.length && new Set(saved).size === IDS.length && saved.every(id => IDS.includes(id))) {
      apply(saved.map(id => sections.find(node => node.id === id)));
    }
  } catch { /* The default order works when storage is unavailable. */ }
  sections.forEach(decorateSection);
  const notice = document.createElement('span');
  notice.className = 'sr-only'; notice.setAttribute('role', 'status');
  parent.append(notice);
  const save = section => {
    const ordered = current();
    let persisted = true;
    try { localStorage.setItem(KEY, JSON.stringify(ordered.map(node => node.id))); } catch { persisted = false; }
    const visible = ordered.filter(node => !node.hidden);
    notice.textContent = `${section.querySelector('.section-drag-handle').getAttribute('aria-label').replace('を並べ替え', '')}を${visible.indexOf(section) + 1}番目に移動しました。${persisted ? '' : '並び順を保存できないため、この画面でのみ有効です。'}`;
  };
  let drag = null, frame = null;
  const clearMarkers = () => sections.forEach(node => node.classList.remove('section-drop-before', 'section-drop-after'));
  const mark = () => {
    clearMarkers();
    const others = current().filter(node => node !== drag.section && !node.hidden);
    const target = others.find(node => drag.y < node.getBoundingClientRect().top + node.getBoundingClientRect().height / 2);
    drag.before = target || null;
    (target || others.at(-1))?.classList.add(target ? 'section-drop-before' : 'section-drop-after');
  };
  const scroll = () => {
    if (!drag?.moving) return;
    const delta = drag.y < 70 ? -12 : drag.y > window.innerHeight - 70 ? 12 : 0;
    if (delta) { window.scrollBy(0, delta); mark(); }
    frame = requestAnimationFrame(scroll);
  };
  const finish = commit => {
    if (!drag) return;
    if (commit && drag.moving) {
      const ordered = current().filter(node => node !== drag.section);
      const index = drag.before ? ordered.indexOf(drag.before) : ordered.length;
      ordered.splice(index, 0, drag.section); apply(ordered); save(drag.section);
    }
    drag.section.classList.remove('section-dragging');
    if (drag.handle.hasPointerCapture(drag.pointerId)) drag.handle.releasePointerCapture(drag.pointerId);
    clearMarkers(); cancelAnimationFrame(frame); drag = null;
  };
  parent.addEventListener('pointerdown', event => {
    const handle = event.target.closest('.section-drag-handle');
    if (!handle || event.button !== 0 || drag) return;
    drag = {handle, section: handle.closest('.reorderable-section'), pointerId:event.pointerId, startY:event.clientY, y:event.clientY, moving:false, before:null};
    handle.setPointerCapture(event.pointerId);
  });
  parent.addEventListener('pointermove', event => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    drag.y = event.clientY;
    if (!drag.moving && Math.abs(drag.y - drag.startY) >= 6) {
      drag.moving = true; drag.section.classList.add('section-dragging'); scroll();
    }
    if (drag.moving) { event.preventDefault(); mark(); }
  });
  parent.addEventListener('pointerup', event => { if (drag?.pointerId === event.pointerId) finish(true); });
  parent.addEventListener('pointercancel', event => { if (drag?.pointerId === event.pointerId) finish(false); });
  parent.addEventListener('lostpointercapture', event => { if (drag?.pointerId === event.pointerId) finish(false); });
  parent.addEventListener('keydown', event => {
    if (event.key === 'Escape' && drag) { event.preventDefault(); finish(false); return; }
    const handle = event.target.closest('.section-drag-handle');
    if (!handle || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const section = handle.closest('.reorderable-section'), ordered = current();
    const visible = ordered.filter(node => !node.hidden), index = visible.indexOf(section);
    const target = visible[index + (event.key === 'ArrowUp' ? -1 : 1)];
    if (!target) return;
    const a = ordered.indexOf(section), b = ordered.indexOf(target);
    [ordered[a], ordered[b]] = [ordered[b], ordered[a]];
    apply(ordered); save(section); handle.focus();
  });
}
