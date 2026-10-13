// Representative store and hotel identity marks for the benefit-selection cards.
// Use local, real store logos supplied for the UI. Where imagery is unavailable,
// show a readable brand name; never present a synthetic mark as an official logo.
// The representative logo does not imply that every store in that brand accepts benefits.
const commons = filename => 'https://commons.wikimedia.org/wiki/Special:FilePath/' + encodeURIComponent(filename);

const dining = {
  skylark:       {name:'ガスト', sub:'Cafe Restaurant', color:'#aa343a', symbol:'G', asset:commons('Gusto Logo.svg')},
  colowide:      {name:'牛角', sub:'GYU-KAKU', color:'#8b3830', symbol:'牛', asset:'https://livedoor.blogimg.jp/line_jp/imgs/2/9/29dbd189.png'},
  create:        {name:'磯丸水産', sub:'ISOMARU SUISAN', color:'#be3038', symbol:'磯', asset:'./assets/logo-original-create.png'},
  zensho:        {name:'すき家', sub:'SUKIYA', color:'#c43b43', symbol:'S', asset:commons('Sukiya logo.svg')},
  toridoll:      {name:'丸亀製麺', sub:'MARUGAME SEIMEN', color:'#a3302c', symbol:'丸', asset:commons('Marugame Seimen logo.svg')},
  yoshinoya:     {name:'吉野家', sub:'YOSHINOYA', color:'#df7029', symbol:'吉', asset:commons('Yoshinoya Logo.svg')},
  mcd:           {name:'McDonald’s', sub:'マクドナルド', color:'#e5a91e', symbol:'M', large:true, asset:'./assets/mcdonalds-mark.svg'},
  monogatari:    {name:'焼肉きんぐ', sub:'YAKINIKU KING', color:'#71452c', symbol:'肉', asset:'./assets/logo-original-monogatari.jpg'},
  matsuya:       {name:'松屋', sub:'MATSUYA', color:'#38639b', symbol:'松', spriteIndex:3},
  royal:         {name:'ロイヤルホスト', sub:'Royal Host', color:'#be6d27', symbol:'R', asset:commons('Royal Host Logo.png')},
  balnibarbi:    {name:'BALNIBARBI', sub:'ガーブ', color:'#58757b', symbol:'G', asset:'./assets/logo-original-balnibarbi.png'},
  daiichikosho:  {name:'BIG ECHO', sub:'カラオケ ビッグエコー', color:'#d75070', symbol:'BE', asset:'./assets/logo-original-daiichikosho.gif'},
  fujio:         {name:'まいどおおきに食堂', sub:'FUJIO FOOD', color:'#ac7138', symbol:'食', compact:true, asset:'./assets/logo-original-fujio.png'},
  srs:           {name:'和食さと', sub:'SATO', color:'#db273a', symbol:'さ', asset:'./assets/brand-logo-srs.webp'},
  arclands:      {name:'かつや', sub:'KATSUYA', color:'#ee8843', symbol:'か', asset:'./assets/brand-logo-arclands.webp'},
  kineya:        {name:'そじ坊', sub:'KINEYA', color:'#9a4445', symbol:'杵', asset:'./assets/logo-original-kineya.webp'},
  saintmarc:     {name:'サンマルクカフェ', sub:'ST-MARC CAFÉ', color:'#704c3d', symbol:'S', asset:'./assets/logo-original-saintmarc.png'},
  chimney:       {name:'はなの舞', sub:'HANANOMAI', color:'#e60021', symbol:'花', asset:'./assets/brand-logo-chimney.webp'},
  ringerhut:     {name:'Ringer Hut', sub:'リンガーハット', color:'#b24756', symbol:'R', asset:'./assets/logo-original-ringerhut.jpeg'},
  hiday:         {name:'日高屋', sub:'熱烈中華食堂', color:'#b64447', symbol:'日', spriteIndex:4},
  ichibanya:     {name:'CoCo壱番屋', sub:'CURRY HOUSE', color:'#ad6d34', symbol:'Co', asset:'https://pbs.twimg.com/media/ES9CSLQUwAAS2Sc.png'},
  komeda:        {name:'コメダ珈琲店', sub:'KOMEDA’S Coffee', color:'#5481a9', symbol:'☕', asset:commons("Komeda's Coffee Shop logo.svg")},
  dnh:           {name:'ドトールコーヒー', sub:'DOUTOR COFFEE', color:'#87603b', symbol:'D', asset:commons('Doutor Coffee Logo.png')},
  mos:           {name:'MOS BURGER', sub:'モスバーガー', color:'#4d9b69', symbol:'M', asset:commons('MOS-Burger-Logo.svg')},
  yamaokaya:     {name:'ラーメン山岡家', sub:'YAMAOKAYA', color:'#dc4013', symbol:'山', asset:'./assets/brand-logo-yamaokaya.webp'},
  chikaranomoto: {name:'一風堂', sub:'IPPUDO', color:'#c44946', symbol:'一', asset:commons('Ippudo Logo.png')},
  ohsho:         {name:'餃子の王将', sub:'OHSHO', color:'#a83838', symbol:'王', asset:commons('餃子の王将.svg')},
  joyfull:       {name:'ジョイフル', sub:'JOYFULL', color:'#46836b', symbol:'J', asset:commons('Joyfull Restaurant.png')},
  yossix:        {name:'や台ずし', sub:'YATAIZUSHI', color:'#281a13', symbol:'寿', asset:'./assets/brand-logo-yossix.webp'}
};

const hotel = {
  'kyoritsu-hotel-discount':{name:'dormy inn', sub:'ドーミーイン', color:'#555d74', symbol:'d', asset:'https://media.sauna-ikitai.com/kb/tonttu/dormyin_kawasaki/logo.jpg'},
  'greens-hotels':         {name:'Comfort HOTEL', sub:'コンフォートホテル', color:'#8c7c9a', symbol:'C', asset:'https://www.choice-hotels.jp/ogp.jpg'},
  'daiwa-house-hotels':    {name:'Daiwa Roynet Hotel', sub:'ダイワロイネットホテル', color:'#6367a3', symbol:'DR', compact:true},
  'seibu-free-hotels':     {name:'Prince Hotel', sub:'プリンスホテル', color:'#9d8063', symbol:'P', asset:commons('PrinceHotels logo.svg')},
  'kyoritsu-resort-plan':  {name:'共立リゾート', sub:'KYORITSU RESORT', color:'#8c8268', symbol:'♨', asset:'https://dormy-hotels.com/resort/ogp.jpg'},
  'sunfrontier-hotels':    {name:'たびのホテル', sub:'TABINO HOTEL', color:'#637488', symbol:'H', asset:'https://foodslabo-app-prod.s3.ap-northeast-1.amazonaws.com/store/uploads/brands/4170/original-brand/4170/logo/cfb27bdb4b70a7ec720f70d1fd03bb5b.png'},
  'resol-hotels':          {name:'HOTEL RESOL', sub:'ホテルリソル', color:'#578477', symbol:'R', asset:'https://www.resol.jp/common/img/og_image.png'},
  'tosei-hotels':          {name:'TOSEI HOTEL', sub:'COCONE', color:'#788a98', symbol:'C', asset:'https://tosei-hotel.co.jp/files/ogp.jpg'},
  'tkp-hotels':            {name:'TKP', sub:'ホテル・宿泊優待', color:'#cd525d', symbol:'TKP', large:true, asset:'https://www.ishinoya.jp/atami/images/home/about.jpg'},
  'wealth-hotels':         {name:'HOTEL EMISIA', sub:'ホテルエミシア', color:'#9a757a', symbol:'E', asset:'https://www.hotel-emisia.com/sapporo/ogp.jpg'},
  'wakita-hotels':         {name:'HOTEL CORDIA', sub:'ホテルコルディア', color:'#aa8b6a', symbol:'HC', asset:'https://image.jimcdn.com/app/cms/image/transf/dimension%3D2048x2048%3Aformat%3Djpg/path/sb0a7af9f18ef4727/image/i9276edc2076cfada/version/1495000658/image.jpg'},
  'vision-hotels':         {name:'VISION GLAMPING', sub:'ビジョングランピング', color:'#677b66', symbol:'V', asset:'https://vision-glamping.com/yamanakako/img/ogp_img/OGP_7_FAQ.jpg'},
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
  if (Number.isInteger(info.spriteIndex)) {
    const sprite = document.createElement('img');
    sprite.className = 'representative-mark-image';
    sprite.src = `./assets/logo-sprite-cell-${info.spriteIndex}.webp`;
    sprite.alt = ''; 
    mark.append(sprite);
    mark.classList.add('has-real-logo');
  }
  if (info.asset && !Number.isInteger(info.spriteIndex)) {
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
