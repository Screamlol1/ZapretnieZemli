const {URL}=require('node:url');
function connectionURL(raw){
 if(typeof raw!=='string'||raw.length>2048)throw Error('Введите ссылку на игровой стол.');
 let url;try{url=new URL(raw.trim());}catch{throw Error('Нужна полная ссылка, например https://имя-сервера/');}
 if(url.username||url.password)throw Error('Логин и пароль вводятся внутри игры, а не в ссылке.');
 if(url.protocol!=='https:'&&!(url.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(url.hostname)))throw Error('Для подключения нужна HTTPS-ссылка. HTTP разрешён только на этом компьютере.');
 url.hash='';url.search='';url.pathname='/';return url.href;
}
function sameOrigin(raw,base){try{return new URL(raw).origin===new URL(base).origin;}catch{return false;}}
function safeExternal(raw){try{const u=new URL(raw);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password;}catch{return false;}}
module.exports={connectionURL,sameOrigin,safeExternal};
