const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const source = path.join(__dirname, '../src/components/ajin.ts');
const compiled = new Module(source, module);
compiled._compile(ts.transpileModule(fs.readFileSync(source, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, source);
const { ajinRows, filterRows, parseCoordinates, hasCoordinates, canShowOnMap, portSummary, signalValue, onuStatus, telemetryCSV, readAjinResponse, incidentHistory, timestamp } = compiled.exports;

test('filters combine search, dynamic port and status without changing the inventory', () => {
  const rows = [
    { id:10, port:'Slot9-PON3', name:'Ponto 10', desc:'Rua São João', status:'Online' },
    { id:2, port:'Slot9-PON3', name:'Ponto 2', desc:'Rua São João', status:'Offline' },
    { id:1, port:'Slot1-PON1', name:'Ponto 1', status:'Online' },
  ];
  assert.deepEqual(filterRows(rows, 'sao joao', 'Slot9-PON3', 'offline', 'name', true).map(row=>row.id), [2]);
  assert.deepEqual(filterRows(rows, '', '', 'all', 'name', true).map(row=>row.id), [1,2,10]);
  assert.deepEqual(rows.map(row=>row.id), [10,2,1]);
  assert.deepEqual(portSummary(rows).map(port=>[port.port,port.total,port.offline]), [['Slot1-PON1',1,0],['Slot9-PON3',2,1]]);
});
test('status is normalized and an unknown status is not an offline incident', () => {
  assert.equal(onuStatus({status:' online '}), 'online');
  assert.equal(onuStatus({status:'OFFLINE'}), 'offline');
  assert.equal(onuStatus({status:'pending'}), 'unknown');
  assert.equal(filterRows([{id:1,status:'pending'}], '', '', 'offline', 'name', true).length, 0);
});
test('duration sorting uses seconds and a missing optical signal is not fabricated', () => {
  assert.deepEqual(filterRows([{id:1,uptime_seconds:1000},{id:2,uptime_seconds:30}], '', '', 'all', 'uptime', true).map(row=>row.id), [2,1]);
  assert.equal(signalValue({uptime:'10 dias'}), '—');
  assert.equal(signalValue({rx_power:0}), '0');
  assert.deepEqual(filterRows([{id:1,signal:'-3 dBm'},{id:2,signal:'-21.4 dBm'}], '', '', 'all', 'signal', true).map(row=>row.id), [2,1]);
});
test('coordinates accept zero and decimal commas, and reject partial or invalid locations', () => {
  assert.deepEqual(parseCoordinates('0','0'), {latitude:0,longitude:0});
  assert.deepEqual(parseCoordinates('-27,43','-48.40'), {latitude:-27.43,longitude:-48.4});
  assert.deepEqual(parseCoordinates('',''), {latitude:null,longitude:null});
  for (const [lat,lon] of [['','2'],['91','2'],['2','181'],['NaN','2'],['0x10','2'],['2oops','2']]) {
    assert.throws(()=>parseCoordinates(lat,lon));
  }
  assert.equal(hasCoordinates({latitude:0,longitude:0}), true);
  assert.equal(hasCoordinates({latitude:Infinity,longitude:0}), false);
});
test('disabled points remain on the map when coordinates are valid', () => {
  const row={id:1,port:'PON-1',latitude:0,longitude:0,status:'Offline'};
  assert.equal(canShowOnMap(row),true);
  assert.equal(canShowOnMap({...row,map_enabled:false}),true);
  assert.equal(canShowOnMap({...row,map_enabled:true,latitude:null}),false);
  assert.equal(canShowOnMap({...row,map_enabled:true,longitude:181}),false);
  assert.equal(canShowOnMap({...row,map_enabled:true,latitude:NaN}),false);
  assert.equal(canShowOnMap({...row,map_enabled:true,longitude:Infinity}),false);
});

test('geographic points join the list as disabled without inventing ONU hardware data', () => {
  const data={rows:[{id:91,port:'PON1',name:'Ponto 01',status:'Online'}],inactive_points:[
    {number:4,address:'Rua A',latitude:-27,longitude:-48,map_enabled:false},
    {number:1,address:'Duplicado',latitude:0,longitude:0,map_enabled:false},
  ]};
  const rows=ajinRows(data);
  assert.equal(rows.length,2);
  assert.equal(rows[0],data.rows[0]);
  assert.equal(rows[1].name,'Ponto 04');
  assert.equal(rows[1].catalog_number,4);
  assert.equal(rows[1].port,'');
  assert.equal(rows[1].serial,undefined);
  assert.equal(rows[1].vendor,undefined);
  assert.equal(onuStatus(rows[1]),'disabled');
  assert.equal(canShowOnMap(rows[1]),true);
  assert.deepEqual(filterRows(rows,'','','disabled','name',true).map(row=>row.name),['Ponto 04']);
  assert.equal(filterRows(rows,'','','offline','name',true).length,0);
  assert.equal(filterRows(rows,'','','online','name',true).length,1);
  assert.equal(data.rows.length,1);
});

test('disabling an existing ONU overrides network status and excludes active incidents', () => {
  const row={id:91,port:'PON1',name:'Ponto 01',status:'Offline',map_enabled:false};
  assert.equal(onuStatus(row),'disabled');
  assert.equal(onuStatus({...row,status:'Online'}),'disabled');
  assert.equal(onuStatus({...row,map_enabled:true}),'offline');
  const active={port:'PON1',onu_id:91,since:'15/10/2026 às 12:00:00'};
  assert.equal(incidentHistory({rows:[row],active_problems:[active],events:[]}).length,0);
});
test('CSV quotes every cell, preserves UTF-8/newlines and prevents formula execution', () => {
  const csv = telemetryCSV([{id:1, port:'PON;1', name:'Ponto "A" #1', desc:'Rua; São\nJoão', serial:'=1+1'}]);
  assert.ok(csv.startsWith('\uFEFF'));
  assert.ok(csv.includes('"Ponto ""A"" #1"'));
  assert.ok(csv.includes('"Rua; São\nJoão"'));
  assert.ok(csv.includes('"\'=1+1"'));
  assert.ok(csv.includes('"PON;1"'));
});
test('API errors surface to the dialog instead of being treated as saved data', async () => {
  await assert.rejects(readAjinResponse({ok:false,json:async()=>({detail:'Coletor indisponível'})}), /Coletor indisponível/);
  await assert.rejects(readAjinResponse({ok:true,json:async()=>({status:'saved'})}), /Resposta inválida/);
  assert.deepEqual(await readAjinResponse({ok:true,json:async()=>({telemetry:{rows:[]}})}), {rows:[]});
});

const base = {rows:[{id:'1',port:'PON-1',name:'Ponto 1',status:'Online',serial:'AA'}],active_problems:[]};
const transition = (type, stamp, extra={}) => ({port:'PON-1',onu_id:'1',serial:'AA',type,timestamp:`2026-10-15T${stamp}`, ...extra});
test('incident history pairs each outage with its recovery instead of listing falls as open forever', () => {
  const events = [transition('rose','10:01:00'),transition('fell','10:00:00'),transition('rose','09:05:00'),transition('fell','09:00:00')];
  const result = incidentHistory({...base,events_history:events});
  assert.equal(result.length,2);
  assert.deepEqual(result.map(item=>[item.status,item.durationSeconds]),[['resolved',60],['resolved',300]]);
  assert.equal(result[0].recovered,timestamp('2026-10-15T10:01:00'));
});
test('only current problems are open, and duplicated falls are one incident', () => {
  const fell=transition('fell','10:00:00');
  const result=incidentHistory({...base,events_history:[fell,{...fell,id:'duplicate'},transition('fell','10:00:01')],
    active_problems:[{port:'PON-1',onu_id:'1',serial:'AA',since:'15/10/2026 às 10:00:00',duration_seconds:90}]});
  assert.equal(result.length,1);
  assert.equal(result[0].status,'open');assert.equal(result[0].durationSeconds,90);
  assert.equal(incidentHistory({...base,events_history:[fell]})[0].status,'unconfirmed');
});
test('truncated history reconstructs a known outage duration, but never fabricates a missing start', () => {
  const result=incidentHistory({...base,events_history:[transition('rose','10:05:00',{downtime_seconds:300})]});
  assert.equal(result[0].opened,timestamp('2026-10-15T10:00:00'));
  const unknown=incidentHistory({...base,events_history:[transition('rose','10:05:00',{downtime_seconds:0})]});
  assert.equal(unknown[0].opened,null);assert.equal(unknown[0].durationSeconds,undefined);
});
test('different serials reusing an ONU ID must never be paired into the same incident', () => {
  const result=incidentHistory({...base,events_history:[transition('fell','10:00:00'),transition('rose','10:01:00',{serial:'BB'})]});
  assert.equal(result.length,2);
  assert.deepEqual(result.map(item=>item.status).sort(),['resolved','unconfirmed']);
});
test('legacy active problem counts fall back to offline rows, including events outside the retained history', () => {
  const result=incidentHistory({...base,active_problems:1,rows:[{id:2,port:'PON-2',status:'Offline',status_since:'15/10/2026 às 08:00:00',uptime_seconds:7200}]});
  assert.equal(result.length,1);assert.equal(result[0].status,'open');assert.equal(result[0].durationSeconds,7200);
});
