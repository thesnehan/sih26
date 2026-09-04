const API = window.PS73_API || "http://127.0.0.1:8000";
let stations = [], records = [], alerts = [], currentSection = "overview";

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const fmt = n => n == null ? "—" : Number(n).toFixed(1);
const time = s => s ? new Date(s).toLocaleString([], {month:"short",day:"2-digit",hour:"2-digit",minute:"2-digit"}) : "—";
const pill = s => `<span class="pill ${(s||"Normal").toLowerCase()}">${esc(s||"Normal")}</span>`;

function toast(msg){$("toast").textContent=msg;$("toast").classList.add("show");setTimeout(()=>$("toast").classList.remove("show"),2200)}
async function get(path){const r=await fetch(API+path);if(!r.ok)throw new Error(await r.text());return r.json()}

async function load(){
  try{
    const [st, w, a, health] = await Promise.all([
      get("/stations"), get("/weather?limit=240"), get("/anomalies?limit=30"), get("/health")
    ]);
    stations=st.stations; records=w.records; alerts=a.anomalies;
    $("apiBadge").className="badge ok";$("apiBadge").innerHTML='<span class="dot"></span> API online';
    $("stationCount").textContent=health.stations;
    $("readingCount").textContent=health.readings_loaded;
    $("anomalyCount").textContent=alerts.length;
    $("criticalCount").textContent=alerts.filter(x=>x.severity==="Critical").length;
    $("simStatus").className="sim-status "+(health.simulator_running?"running":"");
    $("simStatus").innerHTML=`<span class="dot"></span> Simulator ${health.simulator_running?"running":"stopped"}`;
    renderStations(); renderAlerts(); renderTable(); fillChartStations(); drawChart();
    $("stationUpdated").textContent="Updated "+new Date().toLocaleTimeString();
  }catch(e){
    $("apiBadge").className="badge"; $("apiBadge").innerHTML='<span class="dot"></span> API offline';
    toast("Backend not reachable. Start FastAPI on port 8000.");
  }
}

function renderStations(){
  $("stationCards").innerHTML=stations.slice(0,8).map(s=>{
    const l=s.latest||{}; return `<div class="station-card"><div class="line"><span class="station-id">${esc(s.station_id)}</span>${pill(l.severity)}</div>
      <div class="temp">${fmt(l.temperature)}°C</div><div class="station-meta">${fmt(l.humidity)}% humidity • ${fmt(l.wind_speed)} m/s wind</div></div>`
  }).join("");
}
function renderAlerts(){
  const list=alerts.slice(0,6);
  $("alertPreview").innerHTML=list.length?list.map(a=>`<div class="alert-row"><div class="line"><span class="alert-title">${esc(a.station_id)} • ${esc(a.anomaly_types?.join(", ")||"ML anomaly")}</span>${pill(a.severity)}</div><div class="alert-desc">${esc(a.explanation)} <span>• ${time(a.timestamp)}</span></div></div>`).join(""):"<div class='muted' style='padding:18px 0'>No anomalies detected.</div>";
}
function renderTable(){
  $("stationTable").innerHTML=`<table class="table"><thead><tr><th>Station</th><th>Latest</th><th>Temp</th><th>Humidity</th><th>Wind</th><th>Alerts</th><th>Severity</th></tr></thead><tbody>
  ${stations.map(s=>{let l=s.latest||{};return `<tr><td><b>${esc(s.station_id)}</b></td><td>${time(l.timestamp)}</td><td class="reading">${fmt(l.temperature)}°C</td><td class="reading">${fmt(l.humidity)}%</td><td class="reading">${fmt(l.wind_speed)} m/s</td><td>${s.anomaly_count}</td><td>${pill(l.severity)}</td></tr>`}).join("")}</tbody></table>`;
}
function renderAlertsTable(){
  const f=$("severityFilter").value;
  const list=alerts.filter(a=>!f||a.severity===f);
  $("alertsTable").innerHTML=`<table class="table"><thead><tr><th>Time</th><th>Station</th><th>Severity</th><th>Type</th><th>Explanation</th><th>ML score</th></tr></thead><tbody>
  ${list.map(a=>`<tr><td>${time(a.timestamp)}</td><td><b>${esc(a.station_id)}</b></td><td>${pill(a.severity)}</td><td>${esc(a.anomaly_types?.join(", ")||"ML anomaly")}</td><td>${esc(a.explanation)}</td><td class="reading">${fmt(a.ml_score)}</td></tr>`).join("")||"<tr><td colspan='6'>No matching alerts.</td></tr>"}</tbody></table>`;
}
function fillChartStations(){
  const sel=$("chartStation"), old=sel.value||"AWS-01";
  sel.innerHTML=stations.map(s=>`<option>${esc(s.station_id)}</option>`).join("");
  sel.value=stations.some(s=>s.station_id===old)?old:(stations[0]?.station_id||"");
}
function drawChart(){
  const canvas=$("trendChart"), box=canvas.getBoundingClientRect(), dpr=devicePixelRatio||1;
  canvas.width=box.width*dpr;canvas.height=240*dpr;const c=canvas.getContext("2d");c.scale(dpr,dpr);
  const station=$("chartStation").value; const data=records.filter(r=>r.station_id===station).sort((a,b)=>new Date(a.timestamp)-new Date(b.timestamp)).slice(-24);
  $("chartSubtitle").textContent=`${station||"—"} • last ${data.length} readings`;
  if(!data.length)return;
  const W=box.width,H=240,L=42,R=16,T=20,B=30,w=W-L-R,h=H-T-B;
  c.strokeStyle="#e8edf3";c.lineWidth=1;for(let i=0;i<5;i++){let y=T+h*i/4;c.beginPath();c.moveTo(L,y);c.lineTo(W-R,y);c.stroke()}
  const vals=data.map(x=>Number(x.temperature)).filter(Number.isFinite), min=Math.floor(Math.min(...vals)-1),max=Math.ceil(Math.max(...vals)+1);
  c.fillStyle="#8793a5";c.font="10px system-ui";for(let i=0;i<5;i++){let v=max-(max-min)*i/4;c.fillText(v.toFixed(0)+"°",5,T+h*i/4+3)}
  c.strokeStyle="#26364d";c.lineWidth=2;c.beginPath();data.forEach((r,i)=>{let x=L+w*i/(data.length-1||1),y=T+h-(r.temperature-min)/(max-min)*h;i?c.lineTo(x,y):c.moveTo(x,y)});c.stroke();
  data.forEach((r,i)=>{if(r.is_anomaly){let x=L+w*i/(data.length-1||1),y=T+h-(r.temperature-min)/(max-min)*h;c.fillStyle="#c55a52";c.beginPath();c.arc(x,y,4,0,Math.PI*2);c.fill()}});
}
function showSection(name){
  currentSection=name;document.querySelectorAll(".section").forEach(x=>x.classList.toggle("active",x.id===name));
  document.querySelectorAll(".nav-item").forEach(x=>x.classList.toggle("active",x.dataset.section===name));
  $("pageTitle").textContent={overview:"System overview",stations:"All weather stations",alerts:"Anomaly alerts"}[name];
  if(name==="alerts")renderAlertsTable();
}
async function sim(path){
  try{await get(path);toast(path.includes("start")?"Live simulator started":path.includes("stop")?"Simulator stopped":"New reading generated");await load()}catch(e){toast("Simulator action failed. Check the backend.")}}
document.querySelectorAll(".nav-item").forEach(b=>b.onclick=()=>showSection(b.dataset.section));
document.querySelectorAll("[data-jump]").forEach(b=>b.onclick=()=>showSection(b.dataset.jump));
$("refresh").onclick=load;$("chartStation").onchange=drawChart;$("severityFilter").onchange=renderAlertsTable;
$("startSim").onclick=()=>sim("/simulate/start?interval_seconds="+$("interval").value);
$("stopSim").onclick=()=>sim("/simulate/stop");
$("stepSim").onclick=()=>sim("/simulate/step");
window.onresize=()=>{if(currentSection==="overview")drawChart()};
setInterval(async()=>{try{const s=await get("/simulate/status");const el=$("simStatus");el.className="sim-status "+(s.running?"running":"");el.innerHTML=`<span class="dot"></span> Simulator ${s.running?"running":"stopped"}`}catch{}},3000);
load();