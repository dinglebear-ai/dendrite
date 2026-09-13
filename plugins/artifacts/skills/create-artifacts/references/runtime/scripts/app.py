#!/usr/bin/env python3
"""Serve the cached, validated artifact workbench on localhost."""
from __future__ import annotations
import argparse, gzip, hashlib, json, mimetypes, sys, webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ENGINE=Path(__file__).resolve().parent.parent
ROOT=ENGINE
sys.path.insert(0,str(ROOT))
from _app.render import render_artifact, render_index, render_viewer  # noqa:E402
from _app.search import search as find_text  # noqa:E402
from _app.shell import render_shell  # noqa:E402
from _app.store import CatalogStore  # noqa:E402
from _app.catalog import CATEGORIES  # noqa:E402

SHELL_CACHE={}


def shell_page(catalog,item,state,enriched):
    """Cache rendered shells against the catalog signature.

    The catalog already caches discovery; rendering did not, so every artifact
    view rebuilt the whole sidebar and outline. The signature changes whenever
    any file does, which is exactly when the cache should drop.
    """
    key=(catalog["signature"],item["href"],state)
    if key not in SHELL_CACHE:
        SHELL_CACHE.clear()
        SHELL_CACHE[key]=render_shell(catalog,item,state,enriched)
    return SHELL_CACHE[key]

STORE=None
ASSETS=ENGINE/"_app"/"static"

def public_catalog(catalog):
    artifacts=[]
    for group in catalog["groups"]:
        for item in group["items"]:
            artifacts.append({k:v for k,v in item.items() if k!="source"}|{"category":group["name"]})
    return artifacts

def safe_path(rel, roots):
    target=(ROOT/rel).resolve()
    if ROOT.resolve() not in target.parents or not target.is_file(): raise FileNotFoundError(rel)
    if target.relative_to(ROOT).parts[0] not in roots: raise FileNotFoundError(rel)
    return target

class Handler(BaseHTTPRequestHandler):
    server_version="ProjectArtifactLibrary/4.0"
    def do_GET(self):
        route=unquote(urlsplit(self.path).path); query=parse_qs(urlsplit(self.path).query)
        try:
            catalog=STORE.get()
            by_path={item["href"]:item for item in catalog["items"]}
            rel=route.lstrip("/")
            alias=catalog.get("aliases",{}).get(rel)
            if alias:
                self.send_response(302); self.send_header("Location","/"+alias); self.end_headers(); return
            if route in ("/","/index.html"): self.html(render_index(catalog,True))
            elif route=="/api/artifacts": self.json({"generated_at":datetime.now(timezone.utc).isoformat(),"count":len(catalog["items"]),"signature":catalog["signature"],"issues":catalog["issues"],"artifacts":public_catalog(catalog)})
            elif route=="/api/status": self.json(self.status_payload(catalog))
            elif route=="/find": self.json({"query":query.get("q",[""])[0],"results":find_text(catalog,query.get("q",[""])[0])})
            elif route=="/healthz": self.json({"status":"healthy"})
            elif route=="/readyz": self.json({"status":"ready","catalog":self.package_state(catalog)})
            elif route=="/events": self.events(catalog)
            elif route.startswith("/view/"): self.html(render_viewer(ROOT,route.removeprefix("/view/"),catalog,query.get("mode",["rendered"])[0]))
            elif route.startswith("/raw/"):
                raw=route.removeprefix("/raw/")
                allowed=set(by_path) | {i["generated_from"] for i in catalog["items"] if i.get("generated_from")}
                if raw not in allowed: raise FileNotFoundError(raw)
                self.file(safe_path(raw,{p.split("/")[0] for p in allowed}),attachment=query.get("download")==["1"])
            elif route.startswith("/assets/"):
                asset=(ASSETS/route.removeprefix("/assets/")).resolve()
                if ASSETS.resolve() not in asset.parents or not asset.is_file(): raise FileNotFoundError(route)
                self.file(asset,cache="public, max-age=3600")
            elif rel in by_path and by_path[rel]["kind"]=="html":
                if query.get("shell")==["0"]: self.html(render_artifact(by_path[rel]["source"],by_path[rel]))
                else:
                    state=self.package_state(catalog)
                    page=shell_page(catalog,by_path[rel],state,render_artifact(by_path[rel]["source"],by_path[rel]))
                    self.html(page,cache="no-cache",
                              etag='"'+hashlib.sha256((catalog["signature"]+rel+state).encode()).hexdigest()[:16]+'"')
            elif rel.startswith(tuple(name+"/" for name in CATEGORIES)) and Path(rel).name.startswith("_template"):
                self.file(safe_path(rel,set(g["name"] for g in catalog["groups"])))
            else: self.send_error(HTTPStatus.NOT_FOUND,"Published artifact route not found")
        except FileNotFoundError: self.send_error(HTTPStatus.NOT_FOUND,"Artifact not found")
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception as error: self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR,"Artifact rendering failed",explain=str(error))

    def do_HEAD(self): self.send_error(HTTPStatus.METHOD_NOT_ALLOWED,"HEAD is not exposed")
    @staticmethod
    def package_state(c):
        return "error" if any(i["severity"]=="error" for i in c["issues"]) else ("warning" if c["issues"] else "clean")
    @staticmethod
    def status_payload(c):
        return {"status":Handler.package_state(c),"signature":c["signature"],"artifacts":len(c["items"]),"issues":len(c["issues"]),"errors":sum(i["severity"]=="error" for i in c["issues"]),"warnings":sum(i["severity"]=="warning" for i in c["issues"])}
    def events(self,c):
        self.send_response(200);self.send_header("Content-Type","text/event-stream");self.send_header("Cache-Control","no-store");self.send_header("Connection","keep-alive");self.security_headers();self.end_headers()
        current=c["signature"]
        while True:
            latest=STORE.wait_for_change(current)
            payload=json.dumps({"signature":latest["signature"],"status":Handler.package_state(latest)})
            self.wfile.write(f"data: {payload}\n\n".encode());self.wfile.flush();current=latest["signature"]
    def html(self,value,cache="no-store",etag=None):
        self.bytes(value.encode(),"text/html; charset=utf-8",cache=cache,etag=etag)
    def json(self,value): self.bytes(json.dumps(value,indent=2).encode(),"application/json; charset=utf-8")
    def file(self,path,attachment=False,cache="no-store"):
        kind=mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        headers={"Content-Disposition":f'attachment; filename="{path.name}"'} if attachment else {}
        body=path.read_bytes()
        self.bytes(body,kind,headers=headers,cache=cache,
                   etag='"'+hashlib.sha256(body).hexdigest()[:16]+'"')
    COMPRESSIBLE=("text/","application/json","image/svg","application/javascript")

    def bytes(self,body,kind,status=200,headers=None,cache="no-store",etag=None):
        headers=dict(headers or {})
        # A conditional request costs one round trip instead of the whole body.
        if etag:
            headers["ETag"]=etag
            if self.headers.get("If-None-Match")==etag:
                self.send_response(304);self.send_header("ETag",etag)
                self.send_header("Cache-Control",cache);self.security_headers();self.end_headers()
                return
        # Artifacts are 75-150KB of markup; over a tailnet that is worth compressing.
        if (len(body)>1024 and kind.startswith(self.COMPRESSIBLE)
                and "gzip" in self.headers.get("Accept-Encoding","")):
            body=gzip.compress(body,6)
            headers["Content-Encoding"]="gzip";headers["Vary"]="Accept-Encoding"
        self.send_response(status);self.send_header("Content-Type",kind)
        self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control",cache)
        self.security_headers()
        for key,value in headers.items(): self.send_header(key,value)
        self.end_headers();self.wfile.write(body)
    def security_headers(self):
        self.send_header("X-Content-Type-Options","nosniff");self.send_header("Referrer-Policy","no-referrer");self.send_header("X-Frame-Options","DENY");self.send_header("Content-Security-Policy","default-src 'self' file:; font-src 'self' data: file:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: file:")

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def handle_error(self,request,client_address):
        if isinstance(sys.exc_info()[1],(BrokenPipeError,ConnectionResetError)):
            return
        super().handle_error(request,client_address)

def args():
    p=argparse.ArgumentParser(description="Serve repository artifact outputs on localhost")
    from _app.projects import library_root
    p.add_argument("--root",type=Path,default=library_root())
    p.add_argument("--host",default="127.0.0.1");p.add_argument("--port",type=int,default=8787);p.add_argument("--open",action="store_true");p.add_argument("--no-watch",action="store_true");p.add_argument("--strict",action="store_true");p.add_argument("--json",action="store_true");p.add_argument("--export",action="store_true")
    return p.parse_args()

def main():
    global STORE,ROOT
    options=args();ROOT=options.root.expanduser().resolve();STORE=CatalogStore(ROOT)
    if options.json: print(json.dumps(Handler.status_payload(STORE.get()),indent=2));return
    if options.export:
        (ROOT/"index.html").write_text(render_index(STORE.get(),False));print("Wrote index.html");return
    if options.strict and any(i["severity"]=="error" for i in STORE.get()["issues"]): raise SystemExit("artifact validation errors prevent strict startup")
    if not options.no_watch: STORE.start()
    server=Server((options.host,options.port),Handler);host,port=server.server_address[:2];display="127.0.0.1" if host in ("0.0.0.0","::") else host;url=f"http://{display}:{port}/"
    print(f"Artifact library: {url}\nCached discovery: {'manual' if options.no_watch else 'watching'}")
    if options.open:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:print("\nStopping artifact library.")
    finally:STORE.stop();server.server_close()

if __name__=="__main__":main()
