// Representative store and hotel identity marks for the benefit-selection cards.
// When a verified logo asset is unavailable, show a readable branded wordmark
// instead of a guessed or mislabeled corporate logo. No store/benefit data changes.
const commons = filename => 'https://commons.wikimedia.org/wiki/Special:FilePath/' + encodeURIComponent(filename);

const dining = {
  skylark:       {name:'ガスト', sub:'Cafe Restaurant', color:'#aa343a', symbol:'G', asset:commons('Gusto Logo.svg')},
  colowide:      {name:'牛角', sub:'GYU-KAKU', color:'#8b3830', symbol:'牛'},
  create:        {name:'しゃぶ菜', sub:'SHABUSAI', color:'#a9643b', symbol:'菜'},
  zensho:        {name:'すき家', sub:'SUKIYA', color:'#c43b43', symbol:'S', asset:commons('Sukiya logo.svg')},
  toridoll:      {name:'丸亀製麺', sub:'MARUGAME SEIMEN', color:'#a3302c', symbol:'丸', asset:commons('Marugame Seimen logo.svg')},
  yoshinoya:     {name:'吉野家', sub:'YOSHINOYA', color:'#df7029', symbol:'吉', asset:commons('Yoshinoya Logo.svg')},
  mcd:           {name:'McDonald’s', sub:'マクドナルド', color:'#e5a91e', symbol:'M', large:true, asset:'./assets/mcdonalds-mark.svg'},
  monogatari:    {name:'焼肉きんぐ', sub:'YAKINIKU KING', color:'#71452c', symbol:'肉'},
  matsuya:       {name:'松屋', sub:'MATSUYA', color:'#38639b', symbol:'松'},
  royal:         {name:'ロイヤルホスト', sub:'Royal Host', color:'#be6d27', symbol:'R', asset:commons('Royal Host Logo.png')},
  balnibarbi:    {name:'GARB', sub:'ガーブ', color:'#58757b', symbol:'G'},
  daiichikosho:  {name:'BIG ECHO', sub:'カラオケ ビッグエコー', color:'#d75070', symbol:'BE'},
  fujio:         {name:'まいどおおきに食堂', sub:'FUJIO FOOD', color:'#ac7138', symbol:'食', compact:true},
  srs:           {name:'和食さと', sub:'SATO', color:'#ba4e61', symbol:'さ'},
  arclands:      {name:'かつや', sub:'KATSUYA', color:'#9a5637', symbol:'か'},
  kineya:        {name:'杵屋', sub:'KINEYA', color:'#9a4445', symbol:'杵'},
  saintmarc:     {name:'サンマルクカフェ', sub:'ST-MARC CAFÉ', color:'#704c3d', symbol:'S'},
  chimney:       {name:'はなの舞', sub:'HANANOMAI', color:'#8a5161', symbol:'花'},
  ringerhut:     {name:'Ringer Hut', sub:'リンガーハット', color:'#b24756', symbol:'R'},
  hiday:         {name:'日高屋', sub:'熱烈中華食堂', color:'#b64447', symbol:'日'},
  ichibanya:     {name:'CoCo壱番屋', sub:'CURRY HOUSE', color:'#ad6d34', symbol:'Co', asset:'https://pbs.twimg.com/media/ES9CSLQUwAAS2Sc.png'},
  komeda:        {name:'コメダ珈琲店', sub:'KOMEDA’S Coffee', color:'#5481a9', symbol:'☕', asset:commons("Komeda's Coffee Shop logo.svg")},
  dnh:           {name:'ドトールコーヒー', sub:'DOUTOR COFFEE', color:'#87603b', symbol:'D', asset:commons('Doutor Coffee Logo.png')},
  mos:           {name:'MOS BURGER', sub:'モスバーガー', color:'#4d9b69', symbol:'M', asset:commons('MOS-Burger-Logo.svg')},
  yamaokaya:     {name:'ラーメン山岡家', sub:'YAMAOKAYA', color:'#c7414a', symbol:'山'},
  chikaranomoto: {name:'一風堂', sub:'IPPUDO', color:'#c44946', symbol:'一', asset:commons('Ippudo Logo.png')},
  ohsho:         {name:'餃子の王将', sub:'OHSHO', color:'#a83838', symbol:'王', asset:commons('餃子の王将.svg')},
  joyfull:       {name:'ジョイフル', sub:'JOYFULL', color:'#46836b', symbol:'J', asset:commons('Joyfull Restaurant.png')},
  yossix:        {name:'や台ずし', sub:'YATAIZUSHI', color:'#ac6543', symbol:'寿'}
};

const hotel = {
  'kyoritsu-hotel-discount':{name:'dormy inn', sub:'ドーミーイン', color:'#555d74', symbol:'d'},
  'greens-hotels':         {name:'Comfort HOTEL', sub:'コンフォートホテル', color:'#8c7c9a', symbol:'C'},
  'daiwa-house-hotels':    {name:'Daiwa Roynet Hotel', sub:'ダイワロイネットホテル', color:'#6367a3', symbol:'DR', compact:true},
  'seibu-free-hotels':     {name:'Prince Hotel', sub:'プリンスホテル', color:'#9d8063', symbol:'P', asset:commons('PrinceHotels logo.svg')},
  'kyoritsu-resort-plan':  {name:'共立リゾート', sub:'KYORITSU RESORT', color:'#8c8268', symbol:'♨'},
  'sunfrontier-hotels':    {name:'たびのホテル', sub:'TABINO HOTEL', color:'#637488', symbol:'H'},
  'resol-hotels':          {name:'HOTEL RESOL', sub:'ホテルリソル', color:'#578477', symbol:'R'},
  'tosei-hotels':          {name:'TOSEI HOTEL', sub:'COCONE', color:'#788a98', symbol:'C'},
  'tkp-hotels':            {name:'TKP', sub:'ホテル・宿泊優待', color:'#cd525d', symbol:'TKP', large:true},
  'wealth-hotels':         {name:'HOTEL EMISIA', sub:'ホテルエミシア', color:'#9a757a', symbol:'E'},
  'wakita-hotels':         {name:'HOTEL CORDIA', sub:'ホテルコルディア', color:'#aa8b6a', symbol:'HC'},
  'vision-hotels':         {name:'VISION GLAMPING', sub:'ビジョングランピング', color:'#677b66', symbol:'V'}
};

export function representativeMark(section, id) {
  return (section === 'hotel' ? hotel : dining)[id] || null;
}

export function createBrandMark(section, id) {
  const info = representativeMark(section, id);
  if (!info) return null;
  const mark = document.createElement('span');
  mark.className = 'representative-mark' + (info.compact ? ' representative-mark--compact' : '') +
    (info.large ? ' representative-mark--large' : '');
  mark.style.setProperty('--mark-color', info.color);
  mark.setAttribute('aria-hidden', 'true');
  mark.dataset.representativeBrand = info.name;
  const fallback = document.createElement('span');
  fallback.className = 'representative-mark-fallback';
  const symbol = document.createElement('span');
  symbol.className = 'representative-mark-symbol';
  symbol.textContent = info.symbol;
  const wording = document.createElement('span');
  wording.className = 'representative-mark-wording';
  const main = document.createElement('span');
  main.className = 'representative-mark-name';
  main.textContent = info.name;
  const sub = document.createElement('span');
  sub.className = 'representative-mark-sub';
  sub.textContent = info.sub;
  wording.append(main, sub);
  // Do not fabricate a symbol that could be mistaken for the brand's official mark.
  // Without a verified image, the accurate store-brand name itself is the fallback.
  fallback.append(wording);
  mark.append(fallback);
  if (info.asset) {
    const image = document.createElement('img');
    image.className = 'representative-mark-image';
    image.src = info.asset;
    image.alt = '';
    image.loading = 'lazy';
    image.decoding = 'async';
    image.addEventListener('load', () => {
      if (image.naturalWidth > 0) mark.classList.add('has-real-logo');
    }, {once:true});
    image.addEventListener('error', () => image.remove(), {once:true});
    mark.append(image);
  }
  return mark;
}
