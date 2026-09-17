import { createContext, useEffect, useState } from 'react';
export const portraitQuery='(max-width: 899px) and (orientation: portrait)';
export const tableSizes={landscape:{width:1520,height:1024},portrait:{width:390,height:620}};
export function usePortraitTable(){
  const [portrait,setPortrait]=useState(()=>matchMedia(portraitQuery).matches);
  useEffect(()=>{const media=matchMedia(portraitQuery);const change=()=>setPortrait(media.matches);media.addEventListener('change',change);return()=>media.removeEventListener('change',change);},[]);
  return portrait;
}

export const TableGeometryContext=createContext('');
