import { TableGeometryContext } from './tableLayout';
import { memo, useContext, useState, type CSSProperties } from 'react';
const suits: Record<string, string> = { c: '♣', d: '♦', h: '♥', s: '♠' };
export function CardBack({className='',style,target}:{className?:string;style?:CSSProperties;target?:string}) {
  return <svg data-target={target} className={className} style={style} viewBox="0 0 112 158" preserveAspectRatio="none" aria-hidden="true"><rect width="112" height="158" rx="5" fill="#dce4de"/><rect x="5" y="5" width="102" height="148" rx="3" fill="#304b48" stroke="#a3b8a9"/><path d="M56 22 96 79 56 136 16 79Z M56 36 86 79 56 122 26 79Z" fill="none" stroke="#94b4a0" strokeWidth="2"/></svg>;
}
type CardProps={hole:boolean;card?:string;hidden:boolean;unused:boolean;token:string;delay:number;duration:number;enter:boolean};
const Card=memo(function Card({hole,card,hidden,unused,token,delay,duration,enter}:CardProps){
  const [finished,setFinished]=useState('');
  const animating=!!token&&finished!==token;
  const style={'--card-delay':delay+'ms','--flip-duration':duration+'ms'} as CSSProperties;
  const label=card?`${card[0]==='T'?'10':card[0]}${suits[card[1]]}`:hidden?'未公開底牌':'尚未發牌';
  return <span data-suit={card?.[1]} aria-label={label} className={'card casino-card'+(card?'':hidden?' back':' blank')+(unused?' unused':'')+(animating?(enter?' board-deal':' hole-arrival'):'')} style={style}>
    {card?<span className="card-face" onAnimationEnd={event=>{if(event.target===event.currentTarget)setFinished(token);}}><svg className="casino-art" viewBox="0 0 112 158" preserveAspectRatio="none" aria-hidden="true"><rect width="112" height="158" rx="5" fill="#fffefb"/><text className="face-rank" x={hole?50:56} y={hole?48:65} textAnchor="middle" fontFamily="Georgia, Times New Roman, serif" fontWeight="bold" fontSize={hole?(card[0]==='T'?43:48):(card[0]==='T'?54:60)}>{card[0]==='T'?'10':card[0]}</text><text className="face-suit" x={hole?50:56} y={hole?86:133} textAnchor="middle" fontFamily="Georgia, Times New Roman, serif" fontSize={hole?50:64}>{suits[card[1]]}</text></svg></span>:hidden?<CardBack className="casino-art"/>:null}
    {animating&&card?<CardBack className="deal-back"/>:null}
  </span>;
});
export function Cards({cards,hole=false,slots=2,hidden=false,reveal,highlight,arrival}:{
  cards:string[];hole?:boolean;slots?:number;hidden?:boolean;reveal?:{id:string;count:number;from:number;duration?:number};
  highlight?:string[];arrival?:{id:string;delays:number[];duration?:number};
}) {
  const geometry=useContext(TableGeometryContext);
  return <span className="cards">{Array.from({length:slots},(_,index)=>{
    const card=cards[index], animated=!!reveal&&index>=reveal.from&&index<reveal.count;
    const duration=animated?(reveal.duration??500)*.65:arrival?.duration??180;
    const delay=animated?(index-reveal.from)*((reveal.duration??500)-duration)/Math.max(1,reveal.count-reveal.from-1):arrival?.delays[index]??0;
    return <Card hole={hole} key={geometry+':'+index+':'+(card??'back')} card={card} hidden={hidden} unused={!!(card&&highlight?.length&&!highlight.includes(card))} token={animated?reveal!.id:arrival?.id??''} delay={delay} duration={duration} enter={animated}/>;
  })}</span>;
}
