export const SEARCH_RADII = {
  dining: ['1000', '3000', '5000', '10000', '30000'],
  hotel: ['100000', '500000', '1000000', '1500000', 'all']
};

// Only the range is saved; search coordinates are never persisted.
export function initSearchRadius(select, {read, write}) {
  const keys = {dining: 'yutai-radius', hotel: 'yutai-hotel-radius'};
  const defaults = {dining: '3000', hotel: 'all'};
  const values = Object.fromEntries(Object.keys(keys).map(section => {
    const saved = read(keys[section]);
    return [section, SEARCH_RADII[section].includes(saved) ? saved : defaults[section]];
  }));
  let active = 'dining';
  return {
    setSection(section) {
      active = section;
      select.replaceChildren(...SEARCH_RADII[section].map(value => {
        const option = select.ownerDocument.createElement('option');
        option.value = value;
        option.textContent = value === 'all' ? '全国' : `${Number(value) / 1000} km`;
        return option;
      }));
      select.value = values[section];
    },
    remember() {
      if (!SEARCH_RADII[active].includes(select.value)) return;
      values[active] = select.value;
      write(keys[active], select.value);
    },
    value(section) {
      return values[section] === 'all' ? 'all' : Number(values[section]);
    }
  };
}
