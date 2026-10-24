"""Frozen entry point: initialize diagnostics before importing model dependencies."""
from pathlib import Path
import sys,traceback,tempfile

def main():
    diagnostic=('--self-test' in sys.argv or '--no-browser' in sys.argv)
    stream=None
    if getattr(sys,'frozen',False) and (sys.stdout is None or sys.stderr is None):
        for folder in [Path(sys.executable).parent,Path(tempfile.gettempdir())/'CreditScoreResearch']:
            try:
                folder.mkdir(parents=True,exist_ok=True)
                path=folder/'startup.log'
                stream=path.open('w',encoding='utf-8',buffering=1)
                if sys.stdout is None:sys.stdout=stream
                if sys.stderr is None:sys.stderr=stream
                break
            except OSError:continue
    try:
        from app import main as app_main
        app_main()
    except Exception as e:
        if sys.stderr:traceback.print_exc()
        if sys.platform=='win32' and not diagnostic:
            import ctypes
            location=('\n详细记录：'+str(path)) if stream else ''
            ctypes.windll.user32.MessageBoxW(None,'评分平台启动失败：\n'+str(e)+location+'\n请先完整解压后运行，不要单独移动exe文件。','信用评分平台',16)
        raise SystemExit(1)
    finally:
        if stream:stream.flush()

if __name__=='__main__':main()
