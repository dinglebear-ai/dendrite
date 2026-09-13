#!/usr/bin/env python3
"""Plan and migrate the legacy output repository, preserving bytes and a recovery copy."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

SKILL=Path(__file__).resolve().parents[1]
ENGINE=SKILL/'references/runtime'
CATEGORIES={'reports','pr-reports','proposals','plans','specs','research','sessions','docs'}
CACHES={'__pycache__','.ruff_cache','.pytest_cache','node_modules','python310-proof-venv','.venv','venv'}
FRAMEWORK_DOCS={'CLAUDE.md','AGENTS.md','GEMINI.md','README.md'}

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def project_for(rel):
    if rel.startswith('pr-reports/') and len(Path(rel).parts)>2:
        return Path(rel).parts[1]
    if 'labby-auth' in rel: return 'dinglebear-ai-labby'
    if 'axon-' in rel or 'local-session-model' in rel or 'session-bakeoff' in rel: return 'dinglebear-ai-axon'
    if 'ci-runner-farm-plugin' in rel: return 'dinglebear-ai-unraid-elixir-plugins'
    if 'artifact-validation' in rel or rel in {'docs/EVIDENCE.md'}: return 'jmagar-artifacts'
    if 'limetech-skill-review' in rel: return 'unraid-limetech-ai-skills'
    if 'unraid-plugin-create-review' in rel: return 'dinglebear-ai-dendrite'
    return 'unraid-core'

def work_date(path):
    text=path.read_text(errors='replace')[:18000] if path.suffix in {'.html','.md'} else ''
    candidates=[(m,'metadata') for m in re.findall(r'artifact.date["\s:]+(?:content=)?["\s]*([0-9]{4}-[0-9]{2}-[0-9]{2})',text)]
    candidates += [(m,'filename') for m in re.findall(r'\b(20\d{2}-\d{2}-\d{2})\b',path.name)]
    for value,reason in candidates:
        try: return datetime.strptime(value,'%Y-%m-%d').strftime('%m-%d-%y'),reason
        except ValueError: continue
    return datetime.fromtimestamp(path.stat().st_mtime).strftime('%m-%d-%y'),'original filesystem modification date'

def dated_name(path):
    day,reason=work_date(path)
    stem=re.sub(r'(?:^20\d{2}-\d{2}-\d{2}-|[-_]20\d{2}-\d{2}-\d{2}$)','',path.stem)
    stem=re.sub(r'[^a-z0-9]+','-',stem.lower()).strip('-')
    return day+'-'+stem+path.suffix,reason

def classify(source,path):
    rel=path.relative_to(source).as_posix()
    parts=Path(rel).parts
    if path.is_symlink(): return 'compatibility',None,None
    if path.name == '.DS_Store' or path.name.endswith('.package.lock'):
        return 'recovery-only',None,'filesystem bookkeeping'
    if any(p in CACHES or p.endswith('.egg-info') for p in parts) or path.suffix=='.pyc' or path.name.startswith('._'):
        return 'recovery-only',None,'rebuildable environment or cache'
    if parts[0] in {'_app','_tests'} or path.name in FRAMEWORK_DOCS or path.name.startswith('_template'):
        return 'framework',None,None
    if parts[0]=='.git' or parts[0] in {'.gitignore','.gitattributes'}:
        return 'git',rel,None
    if parts[0]=='scripts':
        if path.name.startswith('prove-') or path.name=='empirical-plugin-evidence.exs':
            name,reason=dated_name(path)
            return 'artifact','unraid-core/scripts/'+name,reason
        return 'framework',None,None
    if rel in {'index.html','index-meta.json','docs/DEPLOYMENT.md'} or rel.startswith('pr-reports/schema/'):
        return 'framework',None,None
    if parts[0]=='dist':
        if path.name=='index-meta.json': return 'recovery-only',None,'legacy export configuration'
        if path.name in FRAMEWORK_DOCS or path.name.startswith('_template'):
            return 'recovery-only',None,'legacy portable framework copy'
        return 'artifact','jmagar-artifacts/exports/09-13-26-legacy-export/'+str(Path(*parts[1:])),None
    if parts[0]=='.runs':
        return 'artifact','dinglebear-ai-axon/research/evidence/legacy-runs/'+str(Path(*parts[1:])),None
    if parts[0]=='review-archives':
        return 'artifact','dinglebear-ai-axon/reports/evidence/'+str(Path(*parts[1:])),None
    if parts[0]=='depot-live-e2e':
        return 'artifact','unraid-core/reports/evidence/depot-live-e2e/'+str(Path(*parts[1:])),None
    if parts[0] in CATEGORIES:
        project=project_for(rel)
        if 'evidence' in parts or len(parts)> (3 if parts[0]=='pr-reports' else 2):
            tail=Path(*parts[2:]) if parts[0]=='pr-reports' else Path(*parts[1:])
            return 'artifact',project+'/'+parts[0]+'/'+str(tail),None
        if path.name.endswith(('.evidence.jsonl','.manifest.json','.package.lock','.evidence.jsonl.lock','.candidate','.pre-finalize')):
            return 'paired',project+'/'+parts[0]+'/'+path.name,None
        name,reason=dated_name(path)
        return 'artifact',project+'/'+parts[0]+'/'+name,reason
    if len(parts)==1 and path.suffix=='.md':
        name,reason=dated_name(path)
        return 'artifact',project_for(rel)+'/reports/'+name,reason
    return 'unknown',None,None

def build_plan(source,destination):
    records=[]
    for directory,dirs,files in os.walk(source,followlinks=False):
        dirs[:]=[d for d in dirs if d!='.git']
        # Preserve directory symlinks as compatibility entries without following them.
        for d in list(dirs):
            path=Path(directory)/d
            if path.is_symlink(): files.append(d);dirs.remove(d)
        for name in sorted(files):
            path=Path(directory)/name
            action,target,reason=classify(source,path)
            rel=path.relative_to(source).as_posix()
            records.append({'old':rel,'new':target,'action':action,'date_source':reason,
                            'sha256':None if path.is_symlink() else digest(path),
                            'symlink':os.readlink(path) if path.is_symlink() else None})
    mapping={r['old']:r['new'] for r in records if r['action']=='artifact'}
    for record in records:
        if record['action']!='paired':continue
        old=record['old']
        # Paired state follows the exact renamed HTML stem; never rename by its own mtime.
        report=re.sub(r'\.(?:evidence\.jsonl(?:\.lock|\.candidate|\.pre-finalize)?|manifest\.json|package\.lock)$','.html',old)
        target=mapping.get(report)
        if target:
            suffix=old[len(report[:-5]):]
            record['new']=target[:-5]+suffix
        record['action']='artifact'
        mapping[old]=record['new']
    destinations=[r['new'] for r in records if r['new']]
    duplicates=sorted({p for p in destinations if destinations.count(p)>1})
    unknown=[r['old'] for r in records if r['action']=='unknown']
    head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    status=subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True)
    return {'version':1,'source':str(source),'destination':str(destination),'head':head,'status_before':status,
            'artifact_paths':mapping,'records':records,'collisions':duplicates,'unknown':unknown}

def apply(plan,backup):
    source=Path(plan['source']);destination=Path(plan['destination'])
    backup=backup.absolute()
    paths=[source.resolve(),destination.resolve(),backup.resolve()]
    if any(a.is_relative_to(b) or b.is_relative_to(a) for n,a in enumerate(paths) for b in paths[n+1:]):
        raise ValueError('source, destination, and backup must be separate non-overlapping paths')
    if destination.exists() or destination.is_symlink() or backup.exists():
        raise FileExistsError('destination and recovery path must both be absent')
    if plan['unknown'] or plan['collisions']:
        raise ValueError('resolve unknown paths and collisions before applying')
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=plan['head']:
        raise ValueError('source Git history changed after planning')
    fresh=build_plan(source,destination)
    if fresh['records']!=plan['records'] or fresh['status_before']!=plan['status_before']:
        raise ValueError('source inventory or Git status changed after planning; create a fresh plan')
    for item in plan['records']:
        path=source/item['old']
        if item['sha256'] and digest(path)!=item['sha256']:
            raise ValueError('source changed after planning: '+item['old'])
    stage=Path(tempfile.mkdtemp(prefix='.artifact-migration-',dir=destination.parent))
    try:
        # Copy outputs first. Leave the original repository untouched until every byte is verified.
        for item in plan['records']:
            if item['action'] not in {'artifact','git'}:continue
            target=stage/item['new'];target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source/item['old'],target)
            if digest(target)!=item['sha256']:raise ValueError('copy verification failed: '+item['old'])
        shutil.copytree(source/'.git',stage/'.git',symlinks=True)
        receipt=stage/'jmagar-artifacts/reports/09-13-26-artifact-migration.json'
        receipt.parent.mkdir(parents=True,exist_ok=True)
        plan['backup']=str(backup)
        plan['verified_at']=datetime.now().astimezone().isoformat()
        receipt.write_text(json.dumps(plan,indent=2)+'\n')
        # Same-filesystem rename preserves the complete original (including untracked work).
        os.rename(source,backup)
        try: os.rename(stage,destination)
        except BaseException:
            os.rename(backup,source)
            raise
        source.mkdir()
        for item in plan['records']:
            old=source/item['old']
            if item['action']=='artifact': target=destination/item['new']
            elif item['action']=='framework':
                parts=Path(item['old']).parts
                if parts[0] in {'_app','_tests','scripts'}:target=ENGINE/item['old']
                elif item['old']=='index.html':target=destination/'index.html'
                elif item['old']=='index-meta.json':target=SKILL/'references/legacy-index-meta.json'
                elif parts[-1].startswith('_template'):target=SKILL/'assets/templates/unraid'/parts[0]/parts[-1]
                elif parts[0]=='pr-reports' and 'schema' in parts:target=ENGINE/item['old']
                elif len(parts)>1 and parts[-1] in FRAMEWORK_DOCS:target=SKILL/'references/types'/(parts[0]+'.md')
                else:target=SKILL/'SKILL.md'
            else:continue
            if old.exists() or old.is_symlink():continue
            old.parent.mkdir(parents=True,exist_ok=True)
            old.symlink_to(target)
        # Recorded absolute evidence paths into archived caches still resolve through recovery.
        for item in plan['records']:
            if item['action'] not in {'recovery-only','compatibility'}:continue
            old=source/item['old']
            if old.exists() or old.is_symlink():continue
            old.parent.mkdir(parents=True,exist_ok=True)
            old.symlink_to(backup/item['old'])
        print(json.dumps({'destination':str(destination),'backup':str(backup),'artifacts':len(plan['artifact_paths']),'receipt':str(destination/receipt.relative_to(stage))},indent=2))
    finally:
        if stage.exists():shutil.rmtree(stage)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--backup',type=Path)
    args=parser.parse_args()
    if args.apply:
        if not args.backup:parser.error('--apply requires --backup')
        saved=json.loads(args.plan.read_text())
        if str(args.source.expanduser().resolve())!=saved['source'] or str(args.destination.expanduser().resolve())!=saved['destination']:
            parser.error('supplied paths do not match the reviewed plan')
        apply(saved,args.backup.expanduser().absolute())
    else:
        plan=build_plan(args.source.expanduser().resolve(),args.destination.expanduser().resolve())
        with args.plan.open('x') as out:json.dump(plan,out,indent=2)
        print(json.dumps({'counts':{k:sum(r['action']==k for r in plan['records']) for k in sorted({r['action'] for r in plan['records']})},'unknown':plan['unknown'],'collisions':plan['collisions'],'plan':str(args.plan)},indent=2))

if __name__=='__main__':main()
