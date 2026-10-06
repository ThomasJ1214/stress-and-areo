import re,html,glob,sys,os
out={}
for f in glob.glob('docs/CalculiX/ccx_2.23/doc/ccx/node*.html'):
    t=open(f,errors='ignore').read()
    title=re.search(r'<TITLE>(.*?)</TITLE>',t,re.S|re.I)
    t=re.sub(r'<[^>]+>',' ',t); t=html.unescape(t); t=re.sub(r'\s+',' ',t)
    out[f]=(title.group(1).strip() if title else '', t)
import pickle; pickle.dump(out,open('docs/doc.pkl','wb'))
