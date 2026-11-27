/* Authenticated local streaming ASR. No external browser recognition fallback. */
window.makeLocalSpeech=function({lang,token,onReady,onPartial,onFinal,onError,onEnd}){
 let socket=null,stream=null,context=null,node=null,source=null,ended=false,stopping=false,timer=null;
 const release=()=>{
  if(node){node.port.onmessage=null;node.disconnect();node=null;}
  if(source){source.disconnect();source=null;}
  if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}
  if(context){context.close().catch(()=>{});context=null;}
 };
 const finish=(error=null)=>{
  if(ended)return;ended=true;clearTimeout(timer);release();
  if(socket){socket.onclose=null;socket.onmessage=null;socket.onerror=null;try{socket.close()}catch{}socket=null;}
  if(error)onError(error);onEnd();
 };
 const sendEnd=()=>{
  release();
  if(socket?.readyState===WebSocket.OPEN){socket.send('end');clearTimeout(timer);timer=setTimeout(()=>finish('Speech result timeout'),8000);}
  else finish();
 };
 async function start(){
  try{
   if(!navigator.mediaDevices?.getUserMedia||!window.AudioContext||!window.AudioWorkletNode)throw Error('Local microphone unsupported');
   const captured=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
   if(ended){captured.getTracks().forEach(t=>t.stop());return;}stream=captured;
   const c=new AudioContext();context=c;await c.audioWorklet.addModule('/static/pcm-capture.js');if(ended)return;
   await c.resume();if(ended)return;
   socket=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/api/studio/listen');
   socket.onopen=()=>{if(!ended)socket.send(JSON.stringify({token,lang}));};
   socket.onerror=()=>finish('Local speech connection failed');
   socket.onclose=()=>finish('Local speech connection closed');
   socket.onmessage=e=>{
    if(ended)return;
    try{
     const msg=JSON.parse(e.data);
     if(msg.type==='ready'&&!stopping){
      clearTimeout(timer);source=c.createMediaStreamSource(stream);node=new AudioWorkletNode(c,'declic-pcm');
      node.port.onmessage=ev=>{
       if(ev.data?.type==='flushed'){sendEnd();return;}
       if(ev.data instanceof ArrayBuffer&&socket?.readyState===WebSocket.OPEN){
        if(socket.bufferedAmount>128000){finish('Local speech connection too slow');return;}
        socket.send(ev.data);
       }
      };
      source.connect(node);node.connect(c.destination);onReady();
      timer=setTimeout(()=>stop(),45000);
     }else if(msg.type==='partial'){onPartial(msg.text);}
     else if(msg.type==='final'){onFinal(msg.text);finish();}
     else if(msg.type==='error')finish(msg.message||'Local speech unavailable');
    }catch{finish('Invalid local speech response');}
   };
   timer=setTimeout(()=>finish('Local speech initialization timeout'),20000);
  }catch(e){finish(e.message||'Microphone unavailable');}
 }
 function stop(){
  if(ended||stopping)return;stopping=true;
  if(node){node.port.postMessage('flush');clearTimeout(timer);timer=setTimeout(sendEnd,300);}
  else sendEnd();
 }
 return {start,stop,abort:()=>finish()};
};
