/* Live studio: allowlisted visual scenes, browser-native speech, bounded dialogue. */
(()=>{'use strict';
const by=id=>document.getElementById(id);
const ui={steps:[],index:0,playing:false,timer:null,epoch:0,history:[],busy:false,recognition:null};
const fr=()=>state.language==='fr';
const say=(a,b)=>fr()?a:b;
const svg=by('studio-svg');
const NS='http://www.w3.org/2000/svg';
function shape(name,attrs={},text){const x=document.createElementNS(NS,name);Object.entries(attrs).forEach(([k,v])=>x.setAttribute(k,String(v)));if(text!==undefined)x.textContent=text;svg.appendChild(x);return x;}
function line(x1,y1,x2,y2,color='#73819b',width=2,dash=''){return shape('line',{x1,y1,x2,y2,stroke:color,'stroke-width':width,'stroke-dasharray':dash,'stroke-linecap':'round'});}
function text(x,y,content,color='#24314b',size=15){return shape('text',{x,y,fill:color,'font-size':size,'font-weight':600,'text-anchor':'middle'},content);}
function arrow(x,y1,y2,color,label){line(x,y1,x,y2,color,3);const d=y2>y1?1:-1;shape('path',{d:'M '+(x-6)+' '+(y2-d*9)+' L '+x+' '+y2+' L '+(x+6)+' '+(y2-d*9),fill:'none',stroke:color,'stroke-width':3});if(label)text(x,y1+(d===1?-9:19),label,color,13);}
function draw(scene='load'){
 svg.replaceChildren();const left=70,right=530,y=184,mid=300,p=185;
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
function add(role,content){const node=document.createElement('div');node.className='studio-message '+role;node.textContent=content;by('studio-chatlog').appendChild(node);by('studio-chatlog').scrollTop=by('studio-chatlog').scrollHeight;}
function stop(){ui.epoch++;ui.playing=false;clearTimeout(ui.timer);if('speechSynthesis'in window)window.speechSynthesis.cancel();by('studio-play').textContent='▶ Play';}
function render(){const s=ui.steps[ui.index];if(!s)return;draw(s.scene);by('studio-title').textContent=s.title;by('studio-formula').textContent=s.formula;by('studio-caption').textContent=s.narration;by('studio-count').textContent=(ui.index+1)+' / '+ui.steps.length;by('studio-prev').disabled=ui.index===0;by('studio-next').disabled=ui.index===ui.steps.length-1;by('studio-play').disabled=false;by('studio-steps').replaceChildren(...ui.steps.map((x,i)=>{const b=document.createElement('button');b.type='button';b.className=i===ui.index?'active':'';b.setAttribute('aria-label',x.title);b.onclick=()=>{stop();ui.index=i;render();};return b;}));}
function play(){if(!ui.steps.length)return;stop();ui.playing=true;const epoch=ui.epoch;by('studio-play').textContent='■ Stop';const advance=()=>{if(epoch!==ui.epoch||!ui.playing)return;clearTimeout(ui.timer);if(ui.index+1>=ui.steps.length){stop();return;}ui.index++;run();};function run(){render();const s=ui.steps[ui.index];if(by('studio-voice').checked&&'speechSynthesis'in window&&'SpeechSynthesisUtterance'in window){const u=new SpeechSynthesisUtterance(s.narration);u.lang=fr()?'fr-FR':'en-US';u.rate=.95;u.onend=advance;u.onerror=()=>{if(epoch===ui.epoch)ui.timer=setTimeout(advance,Math.max(3000,s.narration.length*45));};window.speechSynthesis.speak(u);}else ui.timer=setTimeout(advance,Math.max(3500,s.narration.length*55));}run();}
async function submit(e){e.preventDefault();const q=by('studio-question').value.trim();if(q.length<3||ui.busy)return;stop();ui.busy=true;by('studio-send').disabled=true;by('studio-status').textContent=say('Préparation de la leçon…','Preparing your lesson…');add('student',q);by('studio-question').value='';try{const result=await api('/api/studio',{method:'POST',body:JSON.stringify({question:q,challenge_id:state.challenge?.id||null,lang:state.language,history:ui.history.slice(-8),consent_external:by('studio-consent').checked})});ui.steps=result.steps;ui.index=0;const answer=result.steps.map(x=>x.narration).join('\n\n');add('tutor',answer);ui.history.push({role:'student',text:q},{role:'tutor',text:answer.slice(0,1600)});ui.history=ui.history.slice(-8);by('studio-mode').textContent=result.mode==='live_ai'?'AI · LIVE':say('Guide local','Local guide');by('studio-status').textContent=result.notice;by('studio-sources').textContent=result.sources.length?say('Extraits retrouvés : ','Retrieved excerpts: ')+result.sources.map(s=>s.title+', p. '+(s.page+1)).join(' · '):say('Aucun extrait pertinent retrouvé.','No relevant course excerpt retrieved.');play();}catch(err){by('studio-status').textContent=err.message;add('tutor',say('Impossible de charger la leçon. Réessaie.','Unable to load the lesson. Try again.'));}finally{ui.busy=false;by('studio-send').disabled=false;}}
by('studio-form').addEventListener('submit',submit);
by('studio-play').onclick=()=>ui.playing?stop():play();
by('studio-prev').onclick=()=>{stop();if(ui.index>0)ui.index--;render();};
by('studio-next').onclick=()=>{stop();if(ui.index+1<ui.steps.length)ui.index++;render();};
by('studio-voice').onchange=()=>{if(ui.playing)play();};
by('studio-clear').onclick=()=>{if(ui.busy)return;stop();ui.history=[];ui.steps=[];ui.index=0;by('studio-chatlog').replaceChildren();by('studio-steps').replaceChildren();by('studio-caption').textContent=say('Pose une question pour démarrer.','Ask a question to begin.');by('studio-title').textContent='RDM2';by('studio-formula').textContent='ΣF = 0';by('studio-count').textContent='0 / 0';by('studio-sources').textContent='';by('studio-mode').textContent='Ready';['studio-prev','studio-next','studio-play'].forEach(id=>by(id).disabled=true);draw();};
document.querySelectorAll('[data-studio-prompt]').forEach(b=>b.onclick=()=>{by('studio-question').value=b.dataset.studioPrompt;by('studio-question').focus();});
by('studio-mic').onclick=()=>{const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;if(!Recognition){by('studio-status').textContent=say('Micro non pris en charge. Utilise le clavier.','Speech recognition unavailable. Use the keyboard.');return;}if(ui.recognition){ui.recognition.stop();return;}stop();const r=new Recognition();r.lang=fr()?'fr-FR':'en-US';r.interimResults=true;r.continuous=false;ui.recognition=r;r.onstart=()=>{by('studio-mic').textContent='■ Stop mic';by('studio-status').textContent=say('Je t’écoute…','Listening…');};r.onresult=e=>{by('studio-question').value=Array.from(e.results).map(x=>x[0].transcript).join(' ').slice(0,800);};r.onerror=()=>{by('studio-status').textContent=say('Micro indisponible. Vérifie les permissions.','Microphone unavailable. Check permissions.');};r.onend=()=>{ui.recognition=null;by('studio-mic').textContent='● Micro';};try{r.start();}catch{ui.recognition=null;}};
document.querySelectorAll('[data-view],[data-goto]').forEach(b=>b.addEventListener('click',()=>{if((b.dataset.view||b.dataset.goto)!=='studio'){stop();if(ui.recognition)ui.recognition.stop();}}));
window.addEventListener('pagehide',stop);draw();
})();