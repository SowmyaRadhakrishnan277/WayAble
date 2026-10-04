import type {CriticalPoint, Place, Route, RouteResponse, Status} from './types';

type BackendEvidence = {category:string;severity:'positive'|'caution'|'blocker'|'unknown';message:string;coordinate?:{latitude:number;longitude:number}|null;source?:string;source_url?:string|null;observed_at?:string|null;raw_tags?:Record<string,string>};
type BackendInstruction = {sequence:number;instruction:string;distance_meters:number;coordinate?:{latitude:number;longitude:number}|null};
type BackendRoute = {id:string;label:string;status:'recommended'|'caution'|'avoid';confidence_score:number;rule_based_confidence_score?:number|null;ai_review?:{state:'live'|'unavailable'|'not_configured';model?:string|null;explanation:string;risk_flags:string[];confidence_adjustment:number}|null;distance_meters:number;duration_seconds:number;geometry:{type:'LineString';coordinates:number[][]};legs:Array<{mode:'walk'|'transit';instructions:BackendInstruction[]}>;accessibility_evidence:BackendEvidence[];evidence_summary:string};
type BackendLocation = {label:string;coordinate:{latitude:number;longitude:number}};
export type BackendRouteResponse = {origin:BackendLocation;destination:BackendLocation;routes:BackendRoute[];warnings:string[];provider_status:{accessibility_data:string;public_transport:string};data_sources:Array<{id:string;name:string;state:string;source_url:string;updated_at?:string|null}>};

const statusFor=(severity:BackendEvidence['severity']):Status=>severity==='positive'?'mapped':severity==='blocker'?'barrier':severity==='caution'?'caution':'unknown';
const sourceFor=(source=''):CriticalPoint['evidence']['source']=>/gtfs|nta/i.test(source)?'gtfs':/rail/i.test(source)?'irish_rail':'osm';
const kindFor=(category:string):CriticalPoint['kind']=>{
 const c=category.toLowerCase();
 if(c.includes('tactile'))return'tactile_paving';if(c.includes('surface')||c.includes('smoothness'))return'surface';if(c.includes('barrier'))return'barrier';if(c.includes('wheelchair_access')||c.includes('accessibility'))return'route_feature';
 if(c.includes('lift'))return'lift';if(c.includes('escalator'))return'escalator';if(c.includes('ramp')||c.includes('incline'))return'ramp';if(c.includes('step'))return'steps';if(c.includes('kerb')||c.includes('curb'))return'kerb';if(c.includes('cross'))return'crossing';if(c.includes('platform'))return'platform_transfer';return'station_entrance';
};
const metersBetween=(a:BackendEvidence['coordinate'],b:BackendInstruction['coordinate'])=>{
 if(!a||!b)return Infinity;const rad=(n:number)=>n*Math.PI/180;const dLat=rad(b.latitude-a.latitude),dLon=rad(b.longitude-a.longitude);const v=Math.sin(dLat/2)**2+Math.cos(rad(a.latitude))*Math.cos(rad(b.latitude))*Math.sin(dLon/2)**2;return 6371000*2*Math.atan2(Math.sqrt(v),Math.sqrt(1-v));
};
function makePoint(e:BackendEvidence,index:number,routeId:string):CriticalPoint{return{segment_id:`${routeId}-evidence-${index+1}`,kind:kindFor(e.category),name:e.category.replaceAll('_',' ').replace(/^./,x=>x.toUpperCase()),status:statusFor(e.severity),facts:{...Object.fromEntries(Object.entries(e.raw_tags||{}).filter(([key])=>['highway','barrier','kerb','tactile_paving','wheelchair','wheelchair:description','surface','smoothness','crossing','foot','steps','incline','width','access'].includes(key.toLowerCase()))),detail:e.message},evidence:{source:sourceFor(e.source),...(e.source_url?{source_url:e.source_url}:{}),...(e.observed_at?{observed_at:e.observed_at}:{})}}}
function makeRoute(r:BackendRoute):Route{
 const evidence=r.accessibility_evidence||[];const points=evidence.map((e,i)=>makePoint(e,i,r.id));
 if(!points.length)points.push({segment_id:`${r.id}-access-unknown`,kind:'station_entrance',name:'Route access details',status:'unknown',facts:{detail:'No nearby accessibility tags were returned for this route.'},evidence:{source:'osm'}});
 const instructions=r.legs.flatMap(leg=>leg.instructions).map((step,i)=>{
  const nearby=evidence.map(e=>({e,d:metersBetween(e.coordinate,step.coordinate)})).filter(x=>x.d<=35).sort((a,b)=>a.d-b.d)[0]?.e;
  const status=nearby?statusFor(nearby.severity):'unknown';
  return{order:i+1,instruction:step.instruction,distance_m:step.distance_meters,segment_id:`${r.id}-step-${i+1}`,status,warnings:nearby&&nearby.severity!=='positive'?[nearby.message]:status==='unknown'?['No accessibility details are recorded near this step.']:[]};
 });
 if(!instructions.length)instructions.push({order:1,instruction:'Follow the mapped route to your destination.',distance_m:r.distance_meters,segment_id:`${r.id}-step-1`,status:'unknown',warnings:['No step-by-step instructions were returned.']});
 const score=r.confidence_score;const safeLabel=r.status==='avoid'?'Route with a recorded access barrier':r.status==='caution'?'Route with access details to check':r.label;
 const review=r.ai_review?{state:r.ai_review.state,model:r.ai_review.model||undefined,explanation:r.ai_review.explanation,risk_flags:r.ai_review.risk_flags||[]}:undefined;
 const reviewText=review?.state==='live'?` Optional AI review: ${review.explanation}`:'';
 return{id:r.id,label:safeLabel,modes:[...new Set(r.legs.map(leg=>leg.mode))],duration_min:Math.ceil(r.duration_seconds/60),distance_m:r.distance_meters,delta_vs_fastest_min:null,confidence:{score,level:score>=80?'high':score>=55?'medium':'low',reasons:[r.evidence_summary,...(review?.risk_flags||[])],...(review?{review}:{})},explanation:{text:r.evidence_summary+reviewText,source:'template'},geometry:r.geometry,segment_statuses:instructions.map(s=>s.status),steps:instructions,critical_points:points,suitability:r.status};
}
export function adaptBackendRoutes(data:BackendRouteResponse):RouteResponse{
 const toPlace=(loc:BackendLocation,id:string,type:Place['type']):Place=>({id,name:loc.label,lat:loc.coordinate.latitude,lon:loc.coordinate.longitude,type});
 return{routes:data.routes.map(makeRoute),notices:[...data.warnings,...(data.provider_status.accessibility_data!=='live'?['Some accessibility evidence could not be retrieved. Missing evidence remains unknown.']:[])],generated_at:new Date().toISOString(),origin:toPlace(data.origin,'backend-origin','origin'),destination:toPlace(data.destination,'backend-destination','destination')};
}
