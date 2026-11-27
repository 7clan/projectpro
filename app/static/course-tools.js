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
 for(const c of data.owned){const row=el('div','course-question');row.append(el('strong',null,c.name),button(t('Résultats','Report'),()=>report(c.id)),button(t('Devoirs','Assignments'),()=>assignments(c.id)),button(t('Supprimer','Delete'),async()=>{if(confirm(t('Supprimer cette classe ?','Delete this class?'))){await api('/api/classrooms/'+c.id,{method:'DELETE'});id('class-report').replaceChildren();await loadClasses()}}));box.append(row)}
 for(const c of data.joined){const row=el('div','course-question');row.append(el('strong',null,c.name),button(t('Devoirs','Assignments'),()=>assignments(c.id)),button(t('Quitter et arrêter le partage','Leave and stop sharing'),async()=>{await api('/api/classrooms/'+c.id+'/membership',{method:'DELETE'});await loadClasses()}));box.append(row)}
 if(!data.owned.length&&!data.joined.length)box.append(el('p','muted',t('Aucune classe','No classes')));
}
async function report(cid){
 const r=await api('/api/classrooms/'+cid+'/report');const box=id('class-report');box.replaceChildren(el('h3',null,r.classroom.name),el('p','muted',t('Activité depuis le consentement — pas des notes officielles.','Activity since consent — not official grades.')));
 for(const u of r.learners){box.append(el('p',null,u.name+' · '+u.attempts+' '+t('essais','attempts')+' · '+u.transfer_correct+'/'+u.transfer_attempts+' '+t('transferts réussis','successful transfers')))}
 if(!r.learners.length)box.append(el('p','muted',t('Aucun participant','No participants')));
}
async function assignments(cid){
 const base='/api/classrooms/'+cid+'/assignments',r=await api(base),box=id('assignment-panel');
 box.replaceChildren(el('h3',null,t('Devoirs de la classe','Class assignments')));
 if(r.owner){
  const approval=await api('/api/teacher/status');box.append(el('p','muted',approval.operator_approved?t('Compte approuvé par opérateur','Operator-approved account'):t('Identité enseignante non vérifiée','Teacher identity unverified')));
  const form=el('form'),title=el('input'),date=el('input'),level=el('select');
  title.required=true;title.minLength=2;title.maxLength=100;title.setAttribute('aria-label',t('Titre du devoir','Assignment title'));title.placeholder=t('Titre du devoir','Assignment title');
  date.type='date';date.setAttribute('aria-label',t('Échéance indicative','Suggested due date'));
  level.setAttribute('aria-label',t('Difficulté','Difficulty'));level.add(new Option(t('Facile','Easy'),'easy'));level.add(new Option(t('Avancée','Advanced'),'hard'));
  const submit=el('button','primary-btn',t('Publier 6 QCM','Publish 6 MCQs'));submit.type='submit';
  form.append(title,date,level,submit);form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;try{await api(base,{method:'POST',body:JSON.stringify({title:title.value,due_date:date.value||null,difficulty:level.value,lang:state.language,count:6})});await assignments(cid)}catch(e){showError(e)}finally{submit.disabled=false}};box.append(form);
  const trend=await api('/api/classrooms/'+cid+'/trends');for(const w of trend.weeks)box.append(el('p','muted',w.week+' · '+w.correct+'/'+w.attempts+' '+t('étapes réussies','successful stages')));
 }
 for(const a of r.assignments){
  const row=el('div','course-question');row.append(el('strong',null,a.title),el('p','muted',a.due_date||t('Sans échéance','No due date')));
  if(r.owner){row.append(button(t('Copies','Submissions')+' ('+a.submitted+')',async()=>{const report=await api(base+'/'+a.id+'/report');const out=el('div','course-question');for(const s of report.submissions)out.append(el('p',null,s.name+' · '+s.correct+'/'+s.total));if(!report.submissions.length)out.append(el('p','muted',t('Aucune copie','No submissions')));row.append(out)}));}
  else if(a.score)row.append(el('p',null,a.score.correct+'/'+a.score.total));
  else row.append(button(t('Commencer','Start'),async()=>{const quiz=await api(base+'/'+a.id);const form=el('form');for(const q of quiz.questions){const label=el('label',null,q.prompt);const input=el('select');input.name=q.id;input.required=true;input.add(new Option(t('Choisir','Choose'),''));for(const option of q.options)input.add(new Option(option,option));label.append(input);form.append(label)}const submit=el('button','primary-btn',t('Remettre','Submit'));submit.type='submit';form.append(submit);form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;try{const score=await api(base+'/'+a.id+'/submit',{method:'POST',body:JSON.stringify({answers:Object.fromEntries(new FormData(form))})});form.replaceChildren(el('h3',null,score.correct+'/'+score.total));for(const q of score.results)form.append(el('p',null,(q.correct?'✓ ':'✕ ')+q.answer+' — '+q.excerpt));}catch(e){showError(e);submit.disabled=false}};row.append(form)}));
  box.append(row);
 }
}
id('class-create').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{const r=await api('/api/classrooms',{method:'POST',body:JSON.stringify({name:id('class-name').value})});status('class-code',t('Code à partager (affiché une fois) : ','Share code (shown once): ')+r.join_code);e.target.reset();await loadClasses()}catch(e){showError(e)}finally{b.disabled=false}};
id('class-join').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{await api('/api/classrooms/join',{method:'POST',body:JSON.stringify({code:id('class-join-code').value,consent:id('class-consent').checked})});e.target.reset();await loadClasses()}catch(e){showError(e)}finally{b.disabled=false}};
document.querySelector('[data-view="quiz"]').addEventListener('click',()=>materials().catch(showError));
document.querySelector('[data-view="classroom"]').addEventListener('click',()=>loadClasses().catch(showError));
})();
