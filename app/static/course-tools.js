/* Source-exact quiz and opt-in classrooms. All user content rendered as text. */
(()=>{
let quiz=null,busy=false,revision=0;
const id=x=>document.getElementById(x);
const status=(x,message)=>{id(x).textContent=message};
function button(label,action){const b=el('button','secondary-btn',label);b.type='button';b.onclick=()=>Promise.resolve(action()).catch(showError);return b;}
async function materials(){
 const docs=await api('/api/documents');const select=id('quiz-document'),previous=select.value;
 select.replaceChildren(new Option(t('Tous mes cours','All courses'),''));
 for(const d of docs.documents)select.add(new Option(d.title,d.id));
 if([...select.options].some(o=>o.value===previous))select.value=previous;
}
id('quiz-start').onclick=async()=>{
 if(busy)return;busy=true;id('quiz-start').disabled=true;
 try{
  quiz=await api('/api/quizzes',{method:'POST',body:JSON.stringify({document_id:id('quiz-document').value||null,count:Number(id('quiz-count').value),kind:id('quiz-kind').value,difficulty:id('quiz-difficulty').value,lang:state.language})});
  id('quiz-results').replaceChildren();id('quiz-questions').replaceChildren();
  for(const [i,q] of quiz.questions.entries()){
   const wrap=el('div','course-question');const label=el('label',null,(i+1)+'. '+q.prompt);label.htmlFor='q-'+q.id;
   const input=el(q.options?'select':'input');input.id='q-'+q.id;input.required=true;if(q.options){input.add(new Option(t('Choisir','Choose'),''));for(const o of q.options)input.add(new Option(o,o));}else{input.maxLength=200;input.autocomplete='off';}
   wrap.append(label,el('small','muted',q.title+(q.page!==null?' · p. '+(q.page+1):' · '+(q.difficulty||''))),input);id('quiz-questions').append(wrap);
  }
  id('quiz-form').hidden=false;id('quiz-form').querySelector('button').disabled=false;
  status('quiz-status',quiz.questions.length+' / '+quiz.eligible_pages+' '+t('questions / pages lisibles','questions / readable pages'));
 }catch(e){showError(e)}finally{busy=false;id('quiz-start').disabled=false}
};
id('quiz-form').onsubmit=async e=>{
 e.preventDefault();if(!quiz||busy)return;busy=true;const submit=id('quiz-form').querySelector('button');submit.disabled=true;
 try{
  const answers=Object.fromEntries(quiz.questions.map(q=>[q.id,id('q-'+q.id).value]));
  const r=await api('/api/quizzes/'+quiz.id+'/submit',{method:'POST',body:JSON.stringify({answers})});
  const target=id('quiz-results');target.replaceChildren(el('h3',null,r.correct+' / '+r.total));
  for(const q of r.results){const row=el('div','course-question');row.append(el('strong',null,(q.correct?'✓ ':'✕ ')+q.answer),el('p',null,q.excerpt),button(q.title+' · p. '+(q.page+1),()=>openCourseSource(q)));target.append(row)}
  id('quiz-form').hidden=true;quiz=null;
 }catch(e){showError(e);submit.disabled=false}finally{busy=false}
};
async function loadClasses(){
 const r=++revision;const data=await api('/api/classrooms');if(r!==revision)return;
 const box=id('class-list');box.replaceChildren(el('h3',null,t('Mes classes','My classes')));
 for(const c of data.owned){const row=el('div','course-question');row.append(el('strong',null,c.name),button(t('Résultats','Report'),()=>report(c.id)),button(t('Supprimer','Delete'),async()=>{if(confirm(t('Supprimer cette classe ?','Delete this class?'))){await api('/api/classrooms/'+c.id,{method:'DELETE'});id('class-report').replaceChildren();await loadClasses()}}));box.append(row)}
 for(const c of data.joined){const row=el('div','course-question');row.append(el('strong',null,c.name),button(t('Quitter et arrêter le partage','Leave and stop sharing'),async()=>{await api('/api/classrooms/'+c.id+'/membership',{method:'DELETE'});await loadClasses()}));box.append(row)}
 if(!data.owned.length&&!data.joined.length)box.append(el('p','muted',t('Aucune classe','No classes')));
}
async function report(cid){
 const r=await api('/api/classrooms/'+cid+'/report');const box=id('class-report');box.replaceChildren(el('h3',null,r.classroom.name),el('p','muted',t('Activité depuis le consentement — pas des notes officielles.','Activity since consent — not official grades.')));
 for(const u of r.learners){box.append(el('p',null,u.name+' · '+u.attempts+' '+t('essais','attempts')+' · '+u.transfer_correct+'/'+u.transfer_attempts+' '+t('transferts réussis','successful transfers')))}
 if(!r.learners.length)box.append(el('p','muted',t('Aucun participant','No participants')));
}
id('class-create').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{const r=await api('/api/classrooms',{method:'POST',body:JSON.stringify({name:id('class-name').value})});status('class-code',t('Code à partager (affiché une fois) : ','Share code (shown once): ')+r.join_code);e.target.reset();await loadClasses()}catch(e){showError(e)}finally{b.disabled=false}};
id('class-join').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{await api('/api/classrooms/join',{method:'POST',body:JSON.stringify({code:id('class-join-code').value,consent:id('class-consent').checked})});e.target.reset();await loadClasses()}catch(e){showError(e)}finally{b.disabled=false}};
document.querySelector('[data-view="quiz"]').addEventListener('click',()=>materials().catch(showError));
document.querySelector('[data-view="classroom"]').addEventListener('click',()=>loadClasses().catch(showError));
})();
