"""Artifact-owned evidence bundles, lossless organization, and honest inventory."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

BUNDLE='_bundle.json'

def stamp():return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def slug(value):
    value=re.sub(r'[^a-z0-9]+','-',str(value).lower()).strip('-')
    if not value:raise ValueError('empty evidence identity')
    return value[:180]
def bounded(root,path):
    root=root.resolve();path=path.absolute()
    path.relative_to(root)
    for part in [path,*path.parents]:
        if part==root:break
        if part.is_symlink():raise ValueError('evidence path uses a symlink: '+str(part))
    if not path.resolve().is_relative_to(root):raise ValueError('evidence path escapes output root')
    return path

def files(folder):
    for directory,dirs,names in os.walk(folder,followlinks=False):
        dirs[:]=sorted(d for d in dirs if not (Path(directory)==folder and d=='.git') and not (Path(directory)/d).is_symlink())
        for name in sorted(names):
            p=Path(directory)/name
            if p.is_file() and not p.is_symlink():yield p

def records(folder):
    result=[]
    for directory,dirs,names in os.walk(folder,followlinks=False):
        for name in [*dirs,*names]:
            if (Path(directory)/name).is_symlink():raise ValueError('evidence contains a symlink: '+str(Path(directory)/name))
        dirs.sort()
        for name in sorted(names):
            p=Path(directory)/name
            if p==folder/BUNDLE:continue
            if not p.is_file():raise ValueError('evidence contains a non-regular file: '+str(p))
            result.append({'path':p.relative_to(folder).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)})
    return sorted(result,key=lambda r:r['path'])

def write_json(path,data,exclusive=False):
    if exclusive:
        with path.open('x') as f:json.dump(data,f,indent=2);f.write('\n')
    else:
        temp=path.with_name(path.name+'.'+stamp()+'.tmp')
        try:
            with temp.open('x') as f:json.dump(data,f,indent=2);f.write('\n')
            os.replace(temp,path)
        finally:temp.unlink(missing_ok=True)

def start(root,artifact,run=None,kind='verification'):
    from .catalog import load_catalog
    root=root.resolve();artifact=artifact.resolve();rel=artifact.relative_to(root).as_posix()
    item=next((i for i in load_catalog(root)['items'] if i['href']==rel or i.get('generated_from')==rel),None)
    if not item:raise ValueError('evidence must name a cataloged owning artifact')
    run=run or stamp()
    if run!=slug(run) and not re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z_-]{0,179}',run):raise ValueError('invalid run ID')
    folder=bounded(root,root/item['project']/'_evidence'/Path(item['href']).stem/run)
    folder.mkdir(parents=True,exist_ok=False)
    for name in ('raw','derived'):(folder/name).mkdir()
    data={'version':1,'artifact':item['href'],'artifact_id':item['id'],'repository':item['repository'],'run':run,'kind':kind,'created_at':datetime.now(timezone.utc).isoformat(),'state':'open','files':[]}
    write_json(folder/BUNDLE,data,True)
    return folder

def seal(root,folder,producer):
    folder=bounded(root,folder.expanduser().absolute());path=folder/BUNDLE;data=json.loads(path.read_text())
    if data['state']!='open':raise ValueError('sealed evidence is immutable; create a new run')
    data.update(state='sealed',producer=producer,sealed_at=datetime.now(timezone.utc).isoformat(),files=records(folder))
    write_json(path,data)
    return {'bundle':str(folder),'files':len(data['files']),'state':'sealed'}

def verify(root,folder):
    folder=bounded(root,folder.absolute());data=json.loads((folder/BUNDLE).read_text());errors=[]
    if data.get('state')!='sealed':errors.append('bundle is not sealed')
    expected={r['path']:r for r in data.get('files',[])}
    for rel in expected:
        if Path(rel).is_absolute() or '..' in Path(rel).parts:errors.append('unsafe manifest path: '+rel)
    actual={r['path']:r for r in records(folder)}
    for rel in sorted(set(expected)|set(actual)):
        if expected.get(rel)!=actual.get(rel):errors.append('missing, changed, or unrecorded file: '+rel)
    return {'bundle':str(folder),'files':len(actual),'errors':errors}

def inventory(root,catalog):
    all_files=list(files(root));visible={i['href'] for i in catalog['items']};sources={i['generated_from'] for i in catalog['items'] if i.get('generated_from')}
    evidence=[p for p in all_files if len(p.relative_to(root).parts)>1 and p.relative_to(root).parts[1]!='exports' and ('_evidence' in p.relative_to(root).parts or 'evidence' in p.relative_to(root).parts)]
    bundles=[];invalid_bundles=[]
    for p in evidence:
        if p.name==BUNDLE:
            try:
                data=json.loads(p.read_text())
                if not isinstance(data,dict) or data.get('kind') not in {'verification','model-run','legacy-evidence'} or data.get('state') not in {'open','sealed'} or not isinstance(data.get('files'),list):raise ValueError('invalid bundle metadata')
                bundles.append(data)
            except (ValueError,OSError):invalid_bundles.append(p.relative_to(root).as_posix())
    return {'catalog_items':len(visible),'documents':sum(i['kind'] in {'html','md'} for i in catalog['items']),
        'html_documents':sum(i['kind']=='html' for i in catalog['items']),
        'proof_scripts':sum(i['category']=='scripts' for i in catalog['items']),
        'datasets':sum(i['kind'] in {'json','jsonl'} for i in catalog['items']),
        'paired_sources':len(sources),'evidence_files':sum(p.name!=BUNDLE for p in evidence),'evidence_bundles':len(bundles),
        'invalid_bundles':invalid_bundles,'model_runs':sum(b['kind']=='model-run' for b in bundles),'snapshot_files':sum(len(p.relative_to(root).parts)>1 and p.relative_to(root).parts[1]=='exports' for p in all_files),
        'physical_files_excluding_git':len(all_files),'bytes_excluding_git':sum(p.stat().st_size for p in all_files),
        'by_type':dict(Counter(i['category'] for i in catalog['items']))}

def organization_plan(root,catalog):
    root=root.resolve();moves=[]
    for project in sorted(root.iterdir()):
        if not project.is_dir() or project.is_symlink() or project.name.startswith(('.', '_')):continue
        for typ in sorted(project.iterdir()):
            area=typ/'evidence'
            if not typ.is_dir() or typ.is_symlink() or not area.is_dir() or area.is_symlink():continue
            candidates=[p for p in area.iterdir() if p.is_dir() and not p.is_symlink()]
            for old in sorted(candidates):
                if old.name=='legacy-runs':groups=sorted(p for p in old.iterdir() if p.is_dir() and not p.is_symlink())
                else:groups=[old]
                for source in groups:
                    matches=[i for i in catalog['items'] if i['project']==project.name and i['category']==typ.name and (re.sub(r'^\d{2}-\d{2}-\d{2}-','',Path(i['href']).stem)==old.name or old.name.startswith(re.sub(r'^\d{2}-\d{2}-\d{2}-','',Path(i['href']).stem)+'-'))]
                    if old.name=='legacy-runs':matches=[i for i in catalog['items'] if i['project']==project.name and i['category']=='research' and i['kind']=='html']
                    owner=matches[0] if len(matches)==1 else None
                    key=Path(owner['href']).stem if owner else '_shared-'+slug(old.name)
                    run=('model-'+slug(source.name)) if old.name=='legacy-runs' else 'legacy-import'
                    destination=project/'_evidence'/key/run/'legacy'
                    bounded(root,source);bounded(root,destination)
                    if destination.parent.exists():raise FileExistsError(destination.parent)
                    entries=records(source)
                    if not entries:continue
                    moves.append({'source':source.relative_to(root).as_posix(),'destination':destination.relative_to(root).as_posix(),'artifact':owner['href'] if owner else None,'artifact_id':owner['id'] if owner else None,'kind':'model-run' if old.name=='legacy-runs' else 'legacy-evidence','files':entries})
    return {'version':1,'root':str(root),'moves':moves,'file_count':sum(len(m['files']) for m in moves)}

def organize(root,plan):
    root=root.resolve()
    if plan['root']!=str(root):raise ValueError('plan belongs to a different root')
    for move in plan['moves']:
        source=bounded(root,root/move['source']);destination=bounded(root,root/move['destination'])
        if records(source)!=move['files']:raise ValueError('evidence changed after planning: '+move['source'])
        if destination.parent.exists():raise FileExistsError(destination.parent)
    receipt=bounded(root,root/'jmagar-artifacts/_evidence/_system/organization'/(stamp()+'.json'))
    applied=[];created=[]
    try:
        for move in plan['moves']:
            source=root/move['source'];destination=root/move['destination'];folder=destination.parent
            folder.mkdir(parents=True,exist_ok=False);created.append(folder)
            os.rename(source,destination);applied.append((source,destination))
            source.symlink_to(os.path.relpath(destination,source.parent),target_is_directory=True)
            data={'version':1,'artifact':move['artifact'],'artifact_id':move['artifact_id'],'run':folder.name,'kind':move['kind'],'state':'sealed','producer':'lossless legacy organization','created_at':datetime.now(timezone.utc).isoformat(),'original_directory':move['source'],'files':[dict(r,path='legacy/'+r['path']) for r in move['files']]}
            write_json(folder/BUNDLE,data,True)
            if verify(root,folder)['errors']:raise ValueError('moved evidence verification failed')
        receipt.parent.mkdir(parents=True,exist_ok=True);write_json(receipt,plan,True)
        return {'moved_files':plan['file_count'],'bundles':len(applied),'receipt':str(receipt)}
    except BaseException:
        for source,destination in reversed(applied):
            if source.is_symlink():source.unlink()
            os.rename(destination,source)
        for folder in reversed(created):
            (folder/BUNDLE).unlink(missing_ok=True)
            try:folder.rmdir()
            except OSError:pass
        raise
