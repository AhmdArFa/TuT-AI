const fs = require('fs');

console.log('--- Patching TuT Agent Avatar Selector & Mascot Sync ---');

// 1. Patch profile bundles: fix onClick in avatar tile
const profileBundles = [
  '/app/public/_spa/assets/profile-Bac-vNLs.js',
  '/app/dist/desktop/assets/profile-Bac-vNLs.js'
];

for (const p of profileBundles) {
  if (!fs.existsSync(p)) continue;
  let text = fs.readFileSync(p, 'utf8');
  
  const brokenClick = 'onClick:()=>{let P=bt.find(x=>x.src===t.src);if(P){l(r,{avatar:P.src,name:P.label,title:P.title,description:P.title});try{L.getState().updateAgentConfigById(r,{openingMessage:P.welcome,systemRole:P.systemRole});}catch(_){}}d(t.src);}';
  const fixedClick = 'onClick:()=>{let P=MCIT_AVATAR_LIST.find(x=>x.src===t.src)||t;let targetId=(typeof t==="string"&&t.startsWith("agt_"))?t:(L.getState().activeAgentId||"agt_xEk7XfRtovAl");if(P&&targetId){try{L.getState().updateAgentMetaById(targetId,{avatar:P.src,name:P.label,title:P.title,description:P.title});L.getState().updateAgentConfigById(targetId,{openingMessage:P.welcome,systemRole:P.systemRole});}catch(_e){console.error(_e);}}d(t.src);}';
  
  if (text.includes(brokenClick)) {
    text = text.replace(brokenClick, fixedClick);
    fs.writeFileSync(p, text, 'utf8');
    console.log('Successfully fixed avatar tile onClick in:', p);
  } else if (text.includes('MCIT_AVATAR_LIST.find(x=>x.src===t.src)')) {
    console.log('Avatar tile onClick already patched in:', p);
  } else {
    console.error('Target brokenClick not found in:', p);
  }

  // Also replace any remaining bt.find in onAvatarChange
  if (text.includes('let P=bt.find(x=>x.src===e);')) {
    text = text.replace('let P=bt.find(x=>x.src===e);', 'let P=MCIT_AVATAR_LIST.find(x=>x.src===e);');
    fs.writeFileSync(p, text, 'utf8');
    console.log('Successfully fixed onAvatarChange bt.find in:', p);
  }
}

// 2. Patch layout bundles: mascot portrait priority (pSrc || n)
const layoutBundles = [
  '/app/public/_spa/assets/_layout-M7AKyzf6.js',
  '/app/dist/desktop/assets/_layout-M7AKyzf6.js'
];

for (const p of layoutBundles) {
  if (!fs.existsSync(p)) continue;
  let text = fs.readFileSync(p, 'utf8');
  
  const target = "let i=n||pSrc;return(0,px.jsx)(`div`,{className:mx.root,children:(0,px.jsx)(`img`,";
  const replacement = "let i=pSrc||n;return(0,px.jsx)(`div`,{className:mx.root,children:(0,px.jsx)(`img`,";
  
  if (text.includes(target)) {
    text = text.replace(target, replacement);
    fs.writeFileSync(p, text, 'utf8');
    console.log('Successfully set mascot portrait to pSrc || n in:', p);
  } else if (text.includes(replacement)) {
    console.log('Mascot portrait already set to pSrc || n in:', p);
  } else {
    console.error('Target mascot portrait not found in:', p);
  }
}

// 3. Patch EmojiPicker tab default (default to first custom tab: mcit-gallery)
const emojiPickerBundles = [
  '/app/public/_spa/assets/EmojiPicker-D0FCAVmj.js',
  '/app/dist/desktop/assets/EmojiPicker-D0FCAVmj.js'
];

for (const p of emojiPickerBundles) {
  if (!fs.existsSync(p)) continue;
  let text = fs.readFileSync(p, 'utf8');
  
  const target = "[N,P]=(0,Q.useState)(`emoji`)";
  const replacement = "[N,P]=(0,Q.useState)(v?.length?v[0].value:`emoji`)";
  
  if (text.includes(target)) {
    text = text.replace(target, replacement);
    fs.writeFileSync(p, text, 'utf8');
    console.log('Successfully set EmojiPicker default tab to mcit-gallery in:', p);
  } else if (text.includes(replacement)) {
    console.log('EmojiPicker default tab already set in:', p);
  } else {
    console.error('Target EmojiPicker state not found in:', p);
  }
}

console.log('--- Done patching TuT Agent Avatar Selector & Mascot Sync ---');
