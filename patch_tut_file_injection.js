const fs = require('fs');

console.log('--- Patching TuT Agent file injection in server chunks and client bundles ---');

// 1. Patch server chunks
const serverChunks = [
  '/app/.next/server/chunks/_08gl7tk._.js',
  '/app/.next/server/chunks/_20lco-q._.js'
];

for (const p of serverChunks) {
  if (!fs.existsSync(p)) {
    console.log('Skipping missing chunk:', p);
    continue;
  }
  let text = fs.readFileSync(p, 'utf8');
  const target = 'P("retrieving messages and topics");let{messages:w,topics:f}=await F(i,"lambda.aiChat.messagesAndTopics.query",()=>t.aiChatService.getMessagesAndTopics';
  const injection = 'if(e.newUserMessage?.files?.length){try{let _ds=new k.DocumentService(t.serverDB,t.userId,t.workspaceId);await Promise.allSettled(e.newUserMessage.files.map(fid=>_ds.parseFile(fid)));}catch(err){console.error("[TuT-File] parse error:",err);}}';
  
  if (text.includes(injection)) {
    console.log('Already patched in server chunk:', p);
    continue;
  }
  if (!text.includes(target)) {
    console.error('Target string not found in:', p);
    continue;
  }
  text = text.replace(target, injection + target);
  fs.writeFileSync(p, text, 'utf8');
  console.log('Successfully patched server chunk:', p);
}

// 2. Patch client bundles for _tutFiles content preservation
const clientChatBundles = [
  '/app/public/_spa/assets/chat-Ch8iWO9I.js',
  '/app/dist/desktop/assets/chat-Ch8iWO9I.js'
];

for (const p of clientChatBundles) {
  if (!fs.existsSync(p)) continue;
  let text = fs.readFileSync(p, 'utf8');
  const target = 'url:e.fileUrl||e.base64Url||e.previewUrl||""})),St={';
  const replacement = 'content:e.content||e.parsedContent||e.document?.content||"",url:e.fileUrl||e.base64Url||e.previewUrl||""})),St={';
  if (text.includes(target)) {
    text = text.replace(target, replacement);
    fs.writeFileSync(p, text, 'utf8');
    console.log('Successfully patched _tutFiles in client bundle:', p);
  } else {
    console.log('_tutFiles already patched or target not matched in:', p);
  }
}

// 3. Patch character limits in client bundles (increase 100k -> 500k, preview 4k -> 50k)
const clientIndexBundles = [
  '/app/public/_spa/assets/index-8qv-oyAx.js',
  '/app/public/_spa/assets/index.mobile-Bd6Gq5eJ.js',
  '/app/dist/desktop/assets/index-8qv-oyAx.js'
];

for (const p of clientIndexBundles) {
  if (!fs.existsSync(p)) continue;
  let text = fs.readFileSync(p, 'utf8');
  let modified = false;
  
  // Replace 1e5 (100000) with 5e5 (500000) in file limits
  const targetLimit = '>1e5||t!==void 0&&t>e';
  const newLimit = '>5e5||t!==void 0&&t>e';
  if (text.includes(targetLimit)) {
    text = text.replace(targetLimit, newLimit);
    modified = true;
  }
  
  // Replace 4e3 (4000) preview with 5e4 (50000)
  const targetPreview = 'n0=4e3,r0=';
  const newPreview = 'n0=5e4,r0=';
  if (text.includes(targetPreview)) {
    text = text.replace(targetPreview, newPreview);
    modified = true;
  }
  
  const targetPreview2 = 'maxChars:4e3';
  const newPreview2 = 'maxChars:5e4';
  if (text.includes(targetPreview2)) {
    text = text.replaceAll(targetPreview2, newPreview2);
    modified = true;
  }

  if (modified) {
    fs.writeFileSync(p, text, 'utf8');
    console.log('Successfully patched limits in:', p);
  }
}

console.log('--- Done patching TuT Agent file injection ---');
