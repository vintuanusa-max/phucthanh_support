"""Read native pattern rectangles from an unchanged, hash-bound Illustrator copy."""
import base64, hashlib, json, subprocess
from pathlib import Path
from urllib.parse import unquote

SCAN = r'''(function(){var d=null,old=app.userInteractionLevel,prev=app.documents.length?app.activeDocument:null,out=[];
try{app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;d=app.open(new File(__SOURCE__));
if(d.documentColorSpace!==DocumentColorSpace.CMYK)throw Error('CMYK required');
for(var n=0;n<d.artboards.length;n++)out.push('A\t'+n+'\t'+d.artboards[n].artboardRect.join(','));
for(var i=0;i<d.pathItems.length;i++){var p=d.pathItems[i];if(!p.filled||p.fillColor.typename!=='PatternColor'||p.clipping||p.hidden||p.opacity!==100||p.pathPoints.length!==4||p.width<140||p.height<140)continue;
var ok=true,parent=p.parent,b=p.geometricBounds;while(parent&&parent.typename!=='Document'){if(parent.hidden||parent.visible===false||parent.opacity!==undefined&&parent.opacity!==100||parent.clipped)ok=false;parent=parent.parent;}
for(var j=0;j<4;j++){var q=p.pathPoints[j],a=q.anchor;if((Math.abs(a[0]-b[0])>.1&&Math.abs(a[0]-b[2])>.1)||(Math.abs(a[1]-b[1])>.1&&Math.abs(a[1]-b[3])>.1)||a[0]!==q.leftDirection[0]||a[1]!==q.leftDirection[1]||a[0]!==q.rightDirection[0]||a[1]!==q.rightDirection[1])ok=false;}
if(ok)out.push('P\t'+i+'\t'+encodeURIComponent(p.fillColor.pattern.name)+'\t'+b.join(','));}
return out.join('\n');}finally{if(d)d.close(SaveOptions.DONOTSAVECHANGES);app.userInteractionLevel=old;if(prev){try{prev.activate();}catch(e){}}}})()'''

def recover_illustrator_271(run_result):
    out=(run_result.stderr+run_result.stdout).decode('utf-8',errors='replace')
    if '271' not in out:return False
    check=(
        "$p=@(Get-Process Illustrator -ErrorAction SilentlyContinue); "
        "if($p.Count -gt 0 -and @($p | Where-Object { -not [string]::IsNullOrWhiteSpace($_.MainWindowTitle) }).Count -eq 0){ "
        "$p | ForEach-Object { $_.CloseMainWindow() | Out-Null }; "
        "$d=[DateTime]::UtcNow.AddSeconds(5); while((Get-Process Illustrator -ErrorAction SilentlyContinue) -and [DateTime]::UtcNow -lt $d){ Start-Sleep -Milliseconds 250 }; "
        "if(Get-Process Illustrator -ErrorAction SilentlyContinue){ Stop-Process -Name Illustrator -Force -ErrorAction SilentlyContinue }; "
        "Write-Output 'restarted' }"
    )
    chk=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',check],capture_output=True,timeout=30)
    if 'restarted' in chk.stdout.decode('utf-8',errors='replace'):
        __import__('time').sleep(2)
        return True
    return False

def jsx_run(script,folder):
    target=Path(folder)/'native-job.jsx';target.write_text(script,encoding='utf-8')
    command=__import__("adobe_ready").ready_command("Illustrator.Application","$a")+"$a.DoJavaScript([IO.File]::ReadAllText((Join-Path (Get-Location) 'native-job.jsx')))"
    from font_dialog_guard import FontDialogGuard
    with FontDialogGuard(folder):
        r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],cwd=folder,capture_output=True,timeout=360)
    if r.returncode and recover_illustrator_271(r):
        with FontDialogGuard(folder):
            r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],cwd=folder,capture_output=True,timeout=360)
    if r.returncode:raise ValueError('Illustrator native inspection/export failed; review before retry')
    return r.stdout.decode('utf-8',errors='replace').strip()

def inspect(raw,folder):
    import pymupdf as fitz
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(raw).hexdigest();cache=folder/'native.json'
    if cache.exists():
        result=json.loads(cache.read_text());assert result['source_sha256']==digest
        from pattern_repeat import enrich
        result=enrich(result,folder/'source.ai');cache.write_text(json.dumps(result),encoding='utf-8');return result
    started=folder/'started.json'
    started.unlink(missing_ok=True)
    started.write_text(json.dumps({'sha256':digest}),encoding='utf-8')
    src=folder/'source.ai';src.write_bytes(raw)
    try:text=jsx_run(SCAN.replace('__SOURCE__',json.dumps(str(src).replace('\\','/'))),folder)
    finally:started.unlink(missing_ok=True)
    boards=[];objects=[]
    for line in text.splitlines():
        v=line.split('\t')
        if v[0]=='A':boards.append([float(x) for x in v[2].split(',')])
        elif v[0]=='P':objects.append(dict(id='np'+v[1],index=int(v[1]),pattern=unquote(v[2]),native_bbox=[float(x) for x in v[3].split(',')]))
    if len(boards)>8 or len(objects)>32:raise ValueError('Native pattern inventory too large')
    with fitz.open(src) as doc:
        for obj in objects:
            x0,y1,x1,y0=obj['native_bbox'];matches=[i for i,b in enumerate(boards) if x0>=b[0]-.1 and x1<=b[2]+.1 and y1<=b[1]+.1 and y0>=b[3]-.1]
            if len(matches)!=1:raise ValueError('Pattern outside a unique source artboard')
            page=matches[0];b=boards[page];box=[x0-b[0],b[1]-y1,x1-b[0],b[1]-y0]
            pix=doc[page].get_pixmap(clip=fitz.Rect(box),matrix=fitz.Matrix(500/max(x1-x0,y1-y0),500/max(x1-x0,y1-y0)),colorspace=fitz.csRGB)
            obj.update(page=page+1,bbox_pt=box,width_cm=(x1-x0)*2.54/72,height_cm=(y1-y0)*2.54/72,preview=base64.b64encode(pix.tobytes('png')).decode())
    result=dict(source_sha256=digest,artboards=boards,objects=objects)
    from pattern_repeat import enrich
    result=enrich(result,src)
    cache.write_text(json.dumps(result),encoding='utf-8');return result
