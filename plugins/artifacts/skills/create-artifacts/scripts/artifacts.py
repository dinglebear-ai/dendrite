#!/usr/bin/env python3
"""Create, render, validate, browse, and export project artifact packages."""
from __future__ import annotations
import argparse
import base64
from datetime import date
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SKILL = Path(__file__).resolve().parents[1]
ENGINE = SKILL / 'references/runtime'
sys.path.insert(0,str(ENGINE))
from _app.projects import assert_project, brand_for, library_root, repository_slug, template_path
from _app.catalog import CATEGORIES, load_catalog
from _app.asset_files import embed_fonts
from _app.contracts import contract, registry
from _app import evidence

def module(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),ENGINE/'scripts'/(name+'.py'))
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def put_meta(source, key, value):
    value=html.escape(str(value),quote=True)
    pattern=r'(<meta name="artifact\.'+re.escape(key)+r'" content=")[^"]*(">)'
    source,count=re.subn(pattern,lambda m:m[1]+value+m[2],source,count=1)
    if not count: source=re.sub(r'(</title>)',lambda m:m[1]+'\n<meta name="artifact.'+key+'" content="'+value+'">',source,count=1)
    return source

def choose(args):
    return brand_for(args.repository,unraid_related=getattr(args,'unraid_related',False),worktree=getattr(args,'worktree',None))

def new(args):
    brand=choose(args)
    day=date.fromisoformat(args.date)
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',args.slug):
        raise ValueError('--slug must be descriptive lowercase words separated by hyphens')
    if args.type=='pr-reports':
        raise ValueError('use the pr-new command to create the paired PR report and evidence manifest')
    project=assert_project(args.root,args.repository)
    folder=project/args.type
    if folder.is_symlink(): raise ValueError('artifact folder must not be a symlink')
    template=template_path(args.type,brand)
    output=folder/(day.strftime('%m-%d-%y')+'-'+args.slug+template.suffix)
    content=template.read_text()
    fields={'id':repository_slug(args.repository)+'-'+args.type+'-'+day.isoformat()+'-'+args.slug,
            'status':'draft','date':day.isoformat(),'topic':args.topic or args.slug,
            'contract-version':registry()['version'],'repository':args.repository,'brand':brand,'unraid-related':str(brand=='unraid').lower(),'related':''}
    if args.worktree:
        fields['worktree']=str(Path(args.worktree).expanduser().resolve())
        for key,cmd in [('branch',['branch','--show-current']),('target',['rev-parse','HEAD'])]:
            r=subprocess.run(['git','-C',fields['worktree'],*cmd],text=True,capture_output=True)
            if r.returncode: raise ValueError(r.stderr.strip())
            fields[key]=r.stdout.strip()
    content=content.replace('{{Project}}',html.escape(args.repository))
    if template.suffix=='.html':
        for key,value in fields.items(): content=put_meta(content,key,value)
        content=embed_fonts(content)
    elif template.suffix=='.md':
        front,body=content.split('---',2)[1:]
        for key,value in fields.items():
            line='artifact.'+key+': '+json.dumps(value)
            front,count=re.subn(r'^artifact\.'+re.escape(key)+r':.*$',lambda m:line,front,count=1,flags=re.M)
            if not count: front+='\n'+line+'\n'
        content='---'+front+'---'+body
    else:
        lines=content.splitlines()
        lines[1:1]=['# artifact.'+key+': '+json.dumps(value) for key,value in fields.items()]
        content='\n'.join(lines)+'\n'
    folder.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle: handle.write(content)
    if template.suffix=='.sh': output.chmod(0o755)
    print(json.dumps({'path':str(output),'brand':brand,'state':'scaffold','next':'Fill the type-specific template with actual evidence, then validate.'},indent=2))

def render_plan(args):
    from _app.catalog import metadata
    source=args.source.resolve()
    meta=metadata(source.read_text(),'.md')
    repository=meta.get('repository') or args.repository
    if not repository: raise ValueError('plan requires artifact.repository or --repository')
    brand=brand_for(repository,unraid_related=meta.get('unraid-related')=='true')
    if meta.get('brand',brand)!=brand: raise ValueError('plan template family contradicts repository routing')
    renderer=module('render-plan')
    donor=template_path('reports',brand).read_text()
    donor=donor.replace('{{Project}}',html.escape(repository))
    css=re.search(r'<style>(.*?)</style>',donor,re.S)[1]
    header=re.search(r'<header class="top">.*?</header>',donor,re.S)[0]
    renderer.donor=lambda:(embed_fonts(css),header)
    parsed=renderer.parse(source.read_text())
    parsed['meta'].update({'repository':repository,'brand':brand})
    result=renderer.render(parsed,source.name)
    result=result.replace('Unraid Core —',html.escape(repository)+' —').replace('Core plan','Implementation Plan')
    result=result.replace('<html lang="en" data-theme="light">','<html lang="en">')
    source.with_suffix('.html').write_text(result)
    print(source.with_suffix('.html'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=library_root(),help='Artifact output root (default ~/artifacts)')
    commands=parser.add_subparsers(dest='command',required=True)
    create=commands.add_parser('new',help='Create an evidence-ready scaffold; fill it before validation')
    create.add_argument('--repository',required=True)
    create.add_argument('--type',choices=CATEGORIES,required=True)
    create.add_argument('--slug',required=True)
    create.add_argument('--date',default=date.today().isoformat())
    create.add_argument('--topic')
    create.add_argument('--worktree',type=Path)
    create.add_argument('--unraid-related',action='store_true')
    route=commands.add_parser('route',help='Resolve project template family without writing files')
    route.add_argument('--repository',required=True)
    route.add_argument('--worktree',type=Path)
    route.add_argument('--unraid-related',action='store_true')
    render=commands.add_parser('render-plan')
    render.add_argument('source',type=Path)
    render.add_argument('--repository')
    check=commands.add_parser('validate')
    check.add_argument('--path',type=Path)
    check.add_argument('--json',action='store_true')
    commands.add_parser('index')
    commands.add_parser('inventory',help='Count documents separately from evidence, datasets, and snapshots')
    commands.add_parser('init-root',help='Link root guidance to the installed plugin without duplicating instructions')
    spec=commands.add_parser('contract',help='Read the content requirements for an artifact type')
    spec.add_argument('type',choices=CATEGORIES)
    start=commands.add_parser('evidence-start',help='Allocate an artifact-owned run without executing commands')
    start.add_argument('artifact',type=Path)
    start.add_argument('--run')
    start.add_argument('--kind',choices=['verification','model-run'],default='verification')
    seal=commands.add_parser('evidence-seal',help='Hash completed files; this does not verify their claims')
    seal.add_argument('folder',type=Path)
    seal.add_argument('--producer',required=True)
    verify=commands.add_parser('evidence-verify',help='Check recorded evidence bytes without executing them')
    verify.add_argument('folder',type=Path)
    organize=commands.add_parser('organize-evidence',help='Plan or apply a lossless evidence layout migration')
    organize.add_argument('--plan',type=Path,required=True)
    organize.add_argument('--apply',action='store_true')
    serve=commands.add_parser('serve')
    serve.add_argument('--port',type=int,default=8787)
    serve.add_argument('--open',action='store_true')
    export=commands.add_parser('export')
    export.add_argument('--out',type=Path,required=True)
    for action in ('pr-new','pr'):
        child=commands.add_parser(action,add_help=False,help='PR lifecycle tools; append --help for their contract')
        child.add_argument('arguments',nargs=argparse.REMAINDER)
    args,unknown=parser.parse_known_args()
    if unknown and args.command not in {'pr-new','pr'}: parser.error('unrecognized arguments: '+' '.join(unknown))
    args.root=args.root.expanduser().resolve()
    if args.command=='contract': print(json.dumps(contract(args.type),indent=2)); return 0
    if args.command=='init-root':
        args.root.mkdir(parents=True,exist_ok=True)
        targets={'README.md':'output-README.md','AGENTS.md':'output-AGENTS.md','CLAUDE.md':'output-AGENTS.md','GEMINI.md':'output-AGENTS.md'}
        for name,target in targets.items():
            path=args.root/name;source=SKILL/'references'/target
            if path.is_symlink() and path.resolve()==source:continue
            if path.exists() or path.is_symlink():raise FileExistsError(path)
            path.symlink_to(source)
        print(args.root);return 0
    if args.command=='evidence-start': print(evidence.start(args.root,args.artifact,args.run,args.kind));return 0
    if args.command=='evidence-seal': print(json.dumps(evidence.seal(args.root,args.folder,args.producer),indent=2));return 0
    if args.command=='evidence-verify':
        result=evidence.verify(args.root,args.folder);print(json.dumps(result,indent=2));return int(bool(result['errors']))
    if args.command=='route': print(json.dumps({'repository':args.repository,'directory':repository_slug(args.repository),'brand':choose(args)})); return 0
    if args.command=='new': new(args); return 0
    if args.command=='render-plan': render_plan(args); return 0
    if args.command in {'pr-new','pr'}:
        command='new-pr-report.py' if args.command=='pr-new' else 'pr-report.py'
        forwarded=unknown+args.arguments
        if args.command=='pr-new': forwarded=['--root',str(args.root),*forwarded]
        return subprocess.run([sys.executable,str(ENGINE/'scripts'/command),*forwarded],env={**os.environ,'ARTIFACTS_ROOT':str(args.root)}).returncode
    if args.command=='serve':
        return subprocess.run([sys.executable,str(ENGINE/'scripts/app.py'),'--root',str(args.root),'--port',str(args.port),*(['--open'] if args.open else [])]).returncode
    catalog=load_catalog(args.root)
    if args.command=='inventory':print(json.dumps(evidence.inventory(args.root,catalog),indent=2));return 0
    if args.command=='organize-evidence':
        if args.apply:result=evidence.organize(args.root,json.loads(args.plan.read_text()))
        else:
            result=evidence.organization_plan(args.root,catalog)
            evidence.write_json(args.plan,result,True)
            result={'plan':str(args.plan),'bundles':len(result['moves']),'files':result['file_count']}
        print(json.dumps(result,indent=2));return 0
    if args.command=='validate':
        issues=catalog['issues']
        if args.path:
            rel=args.path.expanduser().resolve().relative_to(args.root).as_posix()
            selected=[i for i in catalog['items'] if i['href']==rel or i.get('generated_from')==rel]
            if not selected:raise ValueError('path is not a cataloged artifact')
            related_paths={rel}
            for item in selected:
                related_paths.add(item['href'])
                if item.get('generated_from'):related_paths.add(item['generated_from'])
            issues=[i for i in issues if i['where'] in related_paths]
        if args.json: print(json.dumps(issues,indent=2))
        else:
            for i in issues: print(i['severity'].upper(),i['where'],i['message'])
            print(f"{len(catalog['items'])} artifacts; {sum(i['severity']=='error' for i in issues)} errors; {sum(i['severity']=='warning' for i in issues)} warnings")
        return int(any(i['severity']=='error' for i in issues))
    from _app.render import render_index
    if args.command=='index':
        output=args.root/'index.html'
        output.write_text(embed_fonts(render_index(catalog,False)))
        print(output);return 0
    if args.command=='export':
        from _app.portable import export_catalog
        export_catalog(catalog,args.out,embed_fonts)
        print(args.out);return 0
    return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,FileExistsError,FileNotFoundError) as error:
        print('artifacts:',error,file=sys.stderr)
        raise SystemExit(2)
