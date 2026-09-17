import { casinoCard } from './casinoCard';
import { TableGeometryContext } from './tableLayout';
import { memo, useContext, useState, type CSSProperties } from 'react';
import { cardLabel } from './wildcards';
export function CardBack({className='',style,target}:{className?:string;style?:CSSProperties;target?:string}) {
  return <img data-target={target} className={className} style={style} src="/assets/cards/casino/back.png" alt="" aria-hidden="true" draggable={false}/>;
}
type CardProps={card?:string;hidden:boolean;unused:boolean;token:string;delay:number;duration:number;enter:boolean};
const Card=memo(function Card({card,hidden,unused,token,delay,duration,enter}:CardProps){
  const [finished,setFinished]=useState('');
  const animating=!!token&&finished!==token;
  const style={'--card-delay':delay+'ms','--flip-duration':duration+'ms'} as CSSProperties;
  const label=card?cardLabel(card):hidden?'未公開底牌':'尚未發牌';
  return <span data-suit={card?.[1]} aria-label={label} className={'card casino-card'+(card?'':hidden?' back':' blank')+(unused?' unused':'')+(animating?(enter?' board-deal':' hole-arrival'):'')} style={style}>
    {card?<span className="card-face" onAnimationEnd={event=>{if(event.target===event.currentTarget)setFinished(token);}}><img className="casino-art" src={casinoCard(card)} alt="" aria-hidden="true" draggable={false}/></span>:hidden?<CardBack className="casino-art"/>:null}
    {animating&&card?<CardBack className="deal-back"/>:null}
  </span>;
});
export function Cards({cards,slots=2,hidden=false,reveal,highlight,arrival}:{
  cards:string[];slots?:number;hidden?:boolean;reveal?:{id:string;count:number;from:number;duration?:number};
  highlight?:string[];arrival?:{id:string;delays:number[];duration?:number};
}) {
  const geometry=useContext(TableGeometryContext);
  return <span className="cards">{Array.from({length:slots},(_,index)=>{
    const card=cards[index], animated=!!reveal&&index>=reveal.from&&index<reveal.count;
    const duration=animated?(reveal.duration??500)*.65:arrival?.duration??180;
    const delay=animated?(index-reveal.from)*((reveal.duration??500)-duration)/Math.max(1,reveal.count-reveal.from-1):arrival?.delays[index]??0;
    return <Card key={geometry+':'+index+':'+(card??'back')} card={card} hidden={hidden} unused={!!(card&&highlight?.length&&!highlight.includes(card))} token={animated?reveal!.id:arrival?.id??''} delay={delay} duration={duration} enter={animated}/>;
  })}</span>;
}
