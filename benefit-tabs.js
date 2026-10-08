// Panels stay mounted: switching categories never resets their selection or search state.
export function initBenefitTabs({onChange = () => {}} = {}) {
  const root = document.getElementById('benefitSelection');
  const tabs = [...root.querySelectorAll('[role="tab"]:not(:disabled)')];
  const select = tab => {
    for (const item of tabs) {
      const active = item === tab;
      item.setAttribute('aria-selected', String(active));
      item.tabIndex = active ? 0 : -1;
      document.getElementById(item.getAttribute('aria-controls')).hidden = !active;
    }
    onChange({diningTab:'dining', hotelTab:'hotel', expiryTab:'expiry'}[tab.id]);
  };
  for (const tab of tabs) {
    tab.addEventListener('click', () => select(tab));
    tab.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const index = tabs.indexOf(tab);
      const next = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs.at(-1) : tabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
      select(next); next.focus();
    });
  }
  select(tabs[0]);
}
