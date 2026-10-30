export const API=process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000';
export async function api(path:string,body?:unknown,method='POST'){
 const r=await fetch(API+path,{credentials:'include',...(body!==undefined?{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
 const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:data.detail?.message||'The request could not be completed.');return data;
}
export async function download(path:string,filename:string,body?:unknown){
 const r=await fetch(API+path,{credentials:'include',...(body!==undefined?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
 if(!r.ok){const data=await r.json();throw Error(typeof data.detail==='string'?data.detail:'Download unavailable.');}
 const url=URL.createObjectURL(await r.blob());const link=document.createElement('a');link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);
}
export function dateLabel(value:number|string|null|undefined){if(!value)return '—';const d=new Date(typeof value==='number'?value*1000:value);return Number.isNaN(d.getTime())?'—':d.toLocaleString();}
