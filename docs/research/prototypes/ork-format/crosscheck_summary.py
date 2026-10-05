import json, glob, math, os, sys
rows = []
summ_keys = ['maxaltitude','maxvelocity','maxacceleration','maxmach','timetoapogee','flighttime','launchrodvelocity','groundhitvelocity','deploymentvelocity']
tot = {'sims':0,'with_data':0,'summary_ok':0,'mass_ok':0,'mass_n':0,'cg_ok':0,'cg_n':0,'ref_ok':0,'ref_n':0}
bad = []
for f in sorted(glob.glob('out/json/*.json')):
    r = json.load(open(f))
    short = os.path.basename(f).replace('.ork.json','').replace('core_src_main_resources_datafiles_examples__','').replace('swing_resources_datafiles_examples__','')
    for s in r['simulations']:
        tot['sims'] += 1
        if 'summary' not in s or not s.get('branches'): continue
        if not s['branches'] or s['branches'][0]['n_points'] == 0: continue
        tot['with_data'] += 1
        d = s.get('derived_from_data', {}); st = s['summary']
        mism = []
        for k in summ_keys:
            if k in st and k in d and not (math.isnan(st[k]) and math.isnan(d[k])):
                tol = max(0.0015, 1e-3*abs(st[k]))   # stored with 3 decimals / 4 sig. digits
                if abs(st[k]-d[k]) > tol: mism.append('%s %.4g/%.4g' % (k, st[k], d[k]))
        if not mism: tot['summary_ok'] += 1
        c = s.get('crosscheck', {})
        line = '%-62s %-22s' % (short[:62], (s['name'] or '')[:22])
        if 'ref_len_stored' in c:
            tot['ref_n'] += 1; ok = abs(c['ref_len_stored']-c['ref_len_model']) <= 0.0006
            tot['ref_ok'] += ok; line += ' ref %s' % ('ok' if ok else 'XX %.4f/%.4f' % (c['ref_len_stored'], c['ref_len_model']))
        if 'dry_mass_stored' in c:
            tot['mass_n'] += 1; e = c['dry_mass_model']-c['dry_mass_stored']; rel = e/c['dry_mass_stored'] if c['dry_mass_stored'] else float('nan')
            ok = abs(e) <= max(0.0011, 0.005*c['dry_mass_stored'])
            tot['mass_ok'] += ok; line += ' | mass %.4f vs %.3f (%+.2f%%)%s' % (c['dry_mass_model'], c['dry_mass_stored'], 100*rel, '' if ok else ' XX')
        if 'cg_stored' in c:
            tot['cg_n'] += 1; e = c['cg_model_motorCGatMid']-c['cg_stored']; ok = abs(e) <= 0.002
            tot['cg_ok'] += ok; line += ' | cg %.4f vs %.3f (%+.1fmm)%s' % (c['cg_model_motorCGatMid'], c['cg_stored'], 1000*e, '' if ok else ' XX')
        elif 'cg_note' in c: line += ' | cg skipped(multi-motor)'
        if mism: line += ' | SUMMARY MISMATCH ' + ', '.join(mism)
        rows.append(line)
print('\n'.join(rows))
print()
print(tot)
