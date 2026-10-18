// One bounded request; mutations are never automatically repeated.
export async function requestJson(path,{data,token='',etag='',timeout=12000,fetchImpl=fetch}={}){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
 try{
  const response=await fetchImpl('/api/'+path,{method:data===undefined?'GET':'POST',signal:controller.signal,headers:{'Content-Type':'application/json',Authorization:token,...(etag?{'If-None-Match':etag}:{})},body:data===undefined?undefined:JSON.stringify(data)});
  if(response.status===304)return {body:null,etag};
  let body;try{body=await response.json();}catch{throw Error('Сервер временно недоступен. Подождите восстановления связи.');}
  if(!response.ok){const e=Error(body.error||'Не удалось выполнить запрос.');e.status=response.status;throw e;}
  return {body,etag:response.headers.get('ETag')||''};
 }catch(e){
  if(controller.signal.aborted)throw Error(data===undefined?'Сервер не отвечает. Повторяем подключение…':'Ответ сервера не получен. Проверьте результат перед повтором действия.');
  if(e instanceof TypeError)throw Error('Нет связи с сервером. Проверьте подключение к интернету.');
  throw e;
 }finally{clearTimeout(timer);}
}
export function acceptState(current,next){return !!next&&(!current||next.id!==current.id||next.revision>=current.revision);}
