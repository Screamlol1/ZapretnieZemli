const test=require('node:test'),assert=require('node:assert/strict');
const {connectionURL,sameOrigin,safeExternal}=require('../policy.cjs');
test('Connect normalizes a server URL without retaining tokens or credentials',()=>{
 assert.equal(connectionURL(' https://game.example/path?token=secret#invite '),'https://game.example/');
 for(const raw of ['javascript:alert(1)','file:///C:/Windows','data:text/html,hello','http://game.example','https://user:password@game.example','not a URL',null])assert.throws(()=>connectionURL(raw));
});
test('Only loopback may use HTTP; external windows cannot escape their origin',()=>{
 for(const host of ['localhost','127.0.0.1','[::1]'])assert.equal(connectionURL(`http://${host}:8791/game`),`http://${host}:8791/`);
 assert.throws(()=>connectionURL('http://localhost.attacker.example/'));
 assert.equal(sameOrigin('https://game.example/account.html','https://game.example/'),true);
 for(const target of ['https://game.example.attacker.test','http://game.example','file:///etc/passwd','javascript:alert(1)'])assert.equal(sameOrigin(target,'https://game.example'),false);
 assert.equal(safeExternal('https://example.com/help'),true);
 for(const target of ['file:///C:/Windows','shell:startup','https://user:pass@example.com','javascript:alert(1)'])assert.equal(safeExternal(target),false);
});
