// Result navigation is deliberately a scroll, not a layout-changing accordion.
// Keep full control with the visitor: any wheel, touch or keyboard input cancels it.
export function createSmoothNavigator(win, doc) {
  let frame = null;
  let attached = false;

  const stop = () => {
    if (frame !== null) win.cancelAnimationFrame(frame);
    frame = null;
    if (!attached) return;
    attached = false;
    win.removeEventListener('wheel', stop, true);
    win.removeEventListener('touchstart', stop, true);
    win.removeEventListener('pointerdown', stop, true);
    win.removeEventListener('keydown', stop, true);
    doc.removeEventListener('visibilitychange', stopOnHidden);
  };

  function stopOnHidden() {
    if (doc.hidden) stop();
  }

  const scrollTo = target => {
    stop();
    if (!target || doc.hidden) return false;

    const start = win.scrollY ?? win.pageYOffset ?? 0;
    const rawMargin = Number.parseFloat(win.getComputedStyle?.(target)?.scrollMarginTop);
    const margin = Number.isFinite(rawMargin) ? rawMargin : 20;
    const height = Math.max(
      doc.documentElement?.scrollHeight || 0,
      doc.body?.scrollHeight || 0
    );
    const limit = Math.max(0, height - win.innerHeight);
    const desired = start + target.getBoundingClientRect().top - margin;
    const finish = Math.min(limit, Math.max(0, desired));
    const change = finish - start;
    if (Math.abs(change) < 8) return false;

    if (win.matchMedia?.('(prefers-reduced-motion: reduce)').matches ||
        typeof win.requestAnimationFrame !== 'function') {
      win.scrollTo(0, finish);
      return true;
    }

    // Longer trips have time to breathe, without turning a search into a long wait.
    const duration = Math.min(1700, Math.max(950, 800 + Math.abs(change) * 0.2));
    let started = null;
    attached = true;
    win.addEventListener('wheel', stop, {capture:true, passive:true});
    win.addEventListener('touchstart', stop, {capture:true, passive:true});
    win.addEventListener('pointerdown', stop, true);
    win.addEventListener('keydown', stop, true);
    doc.addEventListener('visibilitychange', stopOnHidden);

    const animate = timestamp => {
      if (started === null) started = timestamp;
      const progress = Math.min(1, (timestamp - started) / duration);
      // Sinusoidal ease-in-out: unhurried start and a soft landing.
      const eased = (1 - Math.cos(Math.PI * progress)) / 2;
      win.scrollTo(0, start + change * eased);
      if (progress < 1) frame = win.requestAnimationFrame(animate);
      else stop();
    };
    frame = win.requestAnimationFrame(animate);
    return true;
  };

  return {scrollTo, stop};
}
