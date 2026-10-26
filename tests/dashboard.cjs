// Real public payload and DOM interaction checks. No fixture is written to dist.
// Optional --http=http://127.0.0.1:8786 also verifies public-server isolation.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {parseHTML}=require('linkedom');
const root=path.resolve(__dirname,'..');
const dist=path.join(root,'site');
const allowedFiles=new Set(['index.html','app.js','styles.css','data/forecast.json','data/joint_seats.json','data/forecast.csv']);
const allowedRequests=new Set(['data/forecast.json','data/joint_seats.json']);
const actual=JSON.parse(fs.readFileSync(path.join(dist,'data/forecast.json'),'utf8'));
const actualJoint=JSON.parse(fs.readFileSync(path.join(dist,'data/joint_seats.json'),'utf8'));
const html=fs.readFileSync(path.join(dist,'index.html'),'utf8');
const app=fs.readFileSync(path.join(dist,'app.js'),'utf8');

function inventory(directory,prefix=''){
  return fs.readdirSync(directory,{withFileTypes:true}).flatMap(entry=>{
    const name=prefix+entry.name;
    assert.ok(!entry.isSymbolicLink(),`Public output must not contain a symlink: ${name}`);
    return entry.isDirectory()?inventory(path.join(directory,entry.name),name+'/'):[name];
  });
}

function assertNoResearchContent(text,label){
  for(const pattern of [/reports\//i,/artifacts\//i,/configs\//i,/data\/(raw|extracted|manifests)\//i,
    /input_manifest/i,/decision_log/i,/forecast_roadmap/i,/research-2026-/i,/C:\\Users\\/i,
    /LOCAL RESEARCH/,/Research pilot/,/Original bytes hashed/,/uv run knesset/]){
    assert.ok(!pattern.test(text),`${label} includes internal research content: ${pattern}`);
  }
}

async function harness({forecast=actual,joint=actualJoint}={}){
  const {window,document}=parseHTML(html);
  Object.defineProperty(window.HTMLInputElement.prototype,'checked',{configurable:true,
    get(){return this.hasAttribute('checked');},set(value){if(value)this.setAttribute('checked','');else this.removeAttribute('checked');}});
  const requests=[];
  const location=new URL('http://localhost/?run=research-2026-untrusted&scenario=untrusted');
  const context={window,document,URL,URLSearchParams,console,location,
    history:{replaceState(_state,_title,url){location.href=new URL(url,location).href;}},
    fetch:async url=>{
      const name=String(url).replace(/^\.\//,'');requests.push(name);
      assert.ok(allowedRequests.has(name),`Public page requested an unapproved file: ${name}`);
      const body=name==='data/forecast.json'?forecast:joint;
      return {ok:true,json:async()=>JSON.parse(JSON.stringify(body))};
    }};
  const sandbox=vm.createContext(context);
  await vm.runInContext(app,sandbox,{filename:'web/app.js'});
  return {window,document,sandbox,requests};
}

function event(document,window,id,type){document.getElementById(id).dispatchEvent(new window.Event(type));}
function readNumber(element){return Number.parseFloat(element.textContent.replace(/,/g,''));}
function rowFor(document,id){return [...document.querySelectorAll('#forecast-rows tr')].find(row=>row.getAttribute('data-list-id')===id);}
function visibleOptions(document){return [...document.querySelectorAll('#group-options label')].filter(label=>!label.hidden);}

async function main(){
  assert.deepEqual(new Set(inventory(dist)),allowedFiles,'Public output is an explicit six-file allowlist');
  assert.equal(actual.schema_version,'1.0');assert.equal(actual.model_family,'dynamic_vote_forecast');
  assert.equal(actual.forecast.lists.length,37);assert.equal(actual.poll_count,69);assert.equal(actual.series_count,6);
  assert.equal(actual.seat_count,120);assert.equal(actual.forecast.n_draws,4000);
  assert.equal(actual.joint_draws_file,'data/joint_seats.json');assert.equal(actual.csv_file,'data/forecast.csv');
  const allowedTop=new Set(['schema_version','forecast_id','model_family','election_date','as_of','issued_at','poll_count','series_count','seat_count','forecast','sources','assumptions','joint_draws_file','csv_file']);
  assert.deepEqual(new Set(Object.keys(actual)),allowedTop,'Public forecast schema must not inherit research fields');
  assert.deepEqual(new Set(Object.keys(actualJoint)),new Set(['schema_version','forecast_id','model_family','list_ids','n_draws','seat_draws']));
  assertNoResearchContent(JSON.stringify(actual),'Public payload');
  for(const file of ['index.html','app.js','data/forecast.csv'])assertNoResearchContent(fs.readFileSync(path.join(dist,file),'utf8'),file);

  const {window,document,sandbox,requests}=await harness();
  assert.equal(document.getElementById('load-error').hidden,true,document.getElementById('load-error').textContent);
  assert.equal(readNumber(document.getElementById('poll-count')),actual.poll_count);
  assert.equal(document.querySelectorAll('#forecast-rows tr').length,12);
  assert.equal(document.querySelectorAll('#source-rows tr').length,actual.sources.length);
  assert.equal(document.querySelectorAll('#group-options input').length,actual.forecast.lists.length);
  assert.equal(document.getElementById('modal-outcome').hidden,false);
  const modeRows=[...document.querySelectorAll('#mode-rows tr')];
  assert.equal(modeRows.length,11);
  assert.equal(modeRows.reduce((sum,row)=>sum+readNumber(row.querySelectorAll('td')[1]),0),120);
  for(const row of modeRows)assert.equal(readNumber(row.querySelectorAll('td')[1]),actual.forecast.joint_mode.seats[row.getAttribute('data-list-id')]);
  assert.ok(document.getElementById('mode-probability').textContent.includes('2.4 million'));
  event(document,window,'show-all-lists','click');
  assert.equal(document.querySelectorAll('#forecast-rows tr').length,actual.forecast.lists.length);
  for(const list of actual.forecast.lists){
    const row=rowFor(document,list.id);assert.ok(row,`Missing list ${list.id}`);
    const cells=row.querySelectorAll('td');
    assert.ok(cells[0].textContent.includes(list.name_en||list.name_he));
    assert.equal(readNumber(cells[1]),Number(list.mean_seats.toFixed(1)));
    assert.equal(readNumber(cells[2]),actual.forecast.joint_mode.seats[list.id]);
    const interval=cells[3].textContent.match(/\d+/g).map(Number);
    assert.deepEqual(interval,list.interval_80);
  }
  event(document,window,'show-all-lists','click');
  assert.equal(document.querySelectorAll('#forecast-rows tr').length,12);
  assert.ok(document.getElementById('show-all-lists').textContent.includes('37'));

  await vm.runInContext('loadJointSeats()',sandbox);
  const order=[...actual.forecast.lists].sort((a,b)=>b.mean_seats-a.mean_seats);
  const selected=order.slice(0,4).map(row=>row.id);
  const boxes=[...document.querySelectorAll('#group-options input')];
  boxes.forEach(box=>{box.checked=selected.includes(box.value);box.dispatchEvent(new window.Event('change',{bubbles:true}));});
  await vm.runInContext('renderGroup()',sandbox);
  const indices=selected.map(id=>actualJoint.list_ids.indexOf(id));
  const totals=actualJoint.seat_draws.map(row=>indices.reduce((sum,j)=>sum+row[j],0));
  const probability=totals.filter(n=>n>=61).length/totals.length;
  assert.equal(readNumber(document.getElementById('group-probability')),Number((100*probability).toFixed(1)));
  assert.equal(readNumber(document.getElementById('group-mean')),Number((totals.reduce((a,b)=>a+b,0)/totals.length).toFixed(1)));
  const names=document.getElementById('group-selected-names').textContent;
  selected.forEach(id=>assert.ok(names.includes(actual.forecast.lists.find(row=>row.id===id).name_en)));

  const search=document.getElementById('group-search');search.value=order[0].name_en;
  event(document,window,'group-search','input');
  assert.ok(visibleOptions(document).length<boxes.length);
  assert.ok(visibleOptions(document).some(label=>label.textContent.includes(order[0].name_en)));
  assert.equal(readNumber(document.getElementById('group-probability')),Number((100*probability).toFixed(1)),'Filtering must preserve selected group');
  search.value='';event(document,window,'group-search','input');
  assert.equal(visibleOptions(document).length,actual.forecast.lists.length);
  [...document.querySelectorAll('#group-options input')].forEach(box=>{box.checked=true;box.dispatchEvent(new window.Event('change',{bubbles:true}));});
  await vm.runInContext('renderGroup()',sandbox);
  assert.equal(readNumber(document.getElementById('group-probability')),100);
  assert.equal(readNumber(document.getElementById('group-mean')),120);
  event(document,window,'group-clear','click');
  assert.equal(document.querySelectorAll('#group-options input:checked').length,0);

  assert.equal(document.getElementById('download-forecast').getAttribute('href'),actual.csv_file);
  assertNoResearchContent(document.body.textContent,'Rendered public page');
  assert.ok(!document.body.textContent.includes('2026:'),'Internal list identifiers must not replace readable names');
  for(const element of document.querySelectorAll('a[href],link[href],script[src]')){
    const href=element.getAttribute('href')||element.getAttribute('src');
    if(href.startsWith('#')){assert.ok(document.getElementById(href.slice(1)),`Broken anchor ${href}`);continue;}
    if(/^https?:/.test(href)){assert.ok(actual.sources.some(s=>decodeURI(new URL(s.url).href)===decodeURI(new URL(href).href))||href==='https://www.marcel-neunhoeffer.com/pdf/papers/pa_forecast-multiparty.pdf','External links must be reviewed public sources: '+href);continue;}
    assert.ok(allowedFiles.has(href),`Unexpected public link ${href}`);
    assert.ok(fs.existsSync(path.join(dist,href)),`Missing public asset ${href}`);
  }
  assert.deepEqual(new Set(requests),allowedRequests);
  assert.ok(document.querySelector('label[for="group-search"]'));
  assert.ok(document.getElementById('group-result').closest('[aria-live]'));

  // Isolated adversarial text stays in memory; never changes the published data.
  const hostile=JSON.parse(JSON.stringify(actual));
  const marker='<img src=x onerror="injected()">';
  hostile.forecast.lists[0].name_en=marker;
  hostile.sources[0].publisher=marker;hostile.sources[0].url='javascript:injected()';
  const escaped=await harness({forecast:hostile});
  assert.equal(escaped.document.querySelectorAll('img[onerror],script:not([src])').length,0);
  assert.ok(escaped.document.body.textContent.includes(marker),'Untrusted names must render as literal text');
  assert.ok([...escaped.document.querySelectorAll('a[href]')].every(a=>!/^javascript:/i.test(a.getAttribute('href'))));

  for(const patch of [
    {forecast_id:'wrong-forecast'}, {model_family:'vote_share_forecast'},
    {list_ids:['wrong-list',...actualJoint.list_ids.slice(1)]},
    {seat_draws:[actualJoint.seat_draws[0].map((n,i)=>i? n:n+1),...actualJoint.seat_draws.slice(1)]}
  ]){
    const invalid=await harness({joint:{...actualJoint,...patch}});
    await assert.rejects(vm.runInContext('loadJointSeats()',invalid.sandbox));
  }

  console.log('Public DOM: actual37-list forecast, top12/all-list toggle, source links, search, joint majority and clear selection passed.');
  console.log('Public guards: six-file allowlist, payload/request isolation, literal text escaping and joint forecast identity/conservation passed.');
  console.log('Visual browser layout remains unverified; this is a DOM and HTTP check.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
