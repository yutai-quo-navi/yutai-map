// Saint Marc HD card: decide discount from the OFFICIAL store's explicit brand label.
// Fail closed on unknown brands or specifically excluded stores; never infer from fuzzy POI hits.
function benefitKey(value) {
  return String(value || '').normalize('NFKC').toLocaleLowerCase('ja')
    .replace(/[\s\u3000・･._\-‐–—]/g, '')
    .replace(/[\u2018\u2019\u0060\u00b4]/g, "'");
}

export function saintmarcBenefitForStore(company, store) {
  if (company?.id !== 'saintmarc' || !store?.brand_name) return null;
  const rules = company.benefitRules;
  if (!rules?.eligibleBrands?.length) return null;
  const brand = benefitKey(store.brand_name);
  const matches = rules.eligibleBrands.filter(rule =>
    [rule.name, ...(rule.variants || [])].some(alias => benefitKey(alias) === brand)
  );
  if (matches.length !== 1) return null;
  const rule = matches[0];
  if (![10, 20].includes(rule.discountPercent)) return null;

  const storeName = benefitKey(store.name);
  if (!storeName) return null;
  const excluded = (rules.excludedStores || []).some(exception =>
    benefitKey(exception.brand) === benefitKey(rule.name) &&
    storeName.includes(benefitKey(exception.store))
  );
  if (excluded) return null;
  return {discountPercent: rule.discountPercent, brand: rule.name};
}
