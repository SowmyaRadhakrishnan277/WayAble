export type Status='ok'|'barrier'|'unknown'|'reported'|'caution'|'mapped';
export type EvidenceSource='osm'|'gtfs'|'irish_rail'|'community_ai'|'fixture';
export interface Evidence{source:EvidenceSource;source_url?:string;observed_at?:string;stale?:boolean}
export interface Place{id:string;name:string;lat:number;lon:number;type:'origin'|'destination'|'station'|'stop'|'landmark'}
export interface Profile{type:'wheelchair'|'low_vision';chair?:'manual'|'powered';max_incline_pct?:number;min_width_cm?:number}
export type CriticalKind='lift'|'escalator'|'ramp'|'steps'|'crossing'|'kerb'|'station_entrance'|'platform_transfer'|'route_feature'|'surface'|'tactile_paving'|'barrier';
export interface CriticalPoint{segment_id:string;kind:CriticalKind;name:string;status:Status;facts:Record<string,string|number|boolean|null>;evidence:Evidence;plan_b?:{text:string;extra_min:number}}
export interface Step{order:number;instruction:string;landmark?:string;distance_m:number;segment_id:string;status:Status;warnings:string[]}
export interface Route{id:string;label:string;modes?:('walk'|'transit')[];duration_min:number;distance_m:number;delta_vs_fastest_min:number|null;confidence:{score:number;level:'high'|'medium'|'low';reasons:string[];review?:{state:'live'|'unavailable'|'not_configured';model?:string;explanation:string;risk_flags:string[]}};explanation:{text:string;source:'ai'|'template'};geometry:{type:'LineString';coordinates:number[][]};segment_statuses:Status[];steps:Step[];critical_points:CriticalPoint[];suitability?:'recommended'|'caution'|'avoid'}
export interface FastestRoute extends Route{recommended:false;fail_reasons:string[]}
export interface RouteResponse{routes:Route[];fastest?:FastestRoute;notices:string[];generated_at?:string;search_id?:string;origin?:Place;destination?:Place}
export interface User{id:string;display_name:string;email:string}
export interface PhotoAnalysis{analysis_id:string;barrier_type:string;severity:'low'|'medium'|'high';description:string;label:string}
