import {useEffect,useRef} from 'react';
import maplibregl,{Map as MapLibreMap} from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type {Place,Route} from '../api/types';

const fallbackStart:Place={id:'dogpatch',name:'Dogpatch Labs · CHQ',lat:53.3488,lon:-6.2434,type:'origin'};
const fallbackEnd:Place={id:'trinity',name:'Trinity College Dublin',lat:53.3438,lon:-6.2546,type:'destination'};
type Props={route?:Route;start?:Place;end?:Place;className?:string;showControls?:boolean;overview?:boolean};
export default function DublinMap({route,start=fallbackStart,end=fallbackEnd,className='',showControls=true,overview=false}:Props){
 const container=useRef<HTMLDivElement>(null);const map=useRef<MapLibreMap|null>(null);
 useEffect(()=>{
  if(!container.current)return;
  const coordinates=route?.geometry?.coordinates as [number,number][]|undefined;
  const center:[number,number]=overview?[-6.28,53.35]:[(start.lon+end.lon)/2,(start.lat+end.lat)/2];const initialZoom=overview?12.2:14;
  const m=new maplibregl.Map({container:container.current,center,zoom:initialZoom,attributionControl:false,keyboard:true,style:{version:8,sources:{osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap contributors'}},layers:[{id:'osm',type:'raster',source:'osm'}]}});
  map.current=m;const resizeMap=()=>m.resize();window.addEventListener('resize',resizeMap);const observer=new ResizeObserver(resizeMap);observer.observe(container.current);
  m.on('load',()=>{
   m.resize();
   new maplibregl.Marker({color:'#0e5a63'}).setLngLat([start.lon,start.lat]).setPopup(new maplibregl.Popup({offset:18}).setText(`Start: ${start.name}`)).addTo(m);
   new maplibregl.Marker({color:'#b07800'}).setLngLat([end.lon,end.lat]).setPopup(new maplibregl.Popup({offset:18}).setText(`Destination: ${end.name}`)).addTo(m);
   if(coordinates&&coordinates.length>1){m.addSource('journey-route',{type:'geojson',data:{type:'Feature',properties:{},geometry:route!.geometry}});m.addLayer({id:'journey-route',type:'line',source:'journey-route',layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#0e5a63','line-width':6,'line-opacity':.92}});const bounds=coordinates.reduce((box,coord)=>box.extend(coord),new maplibregl.LngLatBounds(coordinates[0],coordinates[0]));m.fitBounds(bounds,{padding:56,duration:0})}else{m.jumpTo({center,zoom:initialZoom})}
  });
  return()=>{window.removeEventListener('resize',resizeMap);observer.disconnect();m.remove();map.current=null};
 },[route,start,end,overview]);
 return <div className={`dublin-map ${className}`}>
  <div ref={container} className="map-canvas" role="region" aria-label={route?'OpenStreetMap view of the selected journey. Full directions are in the text steps.':'Interactive OpenStreetMap of Dublin. No route is drawn until you search.'}/>
  {showControls&&<div className="map-overlay-controls" aria-label="Map controls"><button type="button" aria-label="Zoom in on map" onClick={()=>map.current?.zoomIn()}>+</button><button type="button" aria-label="Zoom out on map" onClick={()=>map.current?.zoomOut()}>−</button><button type="button" onClick={()=>map.current?.easeTo({center:[start.lon,start.lat],zoom:14})}>Reset</button></div>}
  <div className="map-attribution">© OpenStreetMap contributors <span>·</span> {route?'Route preview':'Dublin map preview'}</div>
 </div>
}
