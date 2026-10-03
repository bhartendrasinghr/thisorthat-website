from datetime import date
TODAY = date(2026, 10, 1)

C2021 = [
 ('Anand Rathi Wealth', date(2021,12,14),  583.55, 2117.50, 0.25,   'bonus 1:1 x2'),
 ('Data Patterns',      date(2021,12,24),  755.00, 4251.30, 1.0,    'dividends'),
 ('Metro Brands',       date(2021,12,22),  493.35,  833.50, 1.0,    'dividends'),
 ('Paytm (One97)',      date(2021,11,18), 1560.80, 1656.00, 1.0,    'none'),
 ('Nykaa',              date(2021,11,10), 2205.80,  324.95, 0.1667, 'bonus 5:1'),
 ('PB Fintech',         date(2021,11,15), 1202.30,  980.00, 1.0,    'none'),
 ('MapmyIndia',         date(2021,12,21), 1393.65,  845.75, 1.0,    'dividends'),
 ('Star Health',        date(2021,12,10),  906.85,  537.70, 1.0,    'none'),
 ('MedPlus Health',     date(2021,12,23), 1121.15,  654.30, 1.0,    'none'),
 ('Latent View',        date(2021,11,23),  488.75,  234.48, 1.0,    'AGMs only'),
]
C2024 = [
 ('Hyundai Motor India',date(2024,10,22), 1819.60, 2024.00, 1.0, 'dividends'),
 ('Awfis Space',        date(2024, 5,30),  421.75,  235.26, 1.0, 'none'),
 ('NTPC Green',         date(2024,11,27),  121.65,   91.09, 1.0, 'none'),
 ('Swiggy',             date(2024,11,13),  456.00,  238.00, 1.0, 'none'),
 ('Bajaj Housing Fin',  date(2024, 9,16),  165.00,   82.91, 1.0, 'none'),
 ('Ola Electric',       date(2024, 8, 9),   91.20,   37.08, 1.0, 'none'),
]

def table(cohort, label):
    rows=[]
    for name, ld, lc, now, f, note in cohort:
        adj = lc*f
        ret = (now/adj-1)*100
        yrs = (TODAY-ld).days/365.25
        cagr = ((now/adj)**(1/yrs)-1)*100
        rows.append((name, ld, lc, adj, now, ret, cagr, f, note, yrs))
    rows.sort(key=lambda r:-r[5])
    print(f"\n  {label}")
    print(f"  {'Company':<21}{'Listed':>10}{'Listing':>10}{'1 Oct 26':>10}{'Return':>10}{'a year':>9}")
    print("  "+"-"*70)
    for name, ld, lc, adj, now, ret, cagr, f, note, yrs in rows:
        star='*' if f!=1.0 else ' '
        print(f"  {name+star:<21}{ld:%b %y':>10}".replace("':>10","")[:21].ljust(21)
              + f"{ld:%b %y}".rjust(10) + f"{adj:>10,.2f}{now:>10,.2f}{ret:>9.1f}%{cagr:>8.1f}%")
    r=[x[5] for x in rows]; r.sort()
    n=len(r); med = r[n//2] if n%2 else (r[n//2-1]+r[n//2])/2
    up=sum(1 for x in r if x>0)
    print(f"   up {up} of {len(r)}   median {med:+.1f}%   avg holding period {sum(x[9] for x in rows)/len(rows):.1f} yrs")
    return rows

a=table(C2021, "2021 cohort  (the boom listings)")
b=table(C2024, "2024 cohort  (the next wave)")

allr=[x[5] for x in a+b]; allr.sort()
n=len(allr); med=allr[n//2] if n%2 else (allr[n//2-1]+allr[n//2])/2
print(f"\n  All 16:  up {sum(1 for x in allr if x>0)} of 16,  median {med:+.1f}%")
print(f"  * corporate-action adjusted. Unadjusted, Nykaa reads -85.3% and Anand Rathi +262.9%.")
