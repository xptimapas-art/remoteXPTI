const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
function load(name){const source=path.join(__dirname,'../src/components/'+name+'.ts');const compiled=new Module(source,module);compiled._compile(ts.transpileModule(fs.readFileSync(source,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,source);return compiled.exports;}
const {emptyServerDraft,serverPayload,pastedCoordinates,readServerGroups,serverRequest}=load('serverForm');
const {hasServerLocation}=load('serverMap');
const draft=()=>({...emptyServerDraft(),name:'COPE',host:'192.0.2.1'});
test('city and UF work independently of the server name; empty location is allowed',()=>{
 assert.equal(serverPayload(draft()).latitude,null);
 const result=serverPayload({...draft(),city:' Florianópolis ',state:'SC'});
 assert.equal(result.name,'COPE');assert.equal(result.city,'Florianópolis');assert.equal(result.latitude,null);
 assert.throws(()=>serverPayload({...draft(),city:'Florianópolis'}),/cidade e estado/);
});
test('exact coordinates accept decimal commas and zero, reject partial numbers and invalid ranges',()=>{
 assert.equal(serverPayload({...draft(),latitude:'0',longitude:'0'}).latitude,0);
 assert.equal(serverPayload({...draft(),latitude:'-27,5',longitude:'-48,5'}).longitude,-48.5);
 for(const [latitude,longitude] of [['1',''],['91','2'],['0','181'],['27foo','2'],['NaN','1']])assert.throws(()=>serverPayload({...draft(),latitude,longitude}),/latitude/);
});
test('port cannot silently become 3389 when blank or invalid',()=>{
 for(const port of ['', '0','65536','3389.5','invalid'])assert.throws(()=>serverPayload({...draft(),port}),/porta/);
});
test('pasted coordinate pairs fill the two fields, including decimal-comma values separated by semicolon',()=>{
 assert.deepEqual(pastedCoordinates('-27.5, -48.5'),['-27.5','-48.5']);
 assert.deepEqual(pastedCoordinates('-27,5; -48,5'),['-27,5','-48,5']);
 assert.equal(pastedCoordinates('not coordinates'),null);
});
test('group response must include real counts and permissions',()=>{
 assert.throws(()=>readServerGroups({groups:[{name:'XPTI'}]}),/não confirmou/);
 assert.equal(readServerGroups({groups:[{name:'XPTI',server_count:0,rename_allowed:true,delete_allowed:true}]}).length,1);
});
test('map accepts zero and rejects incomplete or non-finite coordinates',()=>{
 assert.equal(hasServerLocation({latitude:0,longitude:0}),true);
 for(const value of [{latitude:null,longitude:0},{latitude:NaN,longitude:1},{latitude:1,longitude:181}])assert.equal(hasServerLocation(value),false);
});
test('failed group save remains an error, never a successful local edit',async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify({detail:'Grupo contém servidores.'}),{status:409}));
 await assert.rejects(serverRequest('/api/groups','DELETE',{name:'BEMTEVI'}),/contém servidores/);
});
