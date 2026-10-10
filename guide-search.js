// Only published selections are accepted; deep links never request geolocation.
export function guideSearchSelection(search, companies = []) {
  const params = new URLSearchParams(search);
  const feature = params.get('feature') || '';
  const section = params.get('section') === 'hotel' && /^[a-z0-9-]{1,80}$/.test(feature) ? 'hotel' : 'dining';
  const requestedIssuer = params.get('issuer');
  const issuer = companies.find(company => company.status === 'public' && company.id === requestedIssuer)?.id || '';
  const brand = issuer ? (params.get('brand') || '').slice(0,160) : '';
  return {section, feature: section === 'hotel' ? feature : '', issuer, brand};
}
