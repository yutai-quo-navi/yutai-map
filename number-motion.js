// Final values stay readable and accessible; motion never counts through false values.
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
      // Individual digit slots reveal once; commas and the surrounding text stay still.
      const label = node.textContent;
      node.setAttribute('role', 'img');
      node.setAttribute('aria-label', label);
      node.replaceChildren(...Array.from(label, character => {
        const digit = document.createElement('span');
        digit.textContent = character;
        digit.setAttribute('aria-hidden', 'true');
        digit.className = /\d/.test(character) ? 'motion-digit' : 'motion-separator';
        return digit;
      }));
      node.querySelectorAll('.motion-digit').forEach((digit, index) => {
        const animation = digit.animate([
          {transform:'translateY(.55em)', opacity:0},
          {transform:'translateY(0)', opacity:1}
        ], {duration:240, delay:Math.min(index * 18, 72), easing:'cubic-bezier(.22,1,.36,1)', fill:'backwards'});
        active.add(animation);
        const release = () => active.delete(animation);
        animation.onfinish = release; animation.oncancel = release;
      });
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
