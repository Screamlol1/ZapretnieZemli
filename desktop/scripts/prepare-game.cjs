const fs=require('node:fs/promises'),path=require('node:path');
const desktop=path.resolve(__dirname,'..'),game=path.resolve(desktop,'..'),dest=path.join(desktop,'.stage/game');
const developmentFiles=new Set(['admin_cli.py','bundle.py','import-audio.py','package-lock.json']);
async function copyTree(from,to){await fs.mkdir(to,{recursive:true});for(const item of await fs.readdir(from,{withFileTypes:true})){if(item.isSymbolicLink())throw Error('Symlink in release source: '+item.name);if(item.name==='__pycache__')continue;const a=path.join(from,item.name),b=path.join(to,item.name);if(item.isDirectory())await copyTree(a,b);else await fs.copyFile(a,b);}}
(async()=>{
 if(!dest.startsWith(desktop+path.sep+'.stage'+path.sep))throw Error('Unsafe staging path');
 await fs.rm(dest,{recursive:true,force:true});await fs.mkdir(dest,{recursive:true});
 for(const entry of await fs.readdir(game,{withFileTypes:true})){if(!entry.isFile()||!(/\.(py|mjs|json)$/.test(entry.name))||developmentFiles.has(entry.name))continue;await fs.copyFile(path.join(game,entry.name),path.join(dest,entry.name));}
 await copyTree(path.join(game,'public'),path.join(dest,'public'));
 for(const required of ['server.py','node_runtime.py','public/account.html','public/tools/rules.js','public/spell-catalog.json'])await fs.access(path.join(dest,required));
 const walk=async dir=>{for(const e of await fs.readdir(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(/\.sqlite|\.log$|\.env$/.test(e.name)||developmentFiles.has(e.name)||['local-assets','map-images','.runtime','tests','node_modules'].includes(e.name))throw Error('Private/unwanted file in release: '+p);if(e.isDirectory())await walk(p);}};await walk(dest);
 console.log('Clean game resources staged. No accounts, campaigns, private maps or books.');
})().catch(e=>{console.error(e);process.exitCode=1;});
