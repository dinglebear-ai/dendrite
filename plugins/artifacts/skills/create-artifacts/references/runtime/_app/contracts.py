"""Shared, brand-independent content requirements and structural checks."""
import json
from html.parser import HTMLParser
from .projects import SKILL
from .validate import issue

def registry():
    return json.loads((SKILL/'references/contracts/types.json').read_text())

def contract(category):
    data=registry()
    if category not in data['types']:raise ValueError('unknown artifact type: '+category)
    return {'version':data['version'],'type':category,**data['types'][category]}

class Records(HTMLParser):
    VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self):
        super().__init__();self.records=[];self.active=None;self.stack=[];self.record_depth=0
    def handle_starttag(self,tag,attrs):
        classes=set(dict(attrs).get('class','').split())
        if tag not in self.VOID:self.stack.append((tag,classes))
        if tag=='details' and 'issue' in classes and self.active is None:
            self.active={'classes':set(),'text':{}};self.record_depth=len(self.stack)
        if self.active is not None:self.active['classes'].update(classes)
    def handle_data(self,data):
        if self.active is None or not data.strip():return
        for _,classes in self.stack[self.record_depth-1:]:
            for cls in classes:self.active['text'][cls]=self.active['text'].get(cls,'')+data
    def handle_endtag(self,tag):
        for index in range(len(self.stack)-1,-1,-1):
            if self.stack[index][0]!=tag:continue
            if self.active is not None and index<self.record_depth:
                self.records.append(self.active);self.active=None
            del self.stack[index:];break

def check_content(item,source):
    """Structural completeness only; never proof that an artifact is factually sound."""
    version=item['meta'].get('contract-version')
    if not version:return []  # Historical artifacts retain their original contract.
    rule=contract(item['category']);where=item['href'];issues=[]
    if version!=rule['version']:return [issue('error',where,'unsupported artifact.contract-version','CONTENT-VERSION')]
    if item['kind']!='html' or not rule['record_blocks']:return issues
    parser=Records();parser.feed(source)
    if not parser.records and not item['meta'].get('empty-reason'):
        issues.append(issue('error',where,'no content records; explain a deliberately empty result in artifact.empty-reason','CONTENT-EMPTY'))
    for n,record in enumerate(parser.records,1):
        missing={block for block in rule['record_blocks'] if block not in record['classes'] or not record['text'].get(block,'').strip()}
        if missing:issues.append(issue('error',where,f'content record {n} has missing or empty content: '+', '.join(sorted(missing)),'CONTENT-STRUCTURE'))
    return issues
