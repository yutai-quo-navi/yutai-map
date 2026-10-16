// Motion recipe: transitions.dev Notification badge. Used only in dining choice cells.
export function makeDeadlineBadge(bubble, key) {
  const label = bubble.textContent;
  const days = label === '本日失効' ? '1' : (label.match(/^あと(\d+)日使える$/) || label.match(/^(\d+)日で失効$/))?.[1];
  bubble.classList.add('t-badge');
  bubble.classList.toggle('is-urgent', days != null && Number(days) <= 7 || label === '本日失効');
  bubble.classList.toggle('is-expired', label === '失効');
  bubble.dataset.badgeKey = key;
  bubble.dataset.badgeValue = label;
  bubble.dataset.open = 'false';
  const dot = document.createElement('span');
  dot.className = 't-badge-dot';
  if (days == null) dot.textContent = label === '本日失効' ? '本日' : label;
  else {
    const number=document.createElement('span');number.className='t-badge-number';number.textContent=days;
    const unit=document.createElement('span');unit.className='t-badge-unit';unit.textContent='日';
    dot.append(number);
    bubble.replaceChildren(dot,unit);
    return bubble;
  }
  bubble.replaceChildren(dot);
  return bubble;
}

export function initNotificationBadges(root) {
  const seen = new Map(), observed = new WeakSet();
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const observer = new IntersectionObserver(entries => {
    for (const {target:badge,isIntersecting} of entries) {
      if (!isIntersecting || !badge.isConnected) continue;
      observer.unobserve(badge);
      const key=badge.dataset.badgeKey, value=badge.dataset.badgeValue;
      const animate = !reduced.matches && seen.get(key) !== value;
      seen.set(key,value);
      badge.dataset.badgeMotion=String(animate);
      if (!animate) badge.dataset.open='true';
      else requestAnimationFrame(()=>requestAnimationFrame(()=>{
        if (badge.isConnected) badge.dataset.open='true';
      }));
    }
  });
  const scan = element => {
    if (element.nodeType !== 1) return;
    const badges=[...element.querySelectorAll('.t-badge')];
    if(element.matches('.t-badge')) badges.unshift(element);
    for(const badge of badges) if(!observed.has(badge)){observed.add(badge);observer.observe(badge);}
  };
  const mutations = new MutationObserver(records=>{
    for(const record of records){
      for(const node of record.removedNodes) if(node.nodeType===1){observer.unobserve(node);node.querySelectorAll('.t-badge').forEach(b=>observer.unobserve(b));}
      record.addedNodes.forEach(scan);
    }
  });
  scan(root);mutations.observe(root,{childList:true,subtree:true});
  return ()=>{mutations.disconnect();observer.disconnect();};
}
