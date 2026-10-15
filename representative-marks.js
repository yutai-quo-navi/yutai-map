// Representative store and hotel identity marks for the benefit-selection cards.
// Use local, real store logos supplied for the UI. Where imagery is unavailable,
// show a readable brand name; never present a synthetic mark as an official logo.
// The representative logo does not imply that every store in that brand accepts benefits.

const dining = {
  anrakutei: {name:'安楽亭',sub:'安楽亭',color:'#df001a',symbol:'店',asset:'./assets/logo-anrakutei.svg'},
  tenpos: {name:'ステーキのあさくま',sub:'あさくま',color:'#8b0000',symbol:'店',asset:'./assets/logo-tenpos-asakuma.png'},
  kisoji: {name:'木曽路',sub:'木曽路',color:'#70152e',symbol:'店',asset:'./assets/logo-kisoji.svg'},
  bronco: {name:'ブロンコビリー',sub:'ブロンコビリー',color:'#c7182a',symbol:'店',asset:'./assets/logo-bronco.svg'},
  tenallied: {name:'てんぐ大ホール',sub:'てんぐ大ホール',color:'#222222',symbol:'店',asset:'./assets/logo-tenallied.webp'},
  kourakuen: {name:'幸楽苑',sub:'幸楽苑',color:'#c7182a',symbol:'幸',asset:'./assets/logo-kourakuen.webp'},
  eternal: {name:'鳥貴族',sub:'鳥貴族',color:'#b52025',symbol:'店',asset:'./assets/logo-eternal.svg'},
  hotland: {name:'築地銀だこ',sub:'築地銀だこ',color:'#b52025',symbol:'店',asset:'./assets/logo-hotland.webp'},
  gift: {name:'町田商店',sub:'町田商店',color:'#b51c27',symbol:'町',asset:'./assets/logo-gift-machida.webp'},
  hikari: {name:'立呑み 焼きとん 大黒',sub:'大黒',color:'#252525',symbol:'大',asset:'./assets/logo-hikari-daikoku.webp'},
  amiyaki: {name:"あみやき亭",sub:"あみやき亭",color:"#da252b",symbol:'店',asset:"./assets/logo-original-amiyaki.png"},
  towa: {name:"椿屋珈琲",sub:"椿屋珈琲",color:"#253c20",symbol:'店',asset:"./assets/logo-original-towa.png"},

  genki: {name:'元気寿司・魚べい',sub:'Genki GDC',color:'#efb600',symbol:'元',asset:'./assets/logo-original-genki-uobei.png'},
  skylark:       {name:'ガスト', sub:'Cafe Restaurant', color:'#aa343a', symbol:'G', asset:'./assets/logo-local-skylark.webp'},
  kura:          {name:'くら寿司', sub:'KURA', color:'#191919', symbol:'く', asset:'./assets/logo-original-kura.jpg'},
  foodlife:      {name:'スシロー', sub:'SUSHIRO', color:'#a9151a', symbol:'寿', asset:'./assets/brand-logo-foodlife.svg'},
  colowide:      {name:'牛角', sub:'GYU-KAKU', color:'#8b3830', symbol:'牛', asset:'./assets/logo-local-colowide.webp'},
  create:        {name:'磯丸水産', sub:'ISOMARU SUISAN', color:'#be3038', symbol:'磯', asset:'./assets/logo-isomaru-20261014.webp'},
  zensho:        {name:'すき家', sub:'SUKIYA', color:'#c43b43', symbol:'S', asset:'./assets/logo-local-zensho.webp'},
  toridoll:      {name:'丸亀製麺', sub:'MARUGAME SEIMEN', color:'#a3302c', symbol:'丸', asset:'./assets/logo-local-toridoll.webp'},
  yoshinoya:     {name:'吉野家', sub:'YOSHINOYA', color:'#df7029', symbol:'吉', asset:'./assets/logo-local-yoshinoya.webp'},
  mcd:           {name:'McDonald’s', sub:'マクドナルド', color:'#e5a91e', symbol:'M', large:true, asset:'./assets/mcdonalds-mark.svg'},
  monogatari:    {name:'焼肉きんぐ', sub:'YAKINIKU KING', color:'#71452c', symbol:'肉', asset:'./assets/logo-original-monogatari.jpg'},
  matsuya:       {name:'松屋', sub:'MATSUYA', color:'#38639b', symbol:'松', asset:'./assets/logo-matsuya-20261014.webp'},
  royal:         {name:'ロイヤルホスト', sub:'Royal Host', color:'#be6d27', symbol:'R', asset:'./assets/logo-royal-host-20261014.webp'},
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
  ichibanya:     {name:'CoCo壱番屋', sub:'CURRY HOUSE', color:'#ad6d34', symbol:'Co', asset:'./assets/logo-ichibanya-20261014.webp'},
  komeda:        {name:'コメダ珈琲店', sub:'KOMEDA’S Coffee', color:'#5481a9', symbol:'☕', asset:'./assets/logo-local-komeda.webp'},
  dnh:           {name:'ドトールコーヒー', sub:'DOUTOR COFFEE', color:'#87603b', symbol:'D', asset:'./assets/logo-local-dnh.webp'},
  mos:           {name:'MOS BURGER', sub:'モスバーガー', color:'#4d9b69', symbol:'M', asset:'./assets/logo-local-mos.webp'},
  yamaokaya:     {name:'ラーメン山岡家', sub:'YAMAOKAYA', color:'#dc4013', symbol:'山', asset:'./assets/brand-logo-yamaokaya.webp'},
  chikaranomoto: {name:'一風堂', sub:'IPPUDO', color:'#c44946', symbol:'一', asset:'./assets/logo-local-chikaranomoto.webp'},
  ohsho:         {name:'餃子の王将', sub:'OHSHO', color:'#a83838', symbol:'王', asset:'./assets/logo-local-ohsho.webp'},
  joyfull:       {name:'ジョイフル', sub:'JOYFULL', color:'#46836b', symbol:'J', asset:'./assets/logo-local-joyfull.webp'},
  yossix:        {name:'や台ずし', sub:'YATAIZUSHI', color:'#281a13', symbol:'寿', asset:'./assets/brand-logo-yossix.webp'}
};

const hotel = {
  'kyoritsu-hotel-discount':{name:'dormy inn', sub:'ドーミーイン', color:'#555d74', symbol:'d', asset:'./assets/hotel-logo-kyoritsu-hotel-discount.svg'} ,
  'greens-hotels':         {name:'Comfort HOTEL', sub:'コンフォートホテル', color:'#8c7c9a', symbol:'C', asset:'./assets/hotel-logo-greens-hotels.svg'} ,
  'daiwa-house-hotels':    {name:'Daiwa Roynet Hotel', sub:'ダイワロイネットホテル', color:'#6367a3', symbol:'DR', compact:true, asset:'./assets/hotel-logo-daiwa-house-hotels.svg'} ,
  'seibu-free-hotels':     {name:'Prince Hotel', sub:'プリンスホテル', color:'#9d8063', symbol:'P', asset:'./assets/hotel-logo-seibu-free-hotels.svg'} ,
  'kyoritsu-resort-plan':  {name:'共立リゾート', sub:'KYORITSU RESORT', color:'#8c8268', symbol:'♨', asset:'./assets/hotel-logo-kyoritsu-resort-20261014.png'},
  'sunfrontier-hotels':    {name:'たびのホテル', sub:'TABINO HOTEL', color:'#637488', symbol:'H', asset:'./assets/logo-local-sunfrontier-hotels.webp'},
  'resol-hotels':          {name:'HOTEL RESOL', sub:'ホテルリソル', color:'#578477', symbol:'R', asset:'./assets/hotel-logo-resol-hotels.svg'} ,
  'tosei-hotels':          {name:'TOSEI HOTEL', sub:'COCONE', color:'#788a98', symbol:'C', asset:'./assets/hotel-logo-tosei-hotels.svg'} ,
  'tkp-hotels':            {name:'TKP', sub:'ホテル・宿泊優待', color:'#cd525d', symbol:'TKP', large:true, asset:'./assets/hotel-logo-tkp-hotels.svg'} ,
  'wealth-hotels':         {name:'HOTEL EMISIA', sub:'ホテルエミシア', color:'#9a757a', symbol:'E', asset:'./assets/hotel-logo-wealth-hotels.svg'} ,
  'wakita-hotels':         {name:'HOTEL CORDIA', sub:'ホテルコルディア', color:'#aa8b6a', symbol:'HC', asset:'./assets/hotel-logo-wakita-hotels.svg'} ,
  'vision-hotels':         {name:'VISION GLAMPING', sub:'ビジョングランピング', color:'#677b66', symbol:'V'},
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
    // A real image owns this slot from the start. Reveal text only on failure,
    // never briefly while a cached image is being decoded.
    mark.classList.add('has-real-logo');
    const image = document.createElement('img');
    image.className = 'representative-mark-image';
    image.src = info.asset;
    image.alt = '';
    image.loading = 'eager';
    image.decoding = 'sync';
    image.addEventListener('load', () => {
      if (image.naturalWidth > 0) mark.classList.add('has-real-logo');
    }, {once:true});
    image.addEventListener('error', () => {
      image.remove();
      mark.classList.remove('has-real-logo');
    }, {once:true});
    mark.append(image);
  }
  return mark;
}
