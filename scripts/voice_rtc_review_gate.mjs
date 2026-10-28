/** Test advancement only: no model/content classifier or product permission. */
export class ReviewGate {
 constructor(session,turn,text_sha256){this.identity={session,turn,text_sha256};this.allowed=false;this.terminal=false;}
 stop(){this.terminal=true;this.allowed=false;}
 review(value){
  if(this.terminal)throw Error('TERMINAL_REVIEW_GATE');
  if(Object.entries(this.identity).some(([k,v])=>value[k]!==v))throw Error('STALE_REVIEW');
  if(value.decision!=='PASS'){this.stop();throw Error('CONTENT_REVIEW_FAILED')}
  this.allowed=true;
 }
}
export function assertNotTerminal(rows){
 if(rows.some(e=>['call_stopped','call_ended','room_disconnected','response_cancelled','turn_cancelled'].includes(e.kind)))throw Error('SESSION_TERMINAL');
}
export async function waitForTurn(read,check,{timeout=150000,wait=ms=>new Promise(r=>setTimeout(r,ms))}={}){
 const end=Date.now()+timeout;
 while(Date.now()<end){const rows=await read();assertNotTerminal(rows);const result=check(rows);if(result)return result;await wait(100)}
 throw Error('BOUNDED_WAIT_EXPIRED');
}
