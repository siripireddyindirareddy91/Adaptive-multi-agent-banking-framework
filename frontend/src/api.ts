export type Row = Record<string, any>;
export const API='/api/v1';
export async function api(path:string,options:RequestInit={}) {
  const token=sessionStorage.getItem('nexora_token');
  const response=await fetch(API+path,{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...(token?{Authorization:`Bearer ${token}`} : {}),...options.headers}});
  if(!response.ok){let message='Request failed';try{const error=await response.json();message=typeof error.detail==='string'?error.detail:JSON.stringify(error.detail)}catch{message=await response.text().catch(()=>message)}if(response.status===401&&path!='/auth/login'){sessionStorage.clear();window.location.reload()}throw new Error(message)}
  return response.json();
}
export async function download(resource:string){const r=await fetch(API+'/export/'+resource,{headers:{Authorization:`Bearer ${sessionStorage.getItem('nexora_token')}`}});if(!r.ok)throw new Error('Export failed');const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download=`nexora-${resource}.csv`;a.click();URL.revokeObjectURL(url)}
export function money(value:number){return new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0,notation:value>10000000?'compact':'standard'}).format(value)}
