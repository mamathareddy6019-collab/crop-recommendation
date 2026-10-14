/* Crop Recommendation frontend – talks to the Flask API */
const $ = s => document.querySelector(s);
const FEATURES = [
  {k:'N',label:'Nitrogen',unit:'kg/ha',min:0,max:140,step:1},
  {k:'P',label:'Phosphorus',unit:'kg/ha',min:5,max:145,step:1},
  {k:'K',label:'Potassium',unit:'kg/ha',min:5,max:205,step:1},
  {k:'temperature',label:'Temperature',unit:'°C',min:8,max:44,step:0.1},
  {k:'humidity',label:'Humidity',unit:'%',min:14,max:100,step:1},
  {k:'ph',label:'Soil pH',unit:'pH',min:3.5,max:9.9,step:0.1},
  {k:'rainfall',label:'Rainfall',unit:'mm',min:20,max:300,step:1}
];
const PRESETS = {
  'Monsoon paddy':[80,48,40,24,82,6.4,230],
  'Dry winter':[40,68,80,19,17,7.3,80],
  'Hot summer':[100,17,50,28,85,6.5,50],
  'Humid tropics':[100,82,50,27,80,6.0,105]
};
const EMOJI = {Apple:'🍎',Banana:'🍌',Blackgram:'🫘',Chickpea:'🫛',Coconut:'🥥',Coffee:'☕',Cotton:'☁️',Grapes:'🍇',
  Jute:'🪢',Kidneybeans:'🫘',Lentil:'🥣',Maize:'🌽',Mango:'🥭',Mothbeans:'🌱',Mungbean:'🌱',Muskmelon:'🍈',
  Orange:'🍊',Papaya:'🥭',Pigeonpeas:'🫛',Pomegranate:'🍎',Rice:'🌾',Watermelon:'🍉'};
const vals = PRESETS['Monsoon paddy'].slice();
let photos = {};            // crop name -> image url (served from frontend/images)
let cropsData = null, signup = false, timer = null;
const pct = x => Math.round(x*100);

async function api(path, body){
  const r = await fetch('/api/'+path, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {});
  const data = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(data.error || 'Something went wrong.');
  return data;
}

/* ---------- auth ---------- */
function setMode(on){
  signup = on;
  $('#authTitle').textContent = on ? 'Create account' : 'Sign in';
  $('#go').textContent = on ? 'Create account' : 'Sign in to dashboard';
  $('#swLabel').textContent = on ? 'Have an account?' : 'New here?';
  $('#sw').textContent = on ? 'Sign in' : 'Create an account';
  $('#demo').classList.toggle('hidden', on);
  $('#err').textContent = '';
  $('#signupOnly').classList.toggle('hidden', !on);
  $('#uLabel').textContent = on ? 'Username' : 'Username, email or phone number';
  if(on){ $('#u').value=''; $('#p').value=''; $('#em').value=''; $('#ph').value=''; }
}
$('#sw').onclick = () => setMode(!signup);
$('#go').onclick = async () => {
  try{
    const body = {username:$('#u').value, password:$('#p').value};
    if(signup){ body.email = $('#em').value; body.phone = $('#ph').value; }
    const d = await api(signup ? 'register' : 'login', body);
    enter(d.user);
  }catch(e){ $('#err').textContent = e.message; }
};
['u','em','ph','p'].forEach(id => $('#'+id).addEventListener('keydown', e => { if(e.key==='Enter') $('#go').click(); }));
$('#out').onclick = async () => {
  await api('logout', {});
  $('#app').classList.add('hidden'); $('#login').classList.remove('hidden');
  setMode(false); setMode(false); $('#u').value='farmer'; $('#p').value='grow2026';
};
async function enter(user){
  cropsData = (await api('crops')).crops;
  await loadPhotos();
  $('#login').classList.add('hidden'); $('#app').classList.remove('hidden');
  $('#who').textContent = 'Signed in as ' + user;
  show('rec');
}
document.querySelectorAll('nav [data-v]').forEach(b => b.onclick = () => show(b.dataset.v));
api('me').then(d => { if(d.user) enter(d.user); }).catch(()=>{});

/* ---------- photos ---------- */
async function loadPhotos(){ try{ photos = (await api('photos')).photos; }catch(e){ photos = {}; } }

/* ---------- views ---------- */
function photo(name){
  const u = photos[name.toLowerCase()];
  return `<div class="photo" ${u ? `style="background-image:url('${u}')"` : ''}>${u ? '' : (EMOJI[name]||'🌱')}</div>`;
}
function show(v){
  document.querySelectorAll('nav [data-v]').forEach(b => b.classList.toggle('on', b.dataset.v===v));
  ({rec:viewRec, exp:viewExp, ideal:viewIdeal})[v]();
}

function viewRec(){
  $('#view').innerHTML = `
    <h2>Weather-based recommendation</h2>
    <div class="stats"><div class="card"><small>Best match</small><b id="bn">…</b></div><div class="card"><small>Match score</small><b id="bs">…</b></div></div>
    <div class="cols">
      <div class="card"><h3>Conditions</h3>
        <div class="chips">${Object.keys(PRESETS).map(p=>`<button data-p="${p}">${p}</button>`).join('')}</div>
        ${FEATURES.map((f,i)=>`<div class="row"><div class="top"><label for="n${i}" style="margin:0">${f.label}</label>
          <span class="num"><input type="number" id="n${i}" min="${f.min}" max="${f.max}" step="${f.step}"> ${f.unit}</span></div>
          <input type="range" id="r${i}" aria-label="${f.label}" min="${f.min}" max="${f.max}" step="${f.step}"></div>`).join('')}
      </div>
      <div id="cards"></div>
    </div>`;
  FEATURES.forEach((f,i)=>{
    const n=$('#n'+i), r=$('#r'+i); n.value=r.value=vals[i];
    r.oninput = () => { vals[i]=+r.value; n.value=r.value; queue(); };
    n.oninput = () => { if(n.value!==''){ vals[i]=+n.value; r.value=n.value; queue(); } };
  });
  document.querySelectorAll('[data-p]').forEach(b => b.onclick = () => {
    PRESETS[b.dataset.p].forEach((x,i)=>{ vals[i]=x; $('#n'+i).value=$('#r'+i).value=x; }); queue();
  });
  queue(0);
}
function queue(ms=150){ clearTimeout(timer); timer = setTimeout(paint, ms); }

async function paint(){
  const body = {}; FEATURES.forEach((f,i)=> body[f.k]=vals[i]);
  let results;
  try{ results = (await api('recommend', body)).results; }
  catch(e){ if($('#cards')) $('#cards').innerHTML = `<div class="card">${e.message}</div>`; return; }
  if(!$('#cards')) return;                     // user left the page
  const top = results[0];
  $('#bn').textContent = top.name; $('#bs').textContent = pct(top.score)+'%';
  $('#cards').innerHTML = results.slice(0,5).map((r,n)=>`
    <div class="card best ${n===0?'top':''}">${photo(r.name)}<div style="flex:1"><h3>${r.name}</h3><div>${pct(r.score)}% match</div>
    ${FEATURES.map(f=>`<div class="bar"><span>${f.label.replace(' pH','')}</span><span class="track"><i style="width:${pct(r.features[f.k])}%"></i></span><span>${pct(r.features[f.k])}%</span></div>`).join('')}</div></div>`).join('');
}

function viewExp(){
  $('#view').innerHTML = `<h2>Crop explorer</h2><div class="grid">${cropsData.map(c=>
    `<div class="card">${photo(c.name)}<b>${c.name}</b><br><small>${c.temperature.toFixed(1)}°C · ${Math.round(c.rainfall)} mm rain</small></div>`).join('')}</div>`;
}
function viewIdeal(){
  const fmt = (f,x) => (f.k==='temperature'||f.k==='ph') ? x.toFixed(1) : Math.round(x);
  $('#view').innerHTML = `<h2>Ideal conditions per crop</h2><div class="card tw"><table>
    <thead><tr><th>Crop</th>${FEATURES.map(f=>`<th>${f.label}</th>`).join('')}</tr></thead>
    <tbody>${cropsData.map(c=>`<tr><td>${photo(c.name)}${c.name}</td>${FEATURES.map(f=>`<td>${fmt(f,c[f.k])}</td>`).join('')}</tr>`).join('')}</tbody>
  </table></div>`;
}
