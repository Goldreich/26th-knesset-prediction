"use strict";
const $ = id => document.getElementById(id);
let data, jointDraws, showAllLists=false;
const selectedIds=new Set();
const visibleLimit=12;
let jointPromise=null;

function element(tag,text,className){
  const node=document.createElement(tag);
  if(text!==undefined&&text!==null)node.textContent=String(text);
  if(className)node.className=className;
  return node;
}
function number(value,digits=1){return Number(value).toFixed(digits);}
function day(value){
  if(!value)return "";
  const date=new Date(String(value).slice(0,10)+"T12:00:00Z");
  return Number.isNaN(date.getTime())?"":new Intl.DateTimeFormat("en-GB",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"}).format(date);
}
function timestamp(value){
  const date=new Date(value);
  return Number.isNaN(date.getTime())?"":new Intl.DateTimeFormat("en-GB",{day:"numeric",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",timeZone:"Asia/Jerusalem"}).format(date)+" Israel time";
}
function publicFile(path){
  if(typeof path!=="string"||!/^data\/[a-z0-9_-]+\.(json|csv)$/.test(path))throw new Error("Unavailable data file");
  return path;
}
function sourceURL(value){
  try{const url=new URL(value);return ["https:","http:"].includes(url.protocol)?url.href:null;}catch{return null;}
}
function orderedLists(){
  return [...data.forecast.lists].sort((a,b)=>b.mean_seats-a.mean_seats||nameOf(a).localeCompare(nameOf(b)));
}
function nameOf(row){return row.name_en||row.name_he||"Unnamed list";}
function validateForecast(value){
  if(value.schema_version!=="1.0"||!["seat_poll_forecast","dynamic_vote_forecast"].includes(value.model_family)||typeof value.forecast_id!=="string"||!value.forecast_id||value.seat_count!==120)throw new Error("Unavailable forecast");
  const lists=value.forecast?.lists;
  if(!Array.isArray(lists)||!lists.length||new Set(lists.map(row=>row.id)).size!==lists.length)throw new Error("Unavailable forecast");
  if(!Number.isInteger(value.forecast.n_draws)||value.forecast.n_draws<2)throw new Error("Unavailable forecast");
  for(const row of lists){
    if(typeof row.id!=="string"||!row.id||!(row.name_en||row.name_he)||!Number.isFinite(row.mean_seats)||row.mean_seats<0||row.mean_seats>value.seat_count)throw new Error("Unavailable forecast");
    if(!Array.isArray(row.interval_80)||row.interval_80.length!==2||!row.interval_80.every(v=>Number.isInteger(v)&&v>=0&&v<=value.seat_count)||row.interval_80[0]>row.interval_80[1])throw new Error("Unavailable forecast");
  }
  if(Math.abs(lists.reduce((sum,row)=>sum+row.mean_seats,0)-value.seat_count)>0.001)throw new Error("Unavailable forecast");
  publicFile(value.joint_draws_file);publicFile(value.csv_file);
  return value;
}

function renderForecast(){
  const all=orderedLists(),rows=showAllLists?all:all.slice(0,visibleLimit);
  const maximum=Math.max(10,Math.ceil(Math.max(...all.map(row=>Math.max(row.interval_80[1],row.mean_seats)))/10)*10);
  $("range-scale").replaceChildren(element("span","0"),element("span",maximum+" seats"));
  $("forecast-rows").replaceChildren();
  for(const row of rows){
    const tr=element("tr");tr.dataset.listId=row.id;
    tr.append(element("td",nameOf(row)),element("td",number(row.mean_seats),"number"));
    if(Number.isFinite(row.mean_share)&&Number.isFinite(row.p_threshold)){
      tr.firstChild.append(element("small",number(row.mean_share*100)+"% votes · "+number(row.p_threshold*100,0)+"% chance of passing 3.25%", "vote-detail"));
    }
    const modalSeats=data.forecast.joint_mode?.seats?.[row.id];
    tr.append(element("td",Number.isInteger(modalSeats)?modalSeats:"—","number scenario-column"));
    const cell=element("td"),range=element("div",null,"range-cell"),track=element("div",null,"interval-track");
    track.setAttribute("aria-hidden","true");
    const band=element("span",null,"interval-band"),dot=element("span",null,"interval-dot");
    band.style.left=(row.interval_80[0]/maximum*100)+"%";
    band.style.width=((row.interval_80[1]-row.interval_80[0])/maximum*100)+"%";
    dot.style.left=(row.mean_seats/maximum*100)+"%";
    track.append(band,dot);
    const text=element("span",row.interval_80[0]+"–"+row.interval_80[1],"interval-value");
    text.setAttribute("aria-label","Central 80 percent range: "+row.interval_80[0]+" to "+row.interval_80[1]+" seats");
    range.append(track,text);cell.append(range);tr.append(cell);$("forecast-rows").append(tr);
  }
  $("show-all-lists").hidden=all.length<=visibleLimit;
  $("show-all-lists").textContent=showAllLists?"Show leading lists":"Show all "+all.length+" lists";
  $("show-all-lists").setAttribute("aria-expanded",String(showAllLists));
  $("forecast-scope-note").textContent=showAllLists?"All "+all.length+" lists in the provisional ballot.":"Showing the "+rows.length+" largest expected totals. "+all.length+" lists are included.";
}

function renderGroupOptions(){
  const query=$("group-search").value.trim().toLocaleLowerCase();
  $("group-options").replaceChildren();
  let matches=0;
  for(const row of orderedLists()){
    const label=element("label"),input=element("input");input.type="checkbox";input.value=row.id;input.checked=selectedIds.has(row.id);
    label.hidden=!!query&&!((row.name_en||"")+" "+(row.name_he||"")).toLocaleLowerCase().includes(query);
    if(!label.hidden)matches++;
    input.addEventListener("change",()=>{
      if(input.checked)selectedIds.add(row.id);else selectedIds.delete(row.id);
      renderGroup();
    });
    label.append(input,element("span",nameOf(row)));$("group-options").append(label);
  }
  $("group-search-empty").hidden=matches>0;
}

async function loadJointSeats(){
  if(jointDraws)return jointDraws;
  if(!jointPromise)jointPromise=(async()=>{
    const response=await fetch(publicFile(data.joint_draws_file));
    if(!response.ok)throw new Error("Majority calculation unavailable");
    const draws=await response.json(),expected=new Set(data.forecast.lists.map(row=>row.id));
    if(draws.schema_version!=="1.0"||draws.model_family!==data.model_family||draws.forecast_id!==data.forecast_id)throw new Error("Joint forecast identity mismatch");
    if(!Array.isArray(draws.list_ids)||draws.list_ids.length!==expected.size||new Set(draws.list_ids).size!==expected.size||!draws.list_ids.every(id=>expected.has(id)))throw new Error("Joint list identity mismatch");
    if(draws.n_draws!==data.forecast.n_draws||!Array.isArray(draws.seat_draws)||draws.seat_draws.length!==data.forecast.n_draws||!draws.seat_draws.every(row=>Array.isArray(row)&&row.length===draws.list_ids.length&&row.every(v=>Number.isInteger(v)&&v>=0)&&row.reduce((sum,v)=>sum+v,0)===data.seat_count))throw new Error("Joint seat totals mismatch");
    jointDraws=draws;
    return draws;
  })().catch(error=>{jointPromise=null;throw error;});
  return jointPromise;
}

function renderGroup(){
  const chosen=orderedLists().filter(row=>selectedIds.has(row.id));
  $("group-selected-names").textContent=chosen.map(nameOf).join(" · ");
  $("group-clear").disabled=chosen.length===0;
  if(!chosen.length){
    $("group-probability").textContent="—";$("group-mean").textContent="—";
    $("group-result").textContent="Select lists to explore a possible majority.";
    return;
  }
  if(!jointDraws){
    $("group-result").textContent="Loading the majority estimate…";
    return loadJointSeats().then(()=>renderGroup()).catch(()=>{
      $("group-probability").textContent="—";$("group-mean").textContent="—";
      $("group-result").textContent="The majority estimate is temporarily unavailable. Please try again.";
    });
  }
  const columns=chosen.map(row=>jointDraws.list_ids.indexOf(row.id));
  const majority=Math.floor(data.seat_count/2)+1;
  let events=0,total=0;
  for(const seats of jointDraws.seat_draws){
    const count=columns.reduce((sum,j)=>sum+seats[j],0);total+=count;if(count>=majority)events++;
  }
  $("group-probability").textContent=number(events/jointDraws.n_draws*100)+"%";
  $("group-mean").textContent=number(total/jointDraws.n_draws);
  $("group-result").textContent="Model estimate for the "+chosen.length+" selected "+(chosen.length===1?"list.":"lists.");
}

function renderSources(){
  $("source-rows").replaceChildren();
  for(const source of data.sources||[]){
    const tr=element("tr"),publication=element("td"),url=sourceURL(source.url);
    const title=element(url?"a":"span",source.publisher||"Poll publication");
    if(url){title.href=url;title.target="_blank";title.rel="noopener noreferrer";}
    publication.append(title);
    if(source.firm)publication.append(element("small",source.firm));
    const dates=element("td"),start=day(source.fieldwork_start),end=day(source.fieldwork_end);
    if(start&&end)dates.append(element("span",start===end?end:start+" – "+end));
    else if(end){dates.append(element("span","Through "+end));dates.append(element("small","Fieldwork start not reported"));}
    else {dates.append(element("span",source.publication_date?"Published "+day(source.publication_date):"Date not reported"));dates.append(element("small","Fieldwork dates not reported"));}
    tr.append(publication,dates,element("td",Number.isInteger(source.sample_size)?source.sample_size.toLocaleString("en-GB"):"Not reported","number"));
    $("source-rows").append(tr);
  }
}

function renderMethods(){
  $("methods-summary").textContent="We combine "+data.poll_count+" national seat polls, weighting recent reports more heavily. Repeated polls from the same research series share their weight. Election uncertainty is informed by past elections and by explicit modeling assumptions.";
  if(data.model_family==="dynamic_vote_forecast")$("methods-summary").textContent="We fit changes in party support and pollster differences using "+data.poll_count+" national polls from "+data.series_count+" series. We project voting intentions to election day, add uncertainty shared across polls, and allocate 120 seats for every simulated vote result.";
  $("limitations").replaceChildren();
  for(const text of data.assumptions||[])$("limitations").append(element("li",text));
}

function renderJointMode(){
  const mode=data.forecast.joint_mode;if(!mode)return;
  if(mode.status!=="estimated"||!Number.isFinite(mode.probability)||mode.probability<=0||mode.probability>=1)throw new Error("Invalid modal outcome");
  const ids=data.forecast.lists.map(row=>row.id),values=Object.values(mode.seats||{});
  if(Object.keys(mode.seats).length!==ids.length||!ids.every(id=>Number.isInteger(mode.seats[id])&&mode.seats[id]>=0)||values.reduce((a,b)=>a+b,0)!==120)throw new Error("Invalid modal seats");
  $("mode-details").hidden=false;
  $("mode-probability").textContent="Estimated probability of this exact combination: "+(mode.probability*100).toPrecision(3)+"% — about 1 in "+number(1/mode.probability/1e6)+" million. Many other seat combinations are possible.";
  const runner=mode.alternatives?.[0];
  if(runner){
    const changes=data.forecast.lists.filter(row=>runner.seats[row.id]!==mode.seats[row.id]).map(row=>nameOf(row)+" "+runner.seats[row.id]+" seats");
    $("mode-alternative").textContent="Closest ranked alternative: "+changes.join(", ")+"; all other seats unchanged. The leading allocation is about "+number((mode.probability/runner.probability-1)*100)+"% more probable.";
  }
  $("mode-note").textContent=mode.note;
}

async function init(){
  const response=await fetch("data/forecast.json");
  if(!response.ok)throw new Error("Unavailable forecast");
  data=validateForecast(await response.json());
  $("election-date").textContent=day(data.election_date);
  $("as-of").textContent=timestamp(data.as_of);$("as-of").setAttribute("datetime",data.as_of);
  $("poll-count").textContent=String(data.poll_count);
  $("seat-count").textContent=String(data.seat_count);$("majority-count").textContent=String(Math.floor(data.seat_count/2)+1);
  $("download-forecast").href=publicFile(data.csv_file);
  $("show-all-lists").addEventListener("click",()=>{showAllLists=!showAllLists;renderForecast();});
  $("group-search").addEventListener("input",renderGroupOptions);
  $("group-clear").addEventListener("click",()=>{selectedIds.clear();renderGroupOptions();renderGroup();});
  renderForecast();renderGroupOptions();renderGroup();renderSources();renderMethods();renderJointMode();
}
init().catch(()=>{$("load-error").hidden=false;});
