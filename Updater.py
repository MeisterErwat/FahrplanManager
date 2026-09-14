import os, sys, time, urllib.request, tempfile

def main():
    if len(sys.argv) < 3: raise SystemExit("Aufruf: Updater.exe <ziel-exe> <download-url> [version]")
    target=os.path.abspath(sys.argv[1]); url=sys.argv[2]; version=sys.argv[3] if len(sys.argv)>3 else ''
    if not os.path.isfile(target): raise SystemExit("Zielprogramm nicht gefunden")
    folder=os.path.dirname(target)
    fd,tmp=tempfile.mkstemp(prefix='fm_update_',suffix='.exe',dir=folder); os.close(fd)
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'FahrplanManager-Updater'})
        with urllib.request.urlopen(req,timeout=45) as r, open(tmp,'wb') as out:
            while True:
                chunk=r.read(262144)
                if not chunk: break
                out.write(chunk)
        for _ in range(60):
            try:
                os.replace(tmp,target); break
            except PermissionError:
                time.sleep(0.25)
        else: raise RuntimeError('Alte EXE konnte nicht ersetzt werden.')
        os.startfile(target)
    except Exception as exc:
        try: os.remove(tmp)
        except OSError: pass
        raise SystemExit(f'Update fehlgeschlagen: {exc}')
if __name__=='__main__': main()
