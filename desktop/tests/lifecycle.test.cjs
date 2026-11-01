const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {EventEmitter}=require('node:events');

const source=fs.readFileSync(path.join(__dirname,'../host.cjs'),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));

function fixture({mkdir=async()=>{}}={}){
 const children=[],logs=[];
 const fakeFs={promises:{mkdir,access:async()=>{}},existsSync:()=>false,appendFileSync:(_name,line)=>logs.push(String(line))};
 const spawn=()=>{
  const child=new EventEmitter();child.stdout=new EventEmitter();child.stderr=new EventEmitter();child.stdin=new EventEmitter();child.exitCode=null;child.writes=[];
  child.stdin.write=line=>child.writes.push(JSON.parse(line));
  child.stdin.end=line=>{if(line)child.writes.push(JSON.parse(line));};
  child.exit=(code=0)=>{child.exitCode=code;child.emit('exit',code);child.emit('close',code);};
  child.kill=()=>child.exit(1);
  child.ready=()=>child.stdout.emit('data',Buffer.from('{"type":"ready","url":"http://127.0.0.1:12345/"}\n'));
  children.push(child);return child;
 };
 const output={exports:{}};
 vm.runInNewContext(source,{module:output,exports:output.exports,process,setTimeout,clearTimeout,URL,
  require:id=>id==='node:fs'?fakeFs:id==='node:child_process'?{spawn}:require(id)});
 const host=new output.exports.GameHost({resources:'resources',data:'data'}),states=[];
 host.on('state',state=>states.push(state));
 return {host,children,logs,states};
}

test('shutdown waits for a pending startup and never spawns after filesystem checks finish',async()=>{
 let release;
 const gate=new Promise(resolve=>release=resolve);
 const {host,children,states}=fixture({mkdir:()=>gate});
 const startup=assert.rejects(host.start(),/Приложение закрывается/);
 let stopped=false;
 const shutdown=host.stop().then(()=>stopped=true);
 await tick();assert.equal(stopped,false,'stop must wait for the cancelled startup');
 release();await Promise.all([startup,shutdown]);
 assert.equal(children.length,0,'no server may launch after stop');
 assert.equal(host.state.server,'stopped');
 assert.equal(host.state.error,'');
 assert.equal(states.some(state=>state.server==='running'||state.server==='error'),false);
});

test('a late ready message during shutdown cannot restore running state',async()=>{
 const {host,children,states}=fixture();
 const startup=assert.rejects(host.start(),/Приложение закрывается/);
 await tick();assert.equal(children.length,1);
 const child=children[0],shutdown=host.stop();
 assert.equal(child.writes[0].op,'stop');
 child.ready();child.exit();
 await Promise.all([startup,shutdown]);
 assert.equal(host.child,null);
 assert.equal(host.state.server,'stopped');
 assert.equal(states.some(state=>state.server==='running'||state.server==='error'),false);
});

test('broken command pipe rejects a pending backup and is handled during shutdown',async()=>{
 const {host,children,logs}=fixture();
 const startup=host.start();await tick();const child=children[0];child.ready();await startup;
 const backup=assert.rejects(host.backup('backup-folder'),/Связь со встроенным сервером прервалась.*EPIPE/);
 await tick();assert.equal(child.writes[0].op,'backup');
 const failure=()=>Object.assign(new Error('write EPIPE'),{code:'EPIPE'});
 assert.doesNotThrow(()=>child.stdin.emit('error',failure()));
 await backup;
 assert.equal(host.pending.size,0);
 assert.ok(logs.some(line=>line.includes('EPIPE')));
 const shutdown=host.stop();
 assert.doesNotThrow(()=>child.stdin.emit('error',failure()));
 child.exit();await shutdown;
 assert.equal(host.child,null);
 assert.equal(host.state.server,'stopped');
 assert.equal(host.state.error,'');
});
