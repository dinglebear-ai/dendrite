"""Embed package-owned fonts before artifact compilation or sealing."""
import base64
from pathlib import Path
import re
from .projects import SKILL, ENGINE

def embed_fonts(source):
    """Portable fonts are output dependencies, never a live CDN dependency."""
    def replace(match):
        url=match[1]
        if url.startswith('data:'): return match[0]
        name=Path(url).name
        candidates=[SKILL/'assets/fonts/aurora'/name, ENGINE/'_app/static/fonts'/name]
        found=next((p for p in candidates if p.is_file()),None)
        if not found: raise ValueError('packaged font is missing: '+name)
        return 'url("data:font/woff2;base64,'+base64.b64encode(found.read_bytes()).decode()+'")'
    notices=SKILL/'assets/fonts/licenses'
    if '@font-face' in source and 'Bundled font notices' not in source:
        license_text='\n\n'.join(f.name+'\n'+f.read_text() for f in sorted(notices.glob('*.txt')))
        source=source.replace('@font-face','/* Bundled font notices\n'+license_text.replace('*/','* /')+'\n*/\n@font-face',1)
    return re.sub(r'url\(["\']([^"\']+\.woff2)["\']\)',replace,source)
