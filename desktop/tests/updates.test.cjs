const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {Updates,release,newer,assetURL}=require('../updates.cjs');
const bytes=Buffer.alloc(1000000,42),digest=crypto.createHash('sha256').update(bytes).digest('hex');
const entry={tag_name:'v1.3.0',body:'Обновление',assets:[{name:'ZapretnieZemli-Setup-1.3.0-x64.exe',size:bytes.length,digest:'sha256:'+digest,browser_download_url:'https://github.com/Screamlol1/ZapretnieZemli/releases/download/v1.3.0/ZapretnieZemli-Setup-1.3.0-x64.exe'}]};
test('Update release rejects foreign assets, prereleases, missing hashes and downgrades',()=>{
 assert(newer('1.10.0','1.9.9'));assert(!newer('1.3.0','1.3.0'));assert.equal(release(entry,'1.4.0'),null);assert.equal(release({...entry,prerelease:true},'1.2.0'),null);
 for(const asset of [{...entry.assets[0],digest:null},{...entry.assets[0],browser_download_url:'https://github.com/other/project/releases/download/v1.3.0/a.exe'},{...entry.assets[0],size:1e12}])assert.throws(()=>release({...entry,assets:[asset]},'1.2.0'));
 for(const url of ['http://github.com/a','https://github.com.attacker.example/a','https://user:secret@github.com/a','https://localhost/a'])assert.throws(()=>assetURL(url));
});
test('Update check, bounded download and install-time hash check; corruption never becomes ready',async()=>{
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'zz-update-'));try{
  let corrupt=false;const request=async url=>url.includes('api.github.com')?new Response(JSON.stringify(entry)):new Response(corrupt?Buffer.alloc(bytes.length,1):bytes);
  const u=new Updates({directory,current:'1.2.0',request});await u.check();assert.equal(u.state.status,'available');await u.download();assert.equal(u.state.status,'ready');const file=await u.installer();fs.writeFileSync(file,Buffer.alloc(bytes.length,2));await assert.rejects(()=>u.installer(),/сумма/);
  corrupt=true;await assert.rejects(()=>u.download(),/сумма/);assert.equal(u.state.status,'error');assert.equal(u.file,null);assert(!fs.existsSync(path.join(directory,entry.assets[0].name+'.partial')));
 }finally{fs.rmSync(directory,{recursive:true,force:true});}
});
test('Missing release and offline checks stay explicit; unsafe download redirect is blocked',async()=>{
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'zz-update-'));try{
  const u=new Updates({directory,current:'1.2.0',request:async()=>new Response('',{status:404})});await u.check();assert.equal(u.state.status,'unpublished');
  u.request=async url=>url.includes('api.github.com')?new Response(JSON.stringify(entry)):new Response('',{status:302,headers:{location:'http://127.0.0.1:1234/private'}});await u.check();await assert.rejects(()=>u.download(),/адрес/);assert.equal(u.file,null);
  u.request=async()=>{throw Error('offline');};await assert.rejects(()=>u.check());assert.equal(u.state.status,'error');assert.equal(u.entry,null);
 }finally{fs.rmSync(directory,{recursive:true,force:true});}
});
