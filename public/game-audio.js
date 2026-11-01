/* Local presentation only. The server remains authoritative for every result. */
const AUDIO_DEFAULTS=Object.freeze({muted:false,master:50,effects:65,ambience:25,hiddenBehavior:'pause'});
const SEEN_KEY='zz-audio-seen-v1',MAX_EFFECTS=3,MAX_BUFFERS=6,MAX_BUFFER_BYTES=48*1024*1024,MAX_DECODES=2,EFFECT_FRESHNESS_MS=2000;
const AMBIENT_PREVIEWS=new Set(['battle','wind','forest','cave','river','marsh','fire','city','tavern','rain','night']);
const EFFECT_PREVIEWS=new Set(['metal','footstep','monster','wolf','break','thunder','bell','blacksmith','snow-step']);
let options={...AUDIO_DEFAULTS},context=null,masterBus,effectsBus,ambienceBus,unlocked=false,desktopActive=true;
let current={scope:'',view:'',terrain:'',locationType:'',inCombat:false,ambientOverride:'auto'},ambientKey='',ambientGeneration=0,ambientTimer=null,catalogPromise,previewSequence=0,transientGeneration=0,previewGeneration=0;
let bufferBytes=0,activeDecodes=0,peakDecodes=0,totalDecodes=0,lastHidden=document.hidden;
const buffers=new Map(),inflight=new Map(),decodeQueue=[],effects=[],ambientVoices=new Set();
let seen=new Set();
try{const saved=JSON.parse(sessionStorage.getItem(SEEN_KEY)||'[]');if(Array.isArray(saved))seen=new Set(saved.filter(v=>typeof v==='string'&&v.length<500).slice(-600));}catch{}
const hidden=()=>document.hidden||!desktopActive;
const paused=()=>options.muted||hidden()&&options.hiddenBehavior==='pause';
const eligible=()=>unlocked&&context?.state==='running'&&!paused();
const emit=(name,detail)=>window.dispatchEvent(new CustomEvent(name,{detail}));
function mark(key){seen.add(key);while(seen.size>600)seen.delete(seen.values().next().value);try{sessionStorage.setItem(SEEN_KEY,JSON.stringify([...seen]));}catch{}}
function volume(value,fallback){return typeof value==='number'&&Number.isFinite(value)?Math.max(0,Math.min(100,Math.round(value))):fallback;}
function readOptions(value={}){return {muted:typeof value.muted==='boolean'?value.muted:AUDIO_DEFAULTS.muted,master:volume(value.master,AUDIO_DEFAULTS.master),effects:volume(value.effects,AUDIO_DEFAULTS.effects),ambience:volume(value.ambience,AUDIO_DEFAULTS.ambience),hiddenBehavior:['pause','duck','continue'].includes(value.hiddenBehavior)?value.hiddenBehavior:'pause'};}
function gainTo(node,value,seconds=.07){if(!context||!node)return;const now=context.currentTime;node.gain.cancelScheduledValues(now);node.gain.setValueAtTime(node.gain.value,now);node.gain.linearRampToValueAtTime(value,now+seconds);}
function updateVolumes(){
 if(!context)return;
 const duck=hidden()&&options.hiddenBehavior==='duck'?.15:1;
 gainTo(masterBus,options.muted?0:options.master/100*duck);gainTo(effectsBus,options.effects/100);gainTo(ambienceBus,options.ambience/100);
}
function stopVoice(voice,fade=.12){if(!voice||voice.stopped)return;voice.stopped=true;gainTo(voice.gain,0,fade);try{voice.source.stop((context?.currentTime||0)+fade+.01);}catch{};}
function stopEffects(fade=.04){for(const voice of effects.splice(0))stopVoice(voice,fade);}
function stopTransient(){transientGeneration++;stopEffects(0);}
function stopPreview(){previewGeneration++;for(let index=effects.length-1;index>=0;index--)if(effects[index].preview)stopVoice(effects.splice(index,1)[0],0);}
function stopAmbient(fade=.8){ambientGeneration++;clearTimeout(ambientTimer);ambientTimer=null;ambientKey='';for(const voice of ambientVoices)stopVoice(voice,fade);}
function catalog(){
 if(!catalogPromise)catalogPromise=fetch(new URL('audio-catalog.json',import.meta.url),{cache:'force-cache'}).then(r=>{if(!r.ok)throw Error('Audio catalog unavailable');return r.json();}).then(data=>new Map((data.clips||[]).filter(clip=>typeof clip.id==='string'&&/^audio\/[a-z0-9-]+\.mp3$/.test(clip.url)).map(clip=>[clip.id,clip]))).catch(error=>{catalogPromise=null;throw error;});
 return catalogPromise;
}
function pumpDecodes(){
 while(activeDecodes<MAX_DECODES&&decodeQueue.length){
  const job=decodeQueue.shift();activeDecodes++;peakDecodes=Math.max(peakDecodes,activeDecodes);
  Promise.resolve().then(job.run).then(job.resolve,job.reject).finally(()=>{activeDecodes--;pumpDecodes();});
 }
}
function decodeClip(data,clip){
 return new Promise((resolve,reject)=>{
  decodeQueue.push({resolve,reject,run:async()=>{
   totalDecodes++;const full=await context.decodeAudioData(data);
   if(clip.kind!=='effect'||!clip.limit)return full;
   // Keep only the short take used by an effect in decoded memory. Original
   // user-supplied MP3 bytes stay intact on disk and in the browser cache.
   const offset=Math.min(Math.floor((clip.offset||0)*full.sampleRate),full.length-1),length=Math.min(Math.ceil(clip.limit*full.sampleRate),full.length-offset),take=context.createBuffer(full.numberOfChannels,length,full.sampleRate);
   for(let channel=0;channel<full.numberOfChannels;channel++)take.copyToChannel(full.getChannelData(channel).subarray(offset,offset+length),channel);
   return take;
  }});pumpDecodes();
 });
}
function cacheBuffer(id,buffer){
 const bytes=buffer.length*buffer.numberOfChannels*Float32Array.BYTES_PER_ELEMENT;
 // Oversize ambience may play once, but must not evict the whole useful cache.
 if(bytes>MAX_BUFFER_BYTES)return;
 while(buffers.size>=MAX_BUFFERS||bufferBytes+bytes>MAX_BUFFER_BYTES){const oldest=buffers.keys().next().value;bufferBytes-=buffers.get(oldest).bytes;buffers.delete(oldest);}
 buffers.set(id,{buffer,bytes});bufferBytes+=bytes;
}
async function loadClip(id){
 const clip=(await catalog()).get(id);if(!clip)throw Error('Unknown audio clip');
 const cached=buffers.get(id);let buffer;
 if(cached){buffers.delete(id);buffers.set(id,cached);buffer=cached.buffer;}
 else{
  // In-flight work has its own lifetime: LRU eviction can never drop a pending
  // promise or cause a second decode of the same asset while it is loading.
  let pending=inflight.get(id);
  if(!pending){
   pending=fetch(new URL(clip.url,import.meta.url),{cache:'force-cache'}).then(r=>{if(!r.ok)throw Error('Audio file unavailable');return r.arrayBuffer();}).then(data=>decodeClip(data,clip)).then(decoded=>{cacheBuffer(id,decoded);return decoded;}).finally(()=>{if(inflight.get(id)===pending)inflight.delete(id);});
   inflight.set(id,pending);
  }
  buffer=await pending;
 }
 return {clip:clip.kind==='effect'&&clip.limit?{...clip,offset:0}:clip,buffer};
}
function chooseAmbient(){
 if(!current.scope)return '';
 if(current.ambientOverride==='silent')return '';
 if(AMBIENT_PREVIEWS.has(current.ambientOverride))return current.ambientOverride;
 if(current.inCombat)return 'battle';
 const place={tavern:'tavern',city:'city',settlement:'city',fortress:'city',camp:'fire',cave:'cave',ruin:'cave',ruins:'cave',dungeon:'cave'}[current.locationType];
 if(place)return place;
 return {forest:'forest',darkforest:'forest',marsh:'marsh',water:'river',river:'river',sea:'river',rain:'rain',night:'night',mountain:'wind',highmountain:'wind',hills:'wind',plain:'wind',plains:'wind'}[current.terrain]||'wind';
}
async function refreshAmbient(){
 const desired=eligible()&&options.ambience>0&&options.master>0?chooseAmbient():'';
 if(desired===ambientKey)return;
 stopAmbient();if(!desired)return;
 ambientKey=desired;const generation=ambientGeneration;
 try{
  const {clip,buffer}=await loadClip(desired);
  if(generation!==ambientGeneration||!eligible()||ambientKey!==desired)return;
  const loop=()=>{
   if(generation!==ambientGeneration||!eligible())return;
   const source=context.createBufferSource(),gain=context.createGain(),duration=buffer.duration,fade=Math.min(1.2,duration/4),now=context.currentTime;
   source.buffer=buffer;source.connect(gain);gain.connect(ambienceBus);
   gain.gain.setValueAtTime(0,now);gain.gain.linearRampToValueAtTime(clip.gain||.4,now+fade);gain.gain.setValueAtTime(clip.gain||.4,now+Math.max(fade,duration-fade));gain.gain.linearRampToValueAtTime(0,now+duration);
   const voice={source,gain,stopped:false};ambientVoices.add(voice);source.onended=()=>{ambientVoices.delete(voice);source.disconnect();gain.disconnect();};source.start();
   // Overlap the quiet edges of successive takes instead of a hard loop cut.
   ambientTimer=setTimeout(loop,Math.max(250,(duration-fade)*1000));
  };
  loop();emit('zz:audio-ambience',{id:desired,scope:current.scope});
 }catch{if(generation===ambientGeneration)ambientKey='';emit('zz:audio-status',{available:false,message:'Не удалось загрузить звуки. Игра продолжает работать.'});}
}
async function unlock(){
 if(options.muted)return false;
 try{
  if(!context){const Constructor=window.AudioContext||window.webkitAudioContext;if(!Constructor)return false;context=new Constructor();masterBus=context.createGain();effectsBus=context.createGain();ambienceBus=context.createGain();effectsBus.connect(masterBus);ambienceBus.connect(masterBus);masterBus.connect(context.destination);updateVolumes();}
  if(context.state==='suspended')await context.resume();unlocked=context.state==='running';
  if(unlocked){updateVolumes();refreshAmbient();}return unlocked;
 }catch{return false;}
}
function beginEffect(source,gain,preview=false){
 while(effects.length>=MAX_EFFECTS)stopVoice(effects.shift(),.035);
 const voice={source,gain,stopped:false,preview};effects.push(voice);
 source.onended=()=>{const index=effects.indexOf(voice);if(index>=0)effects.splice(index,1);source.disconnect();gain.disconnect();};return voice;
}
function synthesized(type,preview=false){
 const now=context.currentTime,duration=type==='dice'?.33:.8,buffer=context.createBuffer(1,Math.ceil(context.sampleRate*duration),context.sampleRate),data=buffer.getChannelData(0);
 for(let i=0;i<data.length;i++){
  const t=i/context.sampleRate;
  if(type==='dice'){
   let envelope=0;for(const start of [0,.06,.13,.22]){const age=t-start;if(age>=0&&age<.07)envelope+=Math.exp(-age*80)*(1-Math.exp(-age*1400));}
   data[i]=(Math.random()*2-1)*envelope*.26;
  }else{const envelope=Math.sin(Math.PI*t/duration)**2;data[i]=(Math.sin(2*Math.PI*523.25*t)+Math.sin(2*Math.PI*783.99*t)*.3+Math.sin(2*Math.PI*(1046.5+20*t)*t)*.15)*envelope*.12;}
 }
 const source=context.createBufferSource(),gain=context.createGain();source.buffer=buffer;source.connect(gain);gain.connect(effectsBus);gain.gain.setValueAtTime(1,now);beginEffect(source,gain,preview);source.start();
}
async function playEvent(event={}){
 const scope=String(event.scope||current.scope||''),id=typeof event.id==='string'?event.id:'';
 if(!id||id.length>250||scope.length>200||event.private===true&&event.role!=='gm')return false;
 const key=scope+'|'+id;if(seen.has(key))return false;mark(key);
 const type=String(event.type||'');
 const ambientPreview=event.preview===true&&AMBIENT_PREVIEWS.has(type);
 if(!eligible()||(ambientPreview?options.ambience:options.effects)===0||options.master===0||scope!==current.scope&&!event.preview)return false;
 const generation=transientGeneration,previewStamp=previewGeneration,startedAt=performance.now();
 try{
  if(type==='dice'||type==='magic'){synthesized(type,event.preview===true);emit('zz:audio-cue',{scope,id,type,synthetic:true,preview:event.preview===true});return true;}
  const asset={hit:'metal',combat:'metal',move:'footstep'}[type]||type;
  if(!EFFECT_PREVIEWS.has(asset)&&!ambientPreview)return false;
  const {clip,buffer}=await loadClip(asset);
  if(generation!==transientGeneration||event.preview===true&&previewStamp!==previewGeneration||performance.now()-startedAt>EFFECT_FRESHNESS_MS||!eligible()||(ambientPreview?options.ambience:options.effects)===0||options.master===0||scope!==current.scope&&!event.preview)return false;
  const source=context.createBufferSource(),gain=context.createGain(),offset=Math.min(clip.offset||0,Math.max(0,buffer.duration-.1)),duration=Math.min(ambientPreview?5:clip.limit||2,buffer.duration-offset),now=context.currentTime,fade=ambientPreview?.35:.08;
  source.buffer=buffer;source.connect(gain);gain.connect(ambientPreview?ambienceBus:effectsBus);gain.gain.setValueAtTime(0,now);gain.gain.linearRampToValueAtTime(clip.gain||.4,now+(ambientPreview?.12:.015));gain.gain.setValueAtTime(clip.gain||.4,now+Math.max(.02,duration-fade));gain.gain.linearRampToValueAtTime(0,now+duration);beginEffect(source,gain,event.preview===true);source.start(now,offset,duration);
  emit('zz:audio-cue',{scope,id,type,asset,synthetic:false,preview:!!event.preview,bus:ambientPreview?'ambience':'effects',duration});return true;
 }catch{emit('zz:audio-status',{available:false,message:'Не удалось загрузить звук. Игровой результат сохранён.'});return false;}
}
function configure(value){const next=readOptions(value);if(Object.keys(next).some(key=>next[key]!==options[key]))transientGeneration++;options=next;updateVolumes();if(paused()||options.master===0)stopEffects(0);visibility();if(!unlocked&&!options.muted&&navigator.userActivation?.isActive)unlock();else refreshAmbient();return {...options};}
function updateContext(value={}){
 const next={scope:typeof value.scope==='string'?value.scope.slice(0,200):'',view:String(value.view||''),terrain:String(value.terrain||''),locationType:String(value.locationType||''),inCombat:value.inCombat===true,ambientOverride:value.ambientOverride==='silent'||AMBIENT_PREVIEWS.has(value.ambientOverride)?value.ambientOverride:'auto'};
 if(next.scope!==current.scope){for(const id of Array.isArray(value.eventIds)?value.eventIds:[])if(typeof id==='string'&&id.length<=250)mark(next.scope+'|'+id);stopTransient();stopAmbient();}
 current=next;refreshAmbient();
}
function visibility(){
 const isHidden=hidden();if(isHidden!==lastHidden){transientGeneration++;lastHidden=isHidden;}
 updateVolumes();if(isHidden&&options.hiddenBehavior==='pause'){stopEffects(0);stopAmbient(0);context?.suspend().catch(()=>{});}else if(context&&unlocked){context.resume().then(()=>refreshAmbient()).catch(()=>{});}
}
document.addEventListener('pointerdown',event=>{if(event.isTrusted&&!unlocked)unlock();},{passive:true});
document.addEventListener('keydown',event=>{if(event.isTrusted&&!unlocked)unlock();},{passive:true});
document.addEventListener('visibilitychange',visibility);
window.addEventListener('zz-desktop-visibility',event=>{if(typeof event.detail?.active==='boolean'){desktopActive=event.detail.active;visibility();}});
window.addEventListener('pagehide',()=>{stopTransient();stopAmbient(0);context?.suspend().catch(()=>{});});
export const gameAudio=Object.freeze({configure,updateContext,playEvent,unlock,stopTransient,stopPreview,test:async(type='metal')=>{if(!EFFECT_PREVIEWS.has(type)&&!AMBIENT_PREVIEWS.has(type)&&!['dice','magic'].includes(type))return false;const generation=transientGeneration,previewStamp=previewGeneration;if(!await unlock()||generation!==transientGeneration||previewStamp!==previewGeneration)return false;return playEvent({scope:current.scope,id:'preview-'+Date.now()+'-'+(++previewSequence),type,preview:true});},getState:()=>({options:{...options},unlocked,activeEffects:effects.length,ambient:ambientKey,ambientOverride:current.ambientOverride,hidden:hidden(),scope:current.scope,cache:{decodedCount:buffers.size,decodedBytes:bufferBytes,inflightCount:inflight.size,activeDecodes,queuedDecodes:decodeQueue.length,peakDecodes,totalDecodes,maxBuffers:MAX_BUFFERS,maxBytes:MAX_BUFFER_BYTES,maxDecodes:MAX_DECODES}})});
window.ZZAudio=gameAudio;
