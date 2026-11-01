import assert from 'node:assert/strict';
import {requestJson,acceptState} from '../public/network.js';
let calls=0;
const result=await requestJson('state',{token:'private',etag:'old',fetchImpl:async (url,options)=>{
 calls++;assert.equal(url,'/api/state');assert.equal(options.headers.Authorization,'private');assert.equal(options.headers['If-None-Match'],'old');
 return new Response(null,{status:304});
}});
assert.deepEqual(result,{body:null,etag:'old'});assert.equal(calls,1);
await assert.rejects(requestJson('state',{fetchImpl:async()=>new Response('<html>Gateway down</html>',{status:502})}),/временно недоступен/);
await assert.rejects(requestJson('state',{fetchImpl:async()=>new Response('{"error":"Войдите снова"}',{status:403})}),e=>e.status===403);
calls=0;
await assert.rejects(requestJson('action',{data:{action:'chat'},timeout:5,fetchImpl:async(url,{signal})=>{
 calls++;return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))));
}}),/Проверьте результат перед повтором/);
assert.equal(calls,1,'Never retry a mutation with uncertain outcome');
assert.equal(acceptState({id:'a',revision:5},{id:'a',revision:4}),false);
assert.equal(acceptState({id:'a',revision:5},{id:'a',revision:5}),true);
assert.equal(acceptState({id:'a',revision:5},null),false);
assert.equal(acceptState({id:'a',revision:5},{id:'b',revision:0}),true);
console.log('Network: conditional responses, errors, bounded requests and stale state passed.');
