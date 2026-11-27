/* AudioWorklet: average-resample mono microphone input to 16 kHz PCM16. */
class DeclicCapture extends AudioWorkletProcessor {
 constructor(){
  super();this.ratio=sampleRate/16000;this.phase=0;this.sum=0;this.n=0;this.buf=new Int16Array(3200);this.i=0;
  this.port.onmessage=e=>{if(e.data==='flush'){this.flush();this.port.postMessage({type:'flushed'});}};
 }
 flush(){if(this.i){const bytes=new ArrayBuffer(this.i*2),view=new DataView(bytes);for(let i=0;i<this.i;i++)view.setInt16(i*2,this.buf[i],true);this.port.postMessage(bytes,[bytes]);this.i=0;}}
 process(inputs,outputs){
  const input=inputs[0]?.[0];if(!input)return true;
  for(const x of input){
   this.sum+=x;this.n++;this.phase++;
   if(this.phase>=this.ratio){
    const v=Math.max(-1,Math.min(1,this.sum/this.n));this.buf[this.i++]=Math.round(v*(v<0?32768:32767));this.phase-=this.ratio;this.sum=0;this.n=0;
    if(this.i===this.buf.length)this.flush();
   }
  }
  return true;
 }
}
registerProcessor('declic-pcm',DeclicCapture);
