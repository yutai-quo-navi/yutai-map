// Accessible final values with a short, visible digit-reel transition.
const escape = value => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
export function numberHTML(key, value) {
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number < 0) return escape(value);
  return `<span class="motion-number" data-motion-key="${escape(key)}" data-motion-value="${number}">${number.toLocaleString('ja-JP')}</span>`;
}

export function initNumberMotion(root) {
  const seen = new Map();
  const observed = new WeakSet();
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const active = new Set();
  const stop = () => { if (reduced.matches) for (const animation of active) animation.cancel(); };
  reduced.addEventListener('change', stop);
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      const node = entry.target;
      if (!entry.isIntersecting || !node.isConnected) continue;
      observer.unobserve(node);
      const key = node.dataset.motionKey, value = node.dataset.motionValue;
      const previous = seen.get(key);
      seen.set(key, value);
      if (previous === value || reduced.matches || !node.animate) continue;
      const label = node.textContent;
      const oldLabel = previous == null ? '' : Number(previous).toLocaleString('ja-JP');
      node.setAttribute('role', 'img');
      node.setAttribute('aria-label', label);
      node.replaceChildren(...Array.from(label, (character, index) => {
        const slot = document.createElement('span');
        slot.setAttribute('aria-hidden', 'true');
        if (!/\d/.test(character)) {
          slot.className = 'motion-separator'; slot.textContent = character; return slot;
        }
        slot.className = 'motion-digit';
        const reel = document.createElement('span');
        reel.className = 'motion-reel digit-'+character;
        for (let value = 0; value <= 9; value++) {
          const glyph = document.createElement('span'); glyph.className = 'motion-glyph';
          glyph.textContent = String(value); reel.append(glyph);
        }
        slot.append(reel);
        const before = oldLabel[index - label.length + oldLabel.length];
        const start = /\d/.test(before || '') ? Number(before) : 0;
        const target = Number(character);
        const animation = reel.animate([
          {transform:`translateY(${-start * 1.1}em)`, filter:'blur(1px)'},
          {transform:`translateY(${-target * 1.1}em)`, filter:'blur(0)'}
        ], {duration:previous == null ? 560 : 380, delay:Math.min(index * 35, 105), easing:'cubic-bezier(.22,1,.36,1)', fill:'backwards'});
        active.add(animation);
        const release = () => active.delete(animation);
        animation.onfinish = release; animation.oncancel = release;
        return slot;
      }));
    }
  });
  const scan = element => {
    if (element.nodeType !== 1) return;
    const nodes = [...element.querySelectorAll('[data-motion-value]')];
    if (element.matches('[data-motion-value]')) nodes.unshift(element);
    for (const node of nodes) if (!observed.has(node)) { observed.add(node); observer.observe(node); }
  };
  const mutations = new MutationObserver(records => {
    for (const record of records) {
      for (const removed of record.removedNodes) {
        if (removed.nodeType !== 1) continue;
        observer.unobserve(removed);
        removed.querySelectorAll('[data-motion-value]').forEach(node => observer.unobserve(node));
      }
      record.addedNodes.forEach(scan);
    }
  });
  scan(root);
  mutations.observe(root, {childList:true, subtree:true});
  return () => { mutations.disconnect(); observer.disconnect(); for (const animation of active) animation.cancel(); reduced.removeEventListener('change', stop); };
}
