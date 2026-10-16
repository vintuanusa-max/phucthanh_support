// One request, one invocation, then detach. All objects are tool-owned.
const base=Process.getModuleByName('Viber.exe').base;
const core=Process.getModuleByName('Qt6Core.dll');
const qt=(name,ret,args)=>new NativeFunction(core.getExportByName(name),ret,args);
const type=qt('?type@QMetaType@@SAHPEBD@Z','int',['pointer']);
const size=qt('?sizeOf@QMetaType@@SAHH@Z','int',['int']);
const create=qt('?create@QMetaType@@SAPEAXHPEBX@Z','pointer',['int','pointer']);
const destroy=qt('?destroy@QMetaType@@SAXHPEAX@Z','void',['int','pointer']);
const destruct=qt('?destruct@QMetaType@@SAXHPEAX@Z','void',['int','pointer']);
const objectThread=qt('?thread@QObject@@QEBAPEAVQThread@@XZ','pointer',['pointer']);
const currentThread=qt('?currentThread@QThread@@SAPEAV1@XZ','pointer',[]);
const stringCtor=qt('??0QString@@QEAA@PEBVQChar@@_J@Z','pointer',['pointer','pointer','int64']);
const stringDtor=qt('??1QString@@QEAA@XZ','void',['pointer']);
const infoCtor=new NativeFunction(base.add(0x3278d0),'pointer',['pointer']);
const infoDtor=new NativeFunction(base.add(0x153420),'void',['pointer']);
const quoteCtor=new NativeFunction(base.add(0x77f6c0),'pointer',['pointer']);
const chatDtor=new NativeFunction(base.add(0x0505d0),'void',['pointer']);
const sendText=new NativeFunction(base.add(0x781c30),'bool',Array(7).fill('pointer'));
const chatType=type(Memory.allocUtf8String('ChatData'));
const eventType=type(Memory.allocUtf8String('EventData'));
if(size(chatType)!==280 || size(eventType)!==376)throw Error('Type layout changed');
const publicSender=base.add(0x52e3a20).readPointer();
const expectedThread=objectThread(publicSender);
let job=null, used=false, busy=false;
function execute(request) {
  const release=[]; let result={phase:'result',invoked:false,accepted:false,clean:false};
  try {
    const storage=base.add(0x52e3ad8).readPointer().add(0x28);
    const getterAddress=storage.readPointer().add(0x20).readPointer();
    if(!getterAddress.equals(base.add(0x46aeb0)))throw Error('Group getter changed');
    const getChat=new NativeFunction(getterAddress,'pointer',['pointer','pointer','pointer']);
    const id=Memory.alloc(8);id.writeU64(1);
    const chat=Memory.alloc(280);getChat(storage,chat,id);release.push(()=>chatDtor(chat));
    if(chat.readU64().toString()!=='1' || chat.add(8).readU32()!==4)throw Error('Group mismatch');
    const text=Memory.alloc(24);stringCtor(text,Memory.allocUtf16String(request.text),request.text.length);
    release.push(()=>stringDtor(text));
    if(text.add(16).readS64().toNumber()!==request.text.length)throw Error('Text mismatch');
    const date=create(16,ptr(0));if(date.isNull())throw Error('Date failed');release.push(()=>destroy(16,date));
    const quote=Memory.alloc(480);quoteCtor(quote);
    release.push(()=>{destruct(eventType,quote.add(104));stringDtor(quote.add(80));infoDtor(quote.add(64));stringDtor(quote.add(24));stringDtor(quote);});
    const info=Memory.alloc(8);infoCtor(info);release.push(()=>infoDtor(info));
    const extra=create(8,ptr(0));if(extra.isNull())throw Error('Map failed');release.push(()=>destroy(8,extra));
    const current=base.add(0x52e3a20).readPointer();
    if(!current.equals(publicSender))throw Error('Sender changed');
    const receiver=current.add(0x10).readPointer();
    const verified=base.add(0x52e39e8).readPointer().readPointer().add(0x10).readPointer()
      .add(0x28).readPointer().add(0x30).readPointer().add(0x10).readPointer();
    if(!receiver.equals(verified))throw Error('Sender identity mismatch');
    if(request.dryRun) result.dry_run=true;
    else {
      result.invoked=true;send({phase:'invoking'});
      result.accepted=sendText(receiver,chat,text,date,quote,info,extra);
    }
    result.context_verified=true;
  }catch(e){result.error=String(e).slice(0,180);}
  finally {
    const errors=[];
    for(const free of release.reverse()){try{free();}catch(e){errors.push(String(e).slice(0,100));}}
    result.clean=errors.length===0;
    if(errors.length)result.cleanup_errors=errors;
    send(result);
  }
}
const hook=Interceptor.attach(core.getExportByName('?notifyInternal2@QCoreApplication@@CA_NPEAVQObject@@PEAVQEvent@@@Z'),{
  onLeave(){
    if(!job || busy || !currentThread().equals(expectedThread))return;
    busy=true;const request=job;job=null;
    execute(request);hook.detach();send({phase:'stopped'});
  }
});
rpc.exports={queue(text,dryRun){
  if(used)throw Error('Already used');
  if(typeof text!=='string' || !text.trim() || text.length>8000)throw Error('Invalid text');
  used=true;job={text,dryRun:dryRun===true};return true;
}};
setTimeout(()=>{job=null;hook.detach();send({phase:'timeout'});},15000);
