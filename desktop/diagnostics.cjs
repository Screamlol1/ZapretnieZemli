'use strict';
const fs=require('node:fs'),path=require('node:path');
const pick=(value,allowed,fallback='unknown')=>allowed.includes(value)?value:fallback;
const version=value=>typeof value==='string'&&/^\d{1,4}(?:\.\d{1,8}){1,3}(?:-(?:alpha|beta|rc)(?:\.\d{1,5})?)?$/.test(value)?value:null;
const integer=(value,min,max)=>Number.isInteger(value)&&value>=min&&value<=max?value:null;
const bool=value=>typeof value==='boolean'?value:null;
const ERROR_CODES=['missing-runtime','permission-denied','timeout','connection-failed','server-stopped','render-process-stopped','unknown'];
function errorCode(value){
 const text=typeof value==='string'?value.slice(0,4096):'';if(!text)return null;
 if(/ENOENT|не найден|cannot find/i.test(text))return 'missing-runtime';
 if(/EACCES|EPERM|access denied|доступ запрещ/i.test(text))return 'permission-denied';
 if(/TIMED?_?OUT|timeout|45 секунд|дольше обычного/i.test(text))return 'timeout';
 if(/ERR_(?:CONNECTION|NAME|INTERNET|CERT)|ECONN|ENOTFOUND|сервер не отвечает|не удалось.*(?:ссылку|загрузить игру)|проверьте сеть/i.test(text))return 'connection-failed';
 if(/окно игры остановилось/i.test(text))return 'render-process-stopped';
 if(/сервер (?:остановился|завершился)/i.test(text))return 'server-stopped';
 return 'unknown';
}
function connectionKind(value){if(!value)return 'none';try{const url=new URL(value);if(!['http:','https:'].includes(url.protocol))return 'unknown';return ['127.0.0.1','localhost','[::1]'].includes(url.hostname)?'loopback':'remote';}catch{return 'unknown';}}
function runtimeInfo(resources,runtime){
 let lock={};try{const file=path.join(resources,'runtime-lock.json');if(fs.statSync(file).size<65536)lock=JSON.parse(fs.readFileSync(file,'utf8'));}catch{}
 return {versionSource:'bundle-manifest',python:{version:version(lock.python?.version),available:fs.existsSync(path.join(runtime,'python/python.exe'))},node:{version:version(lock.node?.version),available:fs.existsSync(path.join(runtime,'node/node.exe'))},cloudflared:{version:version(lock.cloudflared?.version),available:fs.existsSync(path.join(runtime,'cloudflared/cloudflared.exe'))}};
}
async function localHealth(host,request){
 if(host?.server!=='running')return {status:'not-running'};
 // Diagnostics may probe only the existing owned loopback server. Never send credentials or contact an invitation URL.
 if(typeof host.localUrl!=='string'||!/^http:\/\/127\.0\.0\.1:[1-9]\d{0,4}\/$/.test(host.localUrl))return {status:'unavailable'};
 try{const response=await request(host.localUrl+'api/health',{redirect:'error',credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(2000)});const data=await response.json();return {status:response.ok&&data?.ok===true?'healthy':'unhealthy',httpStatus:integer(response.status,100,599),ok:data?.ok===true};}catch{return {status:'unreachable'};}
}
function buildReport(input={}){
 const host=input.host||{},view=input.view||{},p=input.preferences||{},d=input.display||{},versions=input.versions||{},runtime=input.runtime||{},health=input.health||{},os=input.os||{};
 const component=name=>({version:version(runtime[name]?.version),available:bool(runtime[name]?.available)});
 // Explicit fields only: never spread host state, process environment, health JSON, preferences or log/error text.
 return {schemaVersion:1,createdAt:new Date().toISOString(),application:{name:'ZapretnieZemli',version:version(input.appVersion),packaged:bool(input.packaged)},platform:{os:pick(os.platform,['win32','linux','darwin']),release:version(os.release),arch:pick(os.arch,['x64','arm64','ia32'])},engine:{electron:version(versions.electron),node:version(versions.node),chrome:version(versions.chrome)},runtime:{versionSource:'bundle-manifest',python:component('python'),node:component('node'),cloudflared:component('cloudflared')},host:{server:pick(host.server,['stopped','starting','running','error']),sharing:pick(host.sharing,['stopped','starting','running','error']),error:errorCode(host.error)},localHealth:{status:pick(health.status,['not-running','unavailable','healthy','unhealthy','unreachable']),httpStatus:integer(health.httpStatus,100,599),ok:bool(health.ok)},view:{page:pick(view.view,['home','game']),connection:connectionKind(view.gameUrl),loading:bool(view.loading),error:errorCode(view.viewError)},window:{mode:pick(p.mode,['windowed','fullscreen','borderless']),width:integer(p.width,320,16384),height:integer(p.height,240,16384),zoom:integer(p.zoom,75,150),rememberWindow:bool(p.rememberWindow),confirmExit:bool(p.confirmExit),maximized:bool(view.maximized),fullscreen:bool(view.fullscreen),displayWidth:integer(d.width,320,16384),displayHeight:integer(d.height,240,16384)},recentErrors:(Array.isArray(input.recentErrors)?input.recentErrors:[]).slice(-8).map(e=>({source:pick(e?.source,['host','view']),code:pick(e?.code,ERROR_CODES),at:typeof e?.at==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(e.at)?e.at:null}))};
}
function reportFilename(appVersion,date=new Date()){return `ZapretnieZemli-diagnostics-${version(appVersion)||'unknown'}-${date.toISOString().replace(/[:.]/g,'-')}.json`;}
module.exports={buildReport,errorCode,runtimeInfo,localHealth,reportFilename};
