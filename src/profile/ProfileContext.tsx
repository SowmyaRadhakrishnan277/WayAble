import {createContext,useContext,useEffect,useMemo,useState} from 'react';
import type {Profile} from '../api/types';
type Theme='system'|'light'|'dark'|'contrast';
type DisplayPreference={theme:Theme;textSize:number};
type Settings={profile:Profile;theme:Theme;textSize:number};
type ProfileContextValue={settings:Settings;update:(value:Partial<Settings>)=>void;setProfile:(type:Profile['type'])=>void};
const defaults:Settings={profile:{type:'wheelchair',chair:'manual',max_incline_pct:8,min_width_cm:90},theme:'light',textSize:100};
function readStored<T>(key:string,fallback:T):T{try{return JSON.parse(localStorage.getItem(key)||'null')??fallback}catch{return fallback}}
const C=createContext<ProfileContextValue>({settings:defaults,update:()=>{},setProfile:()=>{}});
export function ProfileProvider({children}:{children:React.ReactNode}){
 const [settings,setSettings]=useState<Settings>(()=>{const saved=readStored<Partial<Settings>>('wayable_settings',{});return{...defaults,...saved,theme:saved.theme==='system'?'light':saved.theme||defaults.theme}});
 const [wheelchairDisplay,setWheelchairDisplay]=useState<DisplayPreference|null>(()=>readStored<DisplayPreference|null>('wayable_wheelchair_display',null));
 useEffect(()=>{const root=document.documentElement;root.dataset.profile=settings.profile.type;root.dataset.theme=settings.profile.type==='low_vision'&&settings.theme==='system'?'contrast':settings.theme;root.style.setProperty('--text-scale',`${settings.textSize/100}`);localStorage.setItem('wayable_settings',JSON.stringify(settings))},[settings]);
 const update=(value:Partial<Settings>)=>setSettings(current=>({...current,...value}));
 const setProfile=(type:Profile['type'])=>{
  if(type===settings.profile.type)return;
  if(type==='low_vision'){
   const saved={theme:settings.theme,textSize:settings.textSize};
   localStorage.setItem('wayable_wheelchair_display',JSON.stringify(saved));setWheelchairDisplay(saved);
   setSettings(current=>({...current,profile:{...current.profile,type},theme:'contrast',textSize:Math.max(current.textSize,125)}));
   return;
  }
  const display=wheelchairDisplay??{theme:'system' as Theme,textSize:100};
  localStorage.removeItem('wayable_wheelchair_display');setWheelchairDisplay(null);
  setSettings(current=>({...current,profile:{...current.profile,type},theme:display.theme,textSize:display.textSize}));
 };
 const value=useMemo(()=>({settings,update,setProfile}),[settings,wheelchairDisplay]);
 return <C.Provider value={value}>{children}</C.Provider>
}
export const useProfile=()=>useContext(C);
