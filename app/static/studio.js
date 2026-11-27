/* Live studio: allowlisted visual scenes, browser-native speech, bounded dialogue. */
(()=>{'use strict';
const by=id=>document.getElementById(id);
const ui={steps:[],index:0,playing:false,timer:null,epoch:0,history:[],busy:false,recognition:null,request:null,turn:0,audioRequest:null};
const fr=()=>state.language==='fr';
const say=(a,b)=>fr()?a:b;
const svg=by('studio-svg');
const NS='http://www.w3.org/2000/svg';
function shape(name,attrs={},text){const x=document.createElementNS(NS,name);Object.entries(attrs).forEach(([k,v])=>x.setAttribute(k,String(v)));if(text!==undefined)x.textContent=text;svg.appendChild(x);return x;}
function line(x1,y1,x2,y2,color='#73819b',width=2,dash=''){return shape('line',{x1,y1,x2,y2,stroke:color,'stroke-width':width,'stroke-dasharray':dash,'stroke-linecap':'round'});}
function text(x,y,content,color='#24314b',size=15){return shape('text',{x,y,fill:color,'font-size':size,'font-weight':600,'text-anchor':'middle'},content);}
function arrow(x,y1,y2,color,label){line(x,y1,x,y2,color,3);const d=y2>y1?1:-1;shape('path',{d:'M '+(x-6)+' '+(y2-d*9)+' L '+x+' '+y2+' L '+(x+6)+' '+(y2-d*9),fill:'none',stroke:color,'stroke-width':3});if(label)text(x,y1+(d===1?-9:19),label,color,13);}
function draw(scene='load'){
 svg.replaceChildren();if(scene==='unavailable'){text(300,135,say('Leçon générative indisponible','Generated lesson unavailable'),'#24314b',21);text(300,175,say('Réessaie ou utilise le guide RDM2','Retry or use the RDM2 guide'),'#687995',15);return;}const left=70,right=530,y=184,mid=300,p=185;
 text(300,28,say('EXEMPLE ILLUSTRATIF · RDM2','ILLUSTRATIVE EXAMPLE · RDM2'),'#687995',12);
 line(left,y,right,y,'#253955',10);
 for(const x of [left,right]){shape('path',{d:'M '+x+' '+(y+7)+' l -17 25 h 34 z',fill:'#d2daeb',stroke:'#71829e'});line(x-22,y+35,x+22,y+35);}
 text(left,y+58,'A');text(right,y+58,'B');
 line(left,275,right,275,'#a1adc1',1);line(left,269,left,281);line(right,269,right,281);text(mid,297,'L = 8 m');
 if(scene==='distributed'||scene==='balance'||scene==='moment'){
   for(let x=85;x<=515;x+=43)arrow(x,78,148,'#8096bd','');
   line(85,78,515,78,'#8096bd',2);text(mid,64,'q = 2 kN/m','#526f9f',13);
 }
 if(scene==='distributed'){
   const a=shape('g',{class:'studio-enter'});const l=arrow(mid,105,179,'#6358dc','');text(mid,98,'Q = q × L','#6358dc',16);
   line(mid,185,mid,265,'#6358dc',1,'4 5');
 }else{
   arrow(p,104,177,'#e16c50','P = 12 kN');
 }
 if(scene==='load'||scene==='moment'||scene==='compare'){
   line(left,252,p,252,'#6358dc',3);line(left,245,left,259,'#6358dc');line(p,245,p,259,'#6358dc');text((left+p)/2,244,'a','#6358dc',16);
 }
 if(scene==='moment'){shape('circle',{cx:left,cy:y,r:17,fill:'none',stroke:'#6358dc','stroke-width':4,class:'studio-pulse'});text(130,145,say('Pivot A','Pivot A'),'#6358dc',13);}
 if(scene==='balance'){arrow(left,171,108,'#16866f','');arrow(right,171,108,'#16866f','');text(left,100,'RA','#16866f');text(right,100,'RB','#16866f');}
 if(scene==='compare'){const g=shape('g',{});const a=shape('path',{d:'M 185 115 V 176 M 179 165 L 185 176 L 191 165',stroke:'#6358dc','stroke-width':3,fill:'none',opacity:.8});const anim=document.createElementNS(NS,'animateTransform');anim.setAttribute('attributeName','transform');anim.setAttribute('type','translate');anim.setAttribute('values','0 0;230 0;0 0');anim.setAttribute('dur','5s');anim.setAttribute('repeatCount','indefinite');if(!matchMedia('(prefers-reduced-motion: reduce)').matches)a.appendChild(anim);line(p,91,415,91,'#6358dc',2,'6 5');text(mid,79,say('Même force, position différente','Same force, different position'),'#6358dc',13);}
 if(scene==='check')text(mid,113,say('Quelle équation choisir ?','Which equation would you choose?'),'#6358dc',19);
}
const palette={ink:'#24314b',blue:'#4775c9',purple:'#6358dc',green:'#16866f',orange:'#e16c50',muted:'#8194ad',red:'#c33b50',cyan:'#15a7bd',gold:'#d4a12d',pink:'#cc5897'};
let boardTimers=[],boardReveals=[],voiceAudio=null,voiceUrl=null;
const narrationCache=new Map();
function releaseAudio(){if(voiceAudio){voiceAudio.pause();voiceAudio.removeAttribute('src');voiceAudio=null;}if(voiceUrl){URL.revokeObjectURL(voiceUrl);voiceUrl=null;}}
function progressBoard(p){for(const item of boardReveals){if(!item.done&&p>=item.at){item.done=true;item.reveal();}}}
function finishBoard(){progressBoard(1);}
function timedBoard(duration){clearBoardTimers();const start=performance.now();const tick=()=>{const p=Math.min(1,(performance.now()-start)/duration);progressBoard(p);if(p<1)boardTimers.push(setTimeout(tick,60));};tick();}
function clearBoardTimers(){boardTimers.forEach(clearTimeout);boardTimers=[];}
// Place each label using measured SVG font bounds, not character estimates alone.
function arrangeLabels(labels){
 const occupied=[];
 const intersects=(a,b)=>a.x<b.x+b.width+5&&a.x+a.width+5>b.x&&a.y<b.y+b.height+5&&a.y+a.height+5>b.y;
 for(const {node,group,object} of labels){
  const base=node.getBBox();
  const moves=[[0,0]];
  for(const r of [12,24,38,54,72,96,120])for(const [dx,dy] of [[0,-r],[0,r],[-r,0],[r,0],[-r,-r],[r,-r],[-r,r],[r,r]])moves.push([dx,dy]);
  const options=moves.map(([dx,dy])=>{
   const x=Math.max(8,Math.min(592-base.width,base.x+dx)),y=Math.max(8,Math.min(322-base.height,base.y+dy));
   const box={x,y,width:base.width,height:base.height};
   return {box,dx:x-base.x,dy:y-base.y,cost:(x-base.x)**2+(y-base.y)**2};
  }).sort((a,b)=>a.cost-b.cost);
  const selected=options.find(c=>!occupied.some(b=>intersects(c.box,b)))||options[0];
  node.setAttribute('transform','translate('+selected.dx+' '+selected.dy+')');
  node.setAttribute('paint-order','stroke fill');
  node.setAttribute('stroke','#f8faff');node.setAttribute('stroke-width','3');node.setAttribute('stroke-linejoin','round');
  group.dataset.labelCollision=String(occupied.some(b=>intersects(selected.box,b)));
  occupied.push(selected.box);
 }
}
function drawGenerated(step,animate=false){
 clearBoardTimers();boardReveals=[];svg.replaceChildren();
 const duration=Math.max(3500,step.narration.length*55);
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const labels=[];
 for(const o of step.objects){
  const color=palette[o.color]||palette.ink;
  const g=shape('g',{'data-generated':o.kind});let n;
  const attrs={stroke:color,'stroke-width':o.width||3,'stroke-linecap':'round','stroke-linejoin':'round',fill:o.fill?color:'none','fill-opacity':o.fill||0};
  function child(tag,a,txt){const e=document.createElementNS(NS,tag);Object.entries(a).forEach(([k,v])=>e.setAttribute(k,String(v)));if(txt!==undefined)e.textContent=txt;g.appendChild(e);return e;}
  if(o.kind==='line'||o.kind==='arrow'){n=child('line',{...attrs,x1:o.x,y1:o.y,x2:o.x2,y2:o.y2});if(o.kind==='arrow'){const a=Math.atan2(o.y2-o.y,o.x2-o.x);child('polyline',{...attrs,points:[[o.x2-10*Math.cos(a-.5),o.y2-10*Math.sin(a-.5)],[o.x2,o.y2],[o.x2-10*Math.cos(a+.5),o.y2-10*Math.sin(a+.5)]].map(p=>p.join(',')).join(' ')});}}
  else if(o.kind==='rect')n=child('rect',{...attrs,x:o.x,y:o.y,width:o.w,height:o.h,rx:4});
  else if(o.kind==='circle')n=child('circle',{...attrs,cx:o.x,cy:o.y,r:o.r});
  else if(o.kind==='ellipse')n=child('ellipse',{...attrs,cx:o.x,cy:o.y,rx:o.rx,ry:o.ry});
  else if(o.kind==='polyline'||o.kind==='polygon')n=child(o.kind,{...attrs,points:o.points.map(p=>p.join(',')).join(' ')});
  else if(o.kind==='curve'){let d='M '+o.points[0].join(' ');for(let i=1;i<o.points.length-1;i++){const a=o.points[i],b=o.points[i+1];d+=' Q '+a.join(' ')+' '+((a[0]+b[0])/2)+' '+((a[1]+b[1])/2);}d+=' L '+o.points[o.points.length-1].join(' ');n=child('path',{...attrs,d});}
  else if(o.kind==='text'){const font=o.size||18,maxChars=Math.max(10,Math.floor(340/(font*.58)));const words=o.text.split(/\s+/);const rows=[];let row='';for(const word of words){if(row&&(row+' '+word).length>maxChars){rows.push(row);row=word;}else row+=(row?' ':'')+word;}if(row)rows.push(row);const w=Math.min(565,Math.max(...rows.map(r=>r.length))*font*.58);const x=Math.max(15+w/2,Math.min(585-w/2,o.x));const y=Math.max(font+5,Math.min(315-(rows.length-1)*font*1.15,o.y));n=child('text',{x,y,fill:color,'font-size':font,'font-weight':600,'text-anchor':'middle'});rows.forEach((r,i)=>{const t=document.createElementNS(NS,'tspan');t.setAttribute('x',String(x));t.setAttribute('dy',i?String(font*1.15):'0');t.textContent=r;n.appendChild(t);});}
  if(o.kind==='text')labels.push({node:n,group:g,object:o});
  const reveal=()=>{g.style.opacity='1';svg.dispatchEvent(new CustomEvent('studio:reveal',{detail:{at:o.at,audioTime:voiceAudio?.currentTime??null,kind:o.kind}}));if(reduced||!animate)return;
   if(o.motion==='draw'&&n&&typeof n.getTotalLength==='function'){const len=n.getTotalLength();if(len>0){n.animate([{strokeDasharray:String(len),strokeDashoffset:len},{strokeDasharray:String(len),strokeDashoffset:0}],{duration:(o.duration||1)*1000,fill:'forwards'});}}
   else if(o.motion==='move')g.animate([{transform:'translate(0px,0px)'},{transform:'translate('+o.dx+'px,'+o.dy+'px)'}],{duration:(o.duration||1.8)*1000,fill:'forwards',easing:'ease-in-out'});
   else if(o.motion==='grow'||o.motion==='rotate'){g.style.transformBox='fill-box';g.style.transformOrigin='center';const from=o.motion==='grow'?'scale(.05)':'rotate(0deg)';const to=o.motion==='grow'?'scale(1)':'rotate('+o.angle+'deg)';g.animate([{transform:from},{transform:to}],{duration:(o.duration||1)*1000,fill:'forwards',easing:'ease-out'});}
   else if(o.motion==='pulse')g.animate([{opacity:1},{opacity:.3},{opacity:1}],{duration:1000,iterations:3});
   else if(o.motion==='fade'||o.motion==='draw')g.animate([{opacity:0},{opacity:1}],{duration:550});
  };
  if(animate&&!reduced){g.style.opacity='0';boardReveals.push({at:o.at,done:false,reveal});}else reveal();
 }
 arrangeLabels(labels);
 if(!animate)progressBoard(0);
}

function add(role,content){const node=document.createElement('div');node.className='studio-message '+role;node.textContent=content;by('studio-chatlog').appendChild(node);by('studio-chatlog').scrollTop=by('studio-chatlog').scrollHeight;}
function stop(){if(ui.audioRequest){ui.audioRequest.abort();ui.audioRequest=null;}svg.dataset.audio='stopped';releaseAudio();clearBoardTimers();svg.getAnimations({subtree:true}).forEach(a=>a.cancel());ui.epoch++;ui.playing=false;clearTimeout(ui.timer);if('speechSynthesis'in window)window.speechSynthesis.cancel();by('studio-play').textContent='▶ Play';}
function prettyFormula(value){
 let s=String(value||'—').replace(/\\(?:text|mathrm|mathbf)\{([^{}]*)\}/g,'$1');
 for(let i=0;i<6;i++){const next=s.replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g,(_,a,b)=>'('+a+') / ('+b+')');if(next===s)break;s=next;}
 return s.replace(/\\(?:cdot|times)\b/g,' × ').replace(/\\div\b/g,' ÷ ').replace(/\\sqrt\{([^{}]*)\}/g,'√($1)').replace(/\\(?:left|right)\b/g,'').replace(/\^\{?2\}?/g,'²').replace(/\^\{?3\}?/g,'³').replace(/\\,/g,' ').replace(/\\(?:[()[\]])/g,'').replace(/\$/g,'').replace(/\s+/g,' ').trim();
}
function render(){const s=ui.steps[ui.index];if(!s)return;svg.setAttribute('role','img');svg.setAttribute('aria-label',s.title+'. '+s.narration);if(s.scene==='generated')drawGenerated(s,ui.playing);else draw(s.scene);by('studio-title').textContent=s.title;by('studio-formula').textContent=prettyFormula(s.formula);by('studio-caption').textContent=s.narration;by('studio-count').textContent=(ui.index+1)+' / '+ui.steps.length;by('studio-prev').disabled=ui.index===0;by('studio-next').disabled=ui.index===ui.steps.length-1;by('studio-play').disabled=false;by('studio-steps').replaceChildren(...ui.steps.map((x,i)=>{const b=document.createElement('button');b.type='button';b.className=i===ui.index?'active':'';b.setAttribute('aria-label',x.title);b.setAttribute('aria-current',i===ui.index?'step':'false');b.onclick=()=>{stop();ui.index=i;render();};return b;}));}
function play(){
 if(!ui.steps.length)return;
 stop();ui.playing=true;const epoch=ui.epoch;by('studio-play').textContent='■ Stop';
 function active(){return epoch===ui.epoch&&ui.playing;}
 function advance(){if(!active())return;svg.dataset.audio='ended';clearTimeout(ui.timer);clearBoardTimers();finishBoard();const remaining=Math.max(0,...svg.getAnimations({subtree:true}).map(a=>Math.max(0,(a.effect?.getComputedTiming().endTime||0)-(a.currentTime||0))).filter(Number.isFinite));ui.timer=setTimeout(()=>{if(!active())return;if(ui.index+1>=ui.steps.length){ui.playing=false;by('studio-play').textContent='▶ Play';return;}ui.index++;run();},Math.max(1200,Math.min(4000,remaining+200)));}
 async function run(){if(!active())return;releaseAudio();render();const s=ui.steps[ui.index],duration=Math.max(3500,s.narration.length*55);
  if(by('studio-voice').checked){try{const payload={text:s.narration,lang:ui.lessonLang||state.language,cloud:by('studio-voice-engine').value==='cloud'&&by('studio-consent').checked,consent_external:by('studio-consent').checked,cues:[...new Set((s.objects||[]).map(o=>o.at))].sort((a,b)=>a-b)};
const key=JSON.stringify(payload);let saved=narrationCache.get(key);
if(!saved){const controller=new AbortController();ui.audioRequest=controller;const res=await api('/api/studio/audio',{method:'POST',signal:controller.signal,body:JSON.stringify(payload)});if(ui.audioRequest===controller)ui.audioRequest=null;if(!active())return;const backend=res.headers.get('X-Studio-Voice')||'unknown',marks=JSON.parse(res.headers.get('X-Studio-Cues')||'[]'),blob=await res.blob();if(!active())return;saved={backend,marks,blob};if(!payload.cloud||backend==='gemini-neural'||backend==='openrouter-heygen-neural'){if(narrationCache.size>=10)narrationCache.delete(narrationCache.keys().next().value);narrationCache.set(key,saved);}}
if(!active())return;
const {backend,marks,blob}=saved;svg.dataset.voiceBackend=backend;by('studio-voice-status').textContent=backend==='gemini-neural'?'Gemini · cloud':backend==='openrouter-heygen-neural'?'HeyGen · OpenRouter':backend==='piper-neural'?(payload.cloud?say('Piper · secours local','Piper · local fallback'):'Piper · local'):backend;voiceUrl=URL.createObjectURL(blob);const audio=new Audio(voiceUrl);voiceAudio=audio;audio.onplaying=()=>{if(active()){svg.dataset.audio='playing';progressBoard(0);}};audio.ontimeupdate=()=>{if(active()&&Number.isFinite(audio.duration)&&audio.duration>0)progressBoard(marks.length?Math.max(0,...marks.filter(m=>m.time<=audio.currentTime+.04).map(m=>m.at)):audio.currentTime/audio.duration);};audio.onended=()=>{if(active())advance();};audio.onerror=()=>{if(active()){releaseAudio();timedBoard(duration);ui.timer=setTimeout(advance,duration);}};await audio.play();if(!active())return;svg.dataset.audio='playing';svg.dataset.cueCount=String(marks.length);progressBoard(0);return;}catch{if(!active())return;releaseAudio();}}

  if(by('studio-voice').checked&&'speechSynthesis'in window&&'SpeechSynthesisUtterance'in window){
   const u=new SpeechSynthesisUtterance(s.narration);u.lang=(ui.lessonLang||state.language)==='fr'?'fr-FR':'en-US';u.rate=.95;
   svg.dataset.voiceBackend='browser';by('studio-voice-status').textContent=say('Voix du navigateur','Browser voice');let boundary=false,started=false;
   u.onstart=()=>{if(!active())return;started=true;progressBoard(0);ui.timer=setTimeout(()=>{if(active()&&!boundary)timedBoard(duration);},900);};
   u.onboundary=e=>{if(!active())return;if(!boundary){boundary=true;clearBoardTimers();clearTimeout(ui.timer);}progressBoard(e.charIndex/Math.max(1,s.narration.length));};
   u.onend=advance;
   u.onerror=()=>{if(active()){clearTimeout(ui.timer);timedBoard(duration);ui.timer=setTimeout(advance,duration);}};
   window.speechSynthesis.speak(u);
   if(!started)ui.timer=setTimeout(()=>{if(active()&&!started){window.speechSynthesis.cancel();timedBoard(duration);ui.timer=setTimeout(advance,duration);}},2500);
  }else{timedBoard(duration);ui.timer=setTimeout(advance,duration);}
 }run();
}
function interrupt(){stop();ui.turn++;if(ui.request)ui.request.abort();ui.request=null;ui.busy=false;by('studio-send').disabled=false;by('studio-status').textContent=say('Interrompu. Pose ta prochaine question.','Interrupted. Ask your next question.');}
async function submit(e){e.preventDefault();const q=by('studio-question').value.trim();if(q.length<3)return;if(ui.busy)interrupt();stop();const turn=++ui.turn;const controller=new AbortController();ui.request=controller;narrationCache.clear();ui.busy=true;by('studio-send').disabled=true;by('studio-status').textContent=say('Préparation de la leçon…','Preparing your lesson…');add('student',q);by('studio-question').value='';try{const result=await api('/api/studio',{method:'POST',signal:controller.signal,body:JSON.stringify({question:q,challenge_id:state.challenge?.id||null,lang:state.language,history:ui.history.slice(-8),consent_external:by('studio-consent').checked,generative:by('studio-generative').checked})});if(turn!==ui.turn)return;ui.steps=result.steps;ui.index=0;ui.lessonLang=state.language;const answer=result.steps.map(x=>x.narration).join('\n\n');add('tutor',answer);ui.history.push({role:'student',text:q},{role:'tutor',text:answer.slice(0,1600)});ui.history=ui.history.slice(-8);by('studio-mode').textContent=result.visual_mode==='generated'?'AI · GENERATED':result.mode==='live_ai'?'AI · LIVE':say('Guide local','Local guide');by('studio-status').textContent=result.notice+(result.numerical_checks?.length?say(' · '+result.numerical_checks.length+' contrôle(s) numérique(s), pas une validation complète.',' · '+result.numerical_checks.length+' numerical check(s), not full validation.'):'');if(result.sources.length)renderSourceLinks(by('studio-sources'),result.sources);else by('studio-sources').textContent=say('Aucun extrait pertinent retrouvé.','No relevant course excerpt retrieved.');if(state.currentView==='studio')play();else render();if(result.visual_mode==='generated'&&result.model&&by('studio-consent').checked){const reviewNotice=by('studio-status');const original=reviewNotice.textContent;const lesson=ui.steps;api('/api/studio/review',{method:'POST',body:JSON.stringify({question:q,steps:result.steps,author_model:result.model,consent_external:true})}).then(r=>{if(ui.steps!==lesson||turn!==ui.turn||!by('studio-consent').checked)return;reviewNotice.textContent=original+' · '+(r.verdict==='pass'?say('Relecture IA sans erreur signalée (non preuve)','AI review found no issues (not proof)'):r.verdict==='revise'?say('À vérifier : ','Review flagged: ')+r.issues.join(' / '):say('Relecture indisponible','Review unavailable'));}).catch(()=>{});}}catch(err){if(turn!==ui.turn)return;by('studio-status').textContent=err.message;if(!by('studio-question').value)by('studio-question').value=q;add('tutor',say('Impossible de charger la leçon. Réessaie.','Unable to load the lesson. Try again.'));}finally{if(turn===ui.turn){ui.request=null;ui.busy=false;by('studio-send').disabled=false;}}}
by('studio-form').addEventListener('submit',submit);
by('studio-interrupt').onclick=()=>{if(ui.recognition)ui.recognition.abort();interrupt();};
by('studio-play').onclick=()=>ui.playing?stop():play();
by('studio-prev').onclick=()=>{stop();if(ui.index>0)ui.index--;render();};
by('studio-next').onclick=()=>{stop();if(ui.index+1<ui.steps.length)ui.index++;render();};
by('studio-voice').onchange=()=>{if(ui.playing)play();};
by('studio-consent').addEventListener('change',()=>{if(!by('studio-consent').checked){narrationCache.clear();if(ui.playing)play();}});
by('studio-voice-engine').onchange=()=>{if(by('studio-voice-engine').value==='cloud'&&!by('studio-consent').checked){by('studio-voice-engine').value='local';by('studio-voice-status').textContent=say('Autorise l’IA externe pour la voix Gemini.','Enable external AI consent for Gemini speech.');return;}if(ui.playing)play();};
by('studio-clear').onclick=()=>{interrupt();narrationCache.clear();ui.history=[];ui.steps=[];ui.index=0;by('studio-chatlog').replaceChildren();by('studio-steps').replaceChildren();by('studio-caption').textContent=say('Pose une question pour démarrer.','Ask a question to begin.');by('studio-title').textContent='RDM2';by('studio-formula').textContent='ΣF = 0';by('studio-count').textContent='0 / 0';by('studio-sources').textContent='';by('studio-mode').textContent='Ready';['studio-prev','studio-next','studio-play'].forEach(id=>by(id).disabled=true);draw();};
document.querySelectorAll('[data-studio-prompt]').forEach(b=>b.onclick=()=>{by('studio-question').value=b.dataset.studioPrompt;by('studio-question').focus();});
by('studio-mic').onclick=()=>{const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;if(!Recognition){by('studio-status').textContent=say('Micro non pris en charge. Utilise le clavier.','Speech recognition unavailable. Use the keyboard.');return;}if(ui.recognition){ui.recognition.stop();return;}interrupt();let finalText='',failed=false;const r=new Recognition();r.lang=fr()?'fr-FR':'en-US';r.interimResults=true;r.continuous=false;ui.recognition=r;r.onstart=()=>{by('studio-mic').textContent='■ Stop mic';by('studio-status').textContent=say('Je t’écoute…','Listening…');};r.onresult=e=>{const results=Array.from(e.results);finalText=results.filter(x=>x.isFinal).map(x=>x[0].transcript).join(' ').slice(0,800);by('studio-question').value=results.map(x=>x[0].transcript).join(' ').slice(0,800);};r.onerror=()=>{failed=true;by('studio-status').textContent=say('Micro indisponible. Vérifie les permissions.','Microphone unavailable. Check permissions.');};r.onend=()=>{if(ui.recognition!==r)return;ui.recognition=null;by('studio-mic').textContent='● Micro';if(!failed&&by('studio-auto-send').checked&&state.currentView==='studio'&&finalText.trim().length>=3){by('studio-question').value=finalText;by('studio-form').requestSubmit();}};try{r.start();}catch{ui.recognition=null;}};
document.querySelectorAll('[data-view],[data-goto]').forEach(b=>b.addEventListener('click',()=>{if((b.dataset.view||b.dataset.goto)!=='studio'){interrupt();if(ui.recognition){const r=ui.recognition;ui.recognition=null;r.abort();by('studio-mic').textContent='● Micro';}}}));
window.addEventListener('pagehide',interrupt);draw();
})();