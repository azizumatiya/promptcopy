async function refreshState(){
  const r=await fetch(`/api/prompt/${PROMPT_ID}/state`);
  const s=await r.json();
  const like=document.getElementById("likeBtn"), save=document.getElementById("saveBtn");
  if(s.liked)like.classList.add("selected"); else like.classList.remove("selected");
  if(s.saved)save.classList.add("selected"); else save.classList.remove("selected");
}
async function action(kind){
  const data=await postJSON(`/api/prompt/${PROMPT_ID}/${kind}`);
  if(!data)return;
  if(data.ok){
    if(kind==="like"){document.getElementById("likeCount").textContent=data.likes;toast(data.liked?"Liked!":"Like removed");}
    if(kind==="save"){toast(data.saved?"Saved to My Library":"Removed from My Library");}
    refreshState();
  }
}
async function copyPrompt(){
  const text=document.getElementById("promptText").textContent;
  await navigator.clipboard.writeText(text);
  await fetch(`/api/prompt/${PROMPT_ID}/copy`,{method:"POST"});
  toast("Prompt copied!");
}
function openImagePreview(){document.getElementById("imageModal").classList.add("open")}
function closeImagePreview(){document.getElementById("imageModal").classList.remove("open")}
async function sharePrompt(){
  const data={title:document.title,url:location.href};
  if(navigator.share){try{await navigator.share(data)}catch(e){}}
  else{await navigator.clipboard.writeText(location.href);toast("Link copied!");}
}
document.addEventListener("DOMContentLoaded",()=>{
  document.getElementById("likeBtn").onclick=()=>action("like");
  document.getElementById("saveBtn").onclick=()=>action("save");
  document.getElementById("copyBtn").onclick=copyPrompt;
  document.getElementById("copyInline").onclick=copyPrompt;
  refreshState();
});
