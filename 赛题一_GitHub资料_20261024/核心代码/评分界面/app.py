"""Local-only scoring workbench; no cloud requests and no automatic input storage."""
import argparse, json, secrets, threading, webbrowser, sys, traceback, socket, os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit
from pathlib import Path
from schema import FIELDS, GROUPS, SCENARIOS
import scoring

TOKEN=secrets.token_urlsafe(32)
LOCK=threading.Lock()
STATIC=scoring.ROOT/'static'

class Handler(BaseHTTPRequestHandler):
    server_version='CreditResearch/1.0'
    def log_message(self,*args):pass
    def send(self,status,data,kind='application/json; charset=utf-8'):
        if isinstance(data,(dict,list)):data=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
        elif isinstance(data,str):data=data.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers();self.wfile.write(data)
    def host_ok(self):
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in allowed:
            self.send(403,dict(error='只允许从本机访问。'));return False
        return True
    def do_GET(self):
        if not self.host_ok():return
        path=urlsplit(self.path).path
        if path=='/api/config':
            return self.send(200,dict(token=TOKEN,fields=FIELDS,groups=GROUPS,scenarios=SCENARIOS,examples=[dict(id=k,label=v[0]) for k,v in scoring.EXAMPLES.items()]))
        if path=='/api/health':return self.send(200,dict(ready=True,model_sha256=scoring.EXPECTED_SHA))
        if path.startswith('/api/example/'):
            try:return self.send(200,scoring.example(path.rsplit('/',1)[-1]))
            except ValueError as e:return self.send(404,dict(error=str(e)))
        files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/favicon.svg':('favicon.svg','image/svg+xml')}
        if path not in files:return self.send(404,dict(error='页面不存在。'))
        name,mime=files[path];return self.send(200,(STATIC/name).read_bytes(),mime)
    def do_POST(self):
        if not self.host_ok():return
        origin=self.headers.get('Origin')
        allowed={f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}
        if origin and origin not in allowed:return self.send(403,dict(error='请求来源不正确。'))
        if self.headers.get('X-Score-Token')!=TOKEN:return self.send(403,dict(error='会话已更新，请刷新页面。'))
        path=urlsplit(self.path).path
        if path=='/api/shutdown':
            self.send(200,dict(ok=True));threading.Thread(target=self.server.shutdown,daemon=True).start();return
        if path!='/api/score':return self.send(404,dict(error='接口不存在。'))
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send(415,dict(error='请使用 JSON 格式。'))
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=65536:return self.send(413,dict(error='输入文件不能为空或超过 64 KB。'))
            self.connection.settimeout(15)
            payload=json.loads(self.rfile.read(length),parse_constant=lambda _: (_ for _ in ()).throw(ValueError('不支持非有限数字。')))
            with LOCK:result=scoring.run(payload)
            self.send(200,result)
        except (ValueError,TypeError,KeyError,OverflowError) as e:self.send(400,dict(error=str(e)))
        except (TimeoutError,socket.timeout):self.send(408,dict(error='请求读取超时，请重试。'))
        except Exception:
            if sys.stderr:traceback.print_exc()
            self.send(500,dict(error='评分未完成，请检查运行环境或重新启动。系统没有保存输入。'))

def main():
    parser=argparse.ArgumentParser(description='授信客户风险评分研究工作台')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--self-test',action='store_true',help='加载模型并核对全部保存案例后退出，不打开浏览器')
    parser.add_argument('--ready-file',type=Path,help='将实际监听地址写入指定文件，供启动核验使用')
    args=parser.parse_args()
    scoring.load()
    # A bundled known-output check catches missing modules and unsupported runtime changes.
    case=scoring.example('pure_limit')
    x,ref,*_=scoring.normalize(case)
    source=json.loads((scoring.RUNTIME/'examples/pure_limit.json').read_text(encoding='utf-8'))
    expected=json.loads((scoring.RUNTIME/'examples/pure_limit_output.json').read_text(encoding='utf-8'))
    actual=scoring.evaluate(source['current'],ref,source['previous'])
    if abs(actual['pd']-expected['pd'])>1e-10:raise RuntimeError('启动核验未通过：当前环境评分与保存结果不一致。')
    if args.self_test:
        checked=[]
        for key in scoring.EXAMPLES:
            source=json.loads((scoring.RUNTIME/'examples'/f'{key}.json').read_text(encoding='utf-8'))
            expected=json.loads((scoring.RUNTIME/'examples'/f'{key}_output.json').read_text(encoding='utf-8'))
            actual=scoring.evaluate(source['current'],source['reference_limit'],source['previous'])
            for field in ['pd','score']:
                if abs(actual[field]-expected[field])>1e-10:raise RuntimeError(f'案例核验失败：{key} / {field}')
            # Exercise the full UI adapter, including missing optional inputs and curves.
            view=scoring.run(scoring.example(key))
            if abs(view['scenario']['pd']-expected['pd'])>1e-10:raise RuntimeError(f'界面适配核验失败：{key}')
            checked.append(dict(case=key,pd=actual['pd'],score=actual['score']))
        print(json.dumps(dict(passed=True,model_sha256=scoring.EXPECTED_SHA,examples=checked),ensure_ascii=False),flush=True)
        return
    try:server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    except OSError:
        if args.port==0:raise
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    url=f'http://127.0.0.1:{server.server_port}'
    if args.ready_file:
        args.ready_file.write_text(json.dumps(dict(url=url,pid=os.getpid()),ensure_ascii=False),encoding='utf-8')
    if getattr(sys,'frozen',False) and not args.no_browser:
        try:
            (Path(sys.executable).parent/'运行地址.txt').write_text('评分平台本次运行地址：\n'+url+'\n若浏览器没有自动打开，请复制以上地址。关闭系统后此地址不再有效。\n',encoding='utf-8')
        except OSError:pass
    if sys.stdout:print('评分工作台已启动：'+url,flush=True)
    if not args.no_browser:threading.Timer(.4,lambda:webbrowser.open(url)).start()
    try:server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
