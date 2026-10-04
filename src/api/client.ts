import * as mock from './mocks';
import {adaptBackendRoutes, type BackendRouteResponse} from './adapters';
import type {CriticalPoint,PhotoAnalysis,Place,Profile,RouteResponse,User} from './types';

const base=import.meta.env.VITE_API_URL||'http://localhost:8000';
const useRouteMocks=import.meta.env.VITE_USE_MOCKS!=='false';
const local=(key:string)=>{try{return JSON.parse(localStorage.getItem(key)||'[]')}catch{return[]}};
async function request<T>(path:string,init:RequestInit={}):Promise<T>{
 const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),30000);
 try{const response=await fetch(base+path,{...init,signal:controller.signal,headers:{'Content-Type':'application/json',...init.headers}});const data=await response.json().catch(()=>null);if(!response.ok)throw new Error(data?.detail||data?.error?.message||'The request could not be completed.');return data as T}
 catch(error){if(error instanceof Error&&error.name==='AbortError')throw new Error('Route search timed out. Please try again.');if(error instanceof TypeError)throw new Error('WayAble routing service could not be reached. Start the backend and try again.');throw error}
 finally{clearTimeout(timeout)}
}
const locationName=(id:string)=>{const known:Record<string,string>={dogpatch:'Dogpatch Labs, Dublin',trinity:'Trinity College Dublin',connolly:'Connolly Station, Dublin','custom-house':'Custom House, Dublin'};const place=mock.places.find(item=>item.id===id);const name=known[id]||place?.name||id;return /\b(dublin|ireland)\b/i.test(name)?name:`${name}, Dublin`};
export const api={
 login:async(email:string,_password:string)=>({token:'local-demo-token',user:{id:'local-demo-user',display_name:email.split('@')[0],email}}),
 signup:async(display_name:string,email:string,_password:string)=>({token:'local-demo-token',user:{id:'local-demo-user',display_name,email}}),
 me:async():Promise<User>=>JSON.parse(localStorage.getItem('wayable_user')||'null'),
 savedRoutes:async()=>local('wayable_saved'),
 saveRoute:async(name:string,origin_id:string,destination_id:string,profile:Profile)=>{const saved=local('wayable_saved');const item={id:`saved-${Date.now()}`,name,origin_id,destination_id,profile};saved.push(item);localStorage.setItem('wayable_saved',JSON.stringify(saved));return item},
 deleteSaved:async(id:string)=>{const saved=local('wayable_saved').filter((item:any)=>item.id!==id);localStorage.setItem('wayable_saved',JSON.stringify(saved));return{ok:true}},
 history:async()=>local('wayable_history'),
 places:async():Promise<Place[]>=>mock.getPlaces(),
 routes:async(origin:string,destination:string,profile:Profile):Promise<RouteResponse>=>useRouteMocks?mock.getRoutes(origin,destination,profile):adaptBackendRoutes(await request<BackendRouteResponse>('/api/v1/journeys',{method:'POST',body:JSON.stringify({from_location:locationName(origin),to_location:locationName(destination),user_type:profile.type,include_public_transport:true,departure_time:new Date().toISOString()})})),
 criticalPoints:():Promise<CriticalPoint[]>=>mock.getCriticalPoints(),
 analyze:(file:File,segment:string):Promise<PhotoAnalysis>=>mock.analyzePhoto(file,segment),
 report:(segment:string,barrier_type:string,text?:string)=>mock.sendReport(segment,barrier_type,text),
 get isMock(){return useRouteMocks},
 get localDemoFeatures(){return true},
};
