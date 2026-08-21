#!/usr/bin/env python3
# =============================================================================
# gam_web.py - a BROWSER version of GAMGUI for headless environments like
# Google Cloud Shell (which has no graphical display for a desktop window).
#
# It reuses GAMGUI's task catalog and command builder, serves a small web UI,
# and runs gam commands on the server. View it through Cloud Shell's
# "Web Preview" button (port 8080 by default). Standard library only.
#
# Usage:
#   python3 gam_web.py            # then click Web Preview -> port 8080
#   PORT=8081 python3 gam_web.py  # use a different Cloud Shell preview port
#
# Notes:
#   - Binds to 127.0.0.1 only (Cloud Shell's Web Preview proxies to localhost),
#     so it is not exposed on the network. It runs YOUR gam with YOUR existing
#     authorization; it stores no credentials.
#   - Multi-step "workflow" tasks (incident response, bulk license, archive
#     courses, drive transfer) are desktop-only for now and are hidden here;
#     use the desktop GAMGUI or the gam CLI for those.
# =============================================================================

import os
import sys
import json
import html
import types
import subprocess
import http.server

# --- Import GAMGUI for its DATA and LOGIC only (never opens a window) --------
# GAMGUI is a tkinter app; on a headless server tkinter may not be installed.
# Stub it so the import succeeds - we only use the task catalog and the
# command builder, and we never create a Tk window.
try:
    import tkinter  # noqa: F401
except Exception:
    class _Stub:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, _n):
            return _Stub

        def __call__(self, *a, **k):
            return _Stub()

    _tk = types.ModuleType("tkinter")
    _tk.Tk = _Stub
    _tk.StringVar = _Stub
    _tk.Text = _Stub
    _tk.Frame = _Stub
    sys.modules["tkinter"] = _tk
    for _sub in ("ttk", "messagebox", "filedialog", "scrolledtext",
                 "simpledialog"):
        _m = types.ModuleType("tkinter." + _sub)
        _m.__getattr__ = lambda _name: _Stub
        sys.modules["tkinter." + _sub] = _m
        setattr(_tk, _sub, _m)

import GAMGUI as gg   # noqa: E402  (import after the tkinter stub above)

PORT = int(os.environ.get("PORT", "8080"))
GAM = gg.find_gam("")


# --- Task helpers ------------------------------------------------------------

def usable_tasks():
    # Every plain (non-workflow) task, as (category, index, task).
    for cat, tasks in gg.TASKS.items():
        for idx, task in enumerate(tasks):
            if task.get("workflow") or task.get("audit") or task.get("external"):
                continue
            yield cat, idx, task


def tasks_json():
    # Catalog for the browser: categories -> tasks -> fields.
    cats = {}
    for cat, idx, task in usable_tasks():
        field_list = []
        for f in task["fields"]:
            vmap = f.get("valuemap")
            field_list.append({
                "label": f["label"],
                "key": f["key"],
                "required": f["required"],
                "options": (list(vmap.keys()) if vmap
                            else (f["choices"] if f["choices"] is not None
                                  else None)),
            })
        cats.setdefault(cat, []).append({
            "cat": cat, "idx": idx, "name": task["name"],
            "desc": task["desc"], "destructive": task["destructive"],
            "fields": field_list,
        })
    return cats


def collect(task, values):
    # Translate any friendly dropdown value back to the gam value (valuemap).
    out = {}
    for f in task["fields"]:
        v = (values.get(f["key"], "") or "")
        vmap = f.get("valuemap")
        if vmap and v in vmap:
            v = vmap[v]
        out[f["key"]] = v
    return out


# --- The single-page web UI --------------------------------------------------

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>GAM Web</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 :root{--bg:#f6f7f9;--panel:#fff;--line:#d9dee3;--accent:#1a73e8;--warn:#c5221f}
 *{box-sizing:border-box}
 body{margin:0;font:14px/1.45 system-ui,Segoe UI,Roboto,Arial;background:var(--bg);color:#202124}
 header{background:#202124;color:#fff;padding:8px 14px;font-weight:600}
 header small{font-weight:400;color:#9aa0a6;margin-left:8px}
 .wrap{display:flex;height:calc(100vh - 39px)}
 .left{width:290px;overflow:auto;border-right:1px solid var(--line);background:var(--panel)}
 .right{flex:1;overflow:auto;padding:14px}
 .cat{padding:7px 12px;font-weight:600;background:#eef1f4;border-top:1px solid var(--line);cursor:pointer}
 .task{padding:6px 12px 6px 22px;cursor:pointer;border-top:1px solid #eef1f4}
 .task:hover{background:#eaf1fd}
 .task.sel{background:#d2e3fc}
 .task.d{color:var(--warn)}
 h2{margin:2px 0 4px;font-size:16px}
 .desc{color:#5f6368;margin-bottom:10px}
 label{display:block;margin:8px 0 2px;font-weight:600}
 input,select,textarea{width:100%;padding:6px 8px;border:1px solid var(--line);border-radius:4px;font:inherit}
 .row{margin-bottom:6px}
 .req:after{content:" *";color:var(--warn)}
 .prev{font-family:ui-monospace,Consolas,monospace;background:#f1f3f4;border:1px solid var(--line);border-radius:4px;padding:8px;margin:10px 0;white-space:pre-wrap;min-height:20px}
 button{font:inherit;padding:7px 14px;border:0;border-radius:4px;background:var(--accent);color:#fff;cursor:pointer}
 button.sec{background:#e8eaed;color:#202124}
 button:disabled{opacity:.5;cursor:default}
 .out{font-family:ui-monospace,Consolas,monospace;background:#202124;color:#e8eaed;padding:10px;border-radius:4px;white-space:pre-wrap;margin-top:12px;min-height:120px;max-height:55vh;overflow:auto}
 .gam{padding:4px 14px;background:#fef7e0;border-bottom:1px solid var(--line);font-size:12px}
 .gam.bad{background:#fce8e6;color:var(--warn)}
</style></head><body>
<header>GAM Web <small>a browser front-end for GAM (Cloud Shell friendly)</small></header>
<div id="gam" class="gam"></div>
<div class="wrap">
  <div class="left" id="tree"></div>
  <div class="right">
    <div id="pane"><p class="desc">Pick a task on the left, or use Custom command.</p></div>
  </div>
</div>
<script>
let CUR=null;
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
async function api(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return r.json();}
async function boot(){
  const g=await (await fetch('/api/gam')).json();
  const el=document.getElementById('gam');
  if(g.gam){el.textContent='gam: '+g.gam;} else {el.className='gam bad';el.textContent='gam not found on this machine - install/authorize GAM first.';}
  const cats=await (await fetch('/api/tasks')).json();
  const tree=document.getElementById('tree');
  for(const cat in cats){
    const c=document.createElement('div');c.className='cat';c.textContent=cat;tree.appendChild(c);
    for(const t of cats[cat]){
      const d=document.createElement('div');d.className='task'+(t.destructive?' d':'');d.textContent=t.name;
      d.onclick=()=>{document.querySelectorAll('.task').forEach(x=>x.classList.remove('sel'));d.classList.add('sel');showTask(t);};
      tree.appendChild(d);
    }
  }
  const cc=document.createElement('div');cc.className='task';cc.textContent='Custom command';
  cc.onclick=()=>{document.querySelectorAll('.task').forEach(x=>x.classList.remove('sel'));cc.classList.add('sel');showCustom();};
  tree.appendChild(cc);
}
function showTask(t){
  CUR=t;let h='<h2>'+esc(t.name)+'</h2><div class="desc">'+esc(t.desc)+'</div>';
  for(const f of t.fields){
    h+='<div class="row"><label class="'+(f.required?'req':'')+'">'+esc(f.label)+'</label>';
    if(f.options){h+='<select data-k="'+esc(f.key)+'">'+f.options.map(o=>'<option>'+esc(o)+'</option>').join('')+'</select>';}
    else{h+='<input data-k="'+esc(f.key)+'">';}
    h+='</div>';
  }
  h+='<div class="prev" id="prev"></div>';
  h+='<button id="run">Run</button> <button class="sec" onclick="copyCmd()">Copy</button>';
  h+='<div class="out" id="out"></div>';
  document.getElementById('pane').innerHTML=h;
  document.querySelectorAll('[data-k]').forEach(i=>i.oninput=build);
  document.getElementById('run').onclick=run;
  build();
}
function values(){const v={};document.querySelectorAll('[data-k]').forEach(i=>v[i.getAttribute('data-k')]=i.value);return v;}
async function build(){
  const r=await api('/api/build',{cat:CUR.cat,idx:CUR.idx,values:values()});
  document.getElementById('prev').textContent=r.error?('('+r.error+')'):('gam '+r.display);
  window._argv=r.argv;window._err=r.error;
}
function copyCmd(){navigator.clipboard&&navigator.clipboard.writeText(document.getElementById('prev').textContent);}
async function run(){
  if(window._err){alert('Fill in the required fields first.');return;}
  if(CUR.destructive && !confirm('This is a DESTRUCTIVE action:\\n\\ngam '+document.getElementById('prev').textContent.replace(/^gam /,'')+'\\n\\nAre you sure?'))return;
  const out=document.getElementById('out');out.textContent='Running...\\n';
  const btn=document.getElementById('run');btn.disabled=true;
  const r=await api('/api/run',{argv:window._argv});
  out.textContent=r.output+'\\n[exit code '+r.code+']';btn.disabled=false;
}
function showCustom(){
  CUR=null;
  document.getElementById('pane').innerHTML='<h2>Custom command</h2><div class="desc">Type any gam command (without the leading "gam").</div>'+
   '<div class="row"><textarea id="cc" rows="3" placeholder="print users fields primaryemail"></textarea></div>'+
   '<button id="run">Run</button><div class="out" id="out"></div>';
  document.getElementById('run').onclick=async()=>{
    const cmd=document.getElementById('cc').value.trim();if(!cmd)return;
    const out=document.getElementById('out');out.textContent='Running...\\n';
    const r=await api('/api/run',{command:cmd});
    out.textContent=r.output+'\\n[exit code '+r.code+']';
  };
}
boot();
</script></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass   # quiet

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/tasks":
            self._send(200, json.dumps(tasks_json()))
        elif self.path == "/api/gam":
            self._send(200, json.dumps({"gam": GAM}))
        else:
            self._send(404, "{}")

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or "{}")

    def do_POST(self):
        try:
            data = self._body()
        except Exception:
            self._send(400, json.dumps({"error": "bad request"}))
            return
        if self.path == "/api/build":
            try:
                task = gg.TASKS[data["cat"]][int(data["idx"])]
                if (task.get("workflow") or task.get("audit")
                        or task.get("external")):
                    self._send(200, json.dumps(
                        {"error": "This task is desktop-only for now; use the "
                                  "desktop GAMGUI or the gam CLI."}))
                    return
                display, argv, err = gg.build_command(
                    task, collect(task, data.get("values", {})))
                self._send(200, json.dumps(
                    {"display": display, "argv": argv, "error": err}))
            except Exception as exc:
                self._send(200, json.dumps({"error": str(exc)}))
        elif self.path == "/api/run":
            if not GAM:
                self._send(200, json.dumps(
                    {"output": "gam was not found on this machine.", "code": 1}))
                return
            if "command" in data:                      # custom command
                argv = _split(data["command"])
            else:
                argv = list(data.get("argv") or [])
            try:
                proc = subprocess.run([GAM] + argv, capture_output=True,
                                      text=True, encoding="utf-8",
                                      errors="replace", timeout=1800)
                self._send(200, json.dumps(
                    {"output": (proc.stdout or "") + (proc.stderr or ""),
                     "code": proc.returncode}))
            except Exception as exc:
                self._send(200, json.dumps({"output": str(exc), "code": 1}))
        else:
            self._send(404, "{}")


def _split(command):
    # Split a hand-typed command line like the desktop app does (no shell).
    s = command.strip()
    if s.lower().startswith("gam "):
        s = s[4:]
    return gg.win_split(s)


def main():
    print("GAM Web starting on http://127.0.0.1:%d/" % PORT)
    print("gam: %s" % (GAM or "(not found - install/authorize GAM first)"))
    print("In Google Cloud Shell, click 'Web Preview' -> 'Preview on port %d'."
          % PORT)
    print("Press Ctrl+C to stop.")
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
