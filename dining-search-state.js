// Describe the effective search, separately from the saved company selection.
export function searchScopeLabel(selectedCount, brand, category = '') {
  return `${selectedCount}社選択${brand ? `・検索対象は「${brand.name}」のみ` : '・全ブランド'}${category ? `・${category}` : ''}`;
}

export function coverageMessage(coverage, incomplete = false) {
  const messages = [];
  const unresolved = Number(coverage?.unresolved_stores || 0);
  if (unresolved > 0) messages.push(`検索対象企業の全国データに座標未補完の店舗が${unresolved}件あります（この検索範囲内の件数ではありません）。`);
  if (coverage?.unverified_issuers?.length) messages.push('公式一覧との照合状況が未確認の企業を含みます。');
  if (incomplete && !messages.length) messages.push('店舗データの整備・更新状況を確認できません。');
  return messages.length ? messages.join('') + '未登録店舗の有無は、この検索結果だけでは判断できません。' : '';
}

export function emptySearchMessage({brand, category = '', coverage, incomplete = false}) {
  const scope = [brand ? `「${brand.name}」` : '', category ? `「${category}」` : ''].filter(Boolean).join('・');
  if (scope) return `${scope}の条件に一致する登録済み店舗は0件です。`;
  if (Number(coverage?.unresolved_stores) > 0) return '座標を登録済みの対象店舗は0件です。座標未補完の店舗は検索に含まれません。';
  if (incomplete) return '現在の登録データでは対象店舗は0件です。店舗データの整備・照合状況は下記をご確認ください。';
  return '条件に一致する対象店舗は0件です。';
}

// A successful HTTP response still must be a valid search response, never {} => 0.
export function validateSearchResponse(data, issuerIds) {
  const ids = new Set(issuerIds);
  const counts = data?.category_counts;
  if (!Array.isArray(data?.results) || !Number.isInteger(data.count) || data.count !== data.results.length ||
      data.count > 30 || !counts || !['all','restaurant','cafe','bakery','foodcourt','other'].every(k => Number.isInteger(counts[k]) && counts[k] >= 0) ||
      counts.all < data.count || counts.all !== ['restaurant','cafe','bakery','foodcourt','other'].reduce((n,k) => n + counts[k], 0) ||
      typeof data.incomplete !== 'boolean' || typeof data.has_more !== 'boolean' ||
      (data.has_more && (typeof data.next_cursor !== 'string' || !data.next_cursor))) throw new Error('Invalid store search response');
  for (const s of data.results) {
    if (!ids.has(s.issuer_id) || typeof s.store_id !== 'string' || typeof s.name !== 'string' ||
        !Number.isFinite(s.lat) || !Number.isFinite(s.lng) || Math.abs(s.lat) > 90 || Math.abs(s.lng) > 180 ||
        !Number.isFinite(s.distance) || s.distance < 0) throw new Error('Invalid store search record');
  }
  return data;
}
