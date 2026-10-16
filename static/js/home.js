let state={q:"",model:"All",category:"All",type:"All",sort:"newest"};
let prompts=[];
let trend=[];
let trendIndex=0;
let trendTimer=null;

async function loadPrompts(){
  const params=new URLSearchParams(state);
  const r=await fetch("/api/prompts?"+params.toString());
  prompts=await r.json();
  renderGallery();
}
function card(p){
  const badges=(p.is_new?'<span class="card-badge new">NEW</span>':'')+(p.hot?'<span class="card-badge hot">HOT</span>':'');
  return `<article class="prompt-card">
    <a href="/prompt/${p.id}" class="card-image"><img src="${p.image}" alt="${escapeHtml(p.title)}" loading="lazy">${badges}<span class="model-chip">${escapeHtml(p.model)}</span></a>
    <div class="card-body"><div class="card-meta"><span>${escapeHtml(p.category)}</span><span>${p.prompt_type}</span></div>
    <a href="/prompt/${p.id}"><h3>${escapeHtml(p.title)}</h3></a>
    <p>${escapeHtml(p.description||"")}</p>
    <div class="card-foot"><span>❤️ ${formatNumber(p.likes)}</span><span>🔖 ${formatNumber(p.saves)}</span><span>📋 ${formatNumber(p.copies)}</span><button onclick="event.preventDefault();copyFromCard(${p.id},this)" title="Copy prompt"><i data-lucide="copy"></i></button></div>
    </div></article>`;
}
function renderGallery(){
  const g=document.getElementById("gallery"); if(!g)return;
  document.getElementById("resultCount").textContent=prompts.length;
  g.innerHTML=prompts.length?prompts.map(card).join(""):`<div class="empty-wide">No prompts match your filters.</div>`;
  lucide.createIcons();
}
async function copyFromCard(id,btn){
  const p=prompts.find(x=>x.id===id);
  if(!p)return;
  await navigator.clipboard.writeText(p.prompt);
  await fetch(`/api/prompt/${id}/copy`,{method:"POST"});
  toast("Prompt copied!");
  btn.classList.add("copied"); setTimeout(()=>btn.classList.remove("copied"),700);
}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));}

async function loadTrending(){
  const r=await fetch("/api/trending"); trend=await r.json();
  if(!trend.length)return;
  document.getElementById("trendTotal").textContent=String(Math.min(trend.length,10)).padStart(2,"0");
  renderTrend();
  clearInterval(trendTimer);
  trendTimer=setInterval(()=>{trendIndex=(trendIndex+1)%Math.min(trend.length,10);renderTrend()},4500);
}
function renderTrend(){
  const p=trend[trendIndex];
  document.getElementById("trendNumber").textContent=String(trendIndex+1).padStart(2,"0");
  document.getElementById("trendHero").innerHTML=`<a href="/prompt/${p.id}" class="trend-main"><img src="${p.image}" alt=""><div class="trend-overlay"><span>#${trendIndex+1} TRENDING</span><h3>${escapeHtml(p.title)}</h3><p>${escapeHtml(p.description||"")}</p><div><b>❤️ ${formatNumber(p.likes)}</b><b>📋 ${formatNumber(p.copies)}</b><b>👁 ${formatNumber(p.views)}</b></div></div></a>`;
  document.getElementById("trendRail").innerHTML=trend.slice(0,10).map((x,i)=>`<button class="${i===trendIndex?'active':''}" onclick="trendIndex=${i};renderTrend();resetTrendTimer()"><img src="${x.image}" alt=""><span>#${i+1}</span></button>`).join("");
}
function resetTrendTimer(){clearInterval(trendTimer);trendTimer=setInterval(()=>{trendIndex=(trendIndex+1)%Math.min(trend.length,10);renderTrend()},4500);}
document.addEventListener("DOMContentLoaded",()=>{
  document.querySelectorAll(".filter").forEach(btn=>btn.addEventListener("click",()=>{
    const type=btn.dataset;
    if(type.model!==undefined){state.model=type.model;document.querySelectorAll("[data-model]").forEach(x=>x.classList.toggle("active",x===btn));}
    if(type.category!==undefined){state.category=type.category;document.querySelectorAll("[data-category]").forEach(x=>x.classList.toggle("active",x===btn));}
    if(type.type!==undefined){state.type=type.type;document.querySelectorAll("[data-type]").forEach(x=>x.classList.toggle("active",x===btn));}
    loadPrompts();
  }));
  document.querySelectorAll(".category-tile").forEach(btn=>btn.addEventListener("click",()=>{state.category=btn.dataset.category;document.querySelectorAll("[data-category]").forEach(x=>x.classList.toggle("active",x.dataset.category===state.category));document.getElementById("explore").scrollIntoView({behavior:"smooth"});loadPrompts();}));
  document.querySelectorAll("[data-search]").forEach(btn=>btn.addEventListener("click",()=>{document.getElementById("searchInput").value=btn.dataset.search;state.q=btn.dataset.search;loadPrompts();document.getElementById("explore").scrollIntoView({behavior:"smooth"});}));
  document.getElementById("searchForm").addEventListener("submit",e=>{e.preventDefault();state.q=document.getElementById("searchInput").value.trim();loadPrompts();document.getElementById("explore").scrollIntoView({behavior:"smooth"});});
  document.getElementById("sortSelect").addEventListener("change",e=>{state.sort=e.target.value;loadPrompts();});
  document.getElementById("trendPrev").addEventListener("click",()=>{trendIndex=(trendIndex-1+trend.length)%Math.min(trend.length,10);renderTrend();resetTrendTimer();});
  document.getElementById("trendNext").addEventListener("click",()=>{trendIndex=(trendIndex+1)%Math.min(trend.length,10);renderTrend();resetTrendTimer();});
  loadPrompts();loadTrending();
});
