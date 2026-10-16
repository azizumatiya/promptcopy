function toast(message){
  const el=document.getElementById("toast");
  if(!el)return;
  el.textContent=message;
  el.classList.add("show");
  clearTimeout(window.__toast);
  window.__toast=setTimeout(()=>el.classList.remove("show"),2400);
}
async function postJSON(url){
  const r=await fetch(url,{method:"POST",headers:{"X-Requested-With":"XMLHttpRequest"}});
  let data={}; try{data=await r.json();}catch(e){}
  if(r.status===401 && data.redirect){window.location.href=data.redirect;return null;}
  return data;
}
function formatNumber(n){
  n=Number(n||0);
  if(n>=1000000)return (n/1000000).toFixed(1).replace(".0","")+"M";
  if(n>=1000)return (n/1000).toFixed(1).replace(".0","")+"K";
  return String(n);
}
