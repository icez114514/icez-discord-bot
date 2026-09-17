import { createContext, useEffect, useState } from 'react';
export const portraitQuery='(max-width: 899px) and (orientation: portrait)';
export const tableSizes={landscape:{width:1520,height:990},portrait:{width:390,height:840}};
export function usePortraitTable(){
  const [portrait,setPortrait]=useState(()=>matchMedia(portraitQuery).matches);
  useEffect(()=>{const media=matchMedia(portraitQuery);const change=()=>setPortrait(media.matches);media.addEventListener('change',change);return()=>media.removeEventListener('change',change);},[]);
  return portrait;
}

export const TableGeometryContext=createContext('');

export function useCompactTableActions(){
  const query='(max-height: 639px)';
  const [compact,setCompact]=useState(()=>matchMedia(query).matches);
  useEffect(()=>{const media=matchMedia(query);const change=()=>setCompact(media.matches);media.addEventListener('change',change);return()=>media.removeEventListener('change',change);},[]);
  return compact;
}