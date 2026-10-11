import json,sys
t=json.load(open('c50.json'))
sc=t['transform']['scale'];tr=t['transform']['translate']
arcs=[]
for a in t['arcs']:
    x=y=0;pts=[]
    for dx,dy in a:
        x+=dx;y+=dy;pts.append((x*sc[0]+tr[0],y*sc[1]+tr[1]))
    arcs.append(pts)
def arc(i):
    return arcs[i] if i>=0 else arcs[~i][::-1]
def ring(idx):
    out=[]
    for i in idx:
        p=arc(i)
        out.extend(p if not out else p[1:])
    return out
def dp(pts,eps):
    if len(pts)<4:return pts
    keep=[False]*len(pts);keep[0]=keep[-1]=True
    st=[(0,len(pts)-1)]
    while st:
        a,b=st.pop()
        ax,ay=pts[a];bx,by=pts[b];dx=bx-ax;dy=by-ay;L=dx*dx+dy*dy
        mx=-1;mi=-1
        for i in range(a+1,b):
            px,py=pts[i]
            if L==0:d=(px-ax)**2+(py-ay)**2
            else:
                u=max(0,min(1,((px-ax)*dx+(py-ay)*dy)/L));d=(px-ax-u*dx)**2+(py-ay-u*dy)**2
            if d>mx:mx=d;mi=i
        if mx>eps*eps:keep[mi]=True;st.append((a,mi));st.append((mi,b))
    return [p for p,k in zip(pts,keep) if k]
EPS=float(sys.argv[1]) if len(sys.argv)>1 else 0.04
def S(s):return set(x.strip() for x in s.split(';'))
EU=S("Austria;Belgium;Bulgaria;Croatia;Cyprus;N. Cyprus;Czechia;Denmark;Estonia;Finland;France;Germany;Greece;Hungary;Ireland;Italy;Latvia;Lithuania;Luxembourg;Malta;Netherlands;Poland;Portugal;Romania;Slovakia;Slovenia;Spain;Sweden;Norway;United Kingdom;Switzerland;Iceland;Serbia;Bosnia and Herz.;Montenegro;Macedonia;Albania;Kosovo;Ukraine;Moldova;Belarus;Andorra;Monaco;Liechtenstein;San Marino;Vatican;Åland;Faeroe Is.;Jersey;Guernsey;Isle of Man")
R={}
R['europe']=EU
R['russia_cis']=S("Russia;Kazakhstan;Uzbekistan;Turkmenistan;Kyrgyzstan;Tajikistan;Azerbaijan;Armenia;Georgia")
R['middle_east']=S("Saudi Arabia;Iran;Iraq;Kuwait;United Arab Emirates;Qatar;Bahrain;Oman;Yemen;Israel;Palestine;Jordan;Lebanon;Syria;Turkey;Egypt")
R['east_asia']=S("China;Japan;South Korea;North Korea;Taiwan;Mongolia;Vietnam;Thailand;Malaysia;Singapore;Indonesia;Philippines;Myanmar;Cambodia;Laos;Brunei;Timor-Leste;Australia;New Zealand;Hong Kong;Macao")
R['south_asia']=S("India;Pakistan;Bangladesh;Sri Lanka;Nepal;Bhutan;Afghanistan;Maldives")
R['north_america']=S("United States of America;Canada;Mexico;Greenland")
AMER=S("Argentina;Bolivia;Brazil;Chile;Colombia;Ecuador;Guyana;Paraguay;Peru;Suriname;Uruguay;Venezuela;Belize;Costa Rica;El Salvador;Guatemala;Honduras;Nicaragua;Panama;Cuba;Dominican Rep.;Haiti;Jamaica;Bahamas;Barbados;Trinidad and Tobago;Antigua and Barb.;Dominica;Grenada;Saint Lucia;St. Kitts and Nevis;St. Vin. and Gren.;Puerto Rico;U.S. Virgin Is.;Anguilla;Aruba;Bermuda;British Virgin Is.;Cayman Is.;Curaçao;Falkland Is.;Montserrat;Sint Maarten;St-Barthélemy;St-Martin;Turks and Caicos Is.;St. Pierre and Miquelon;Trinidad and Tobago")
R['latin_america']=AMER
AFR=S("Algeria;Angola;Benin;Botswana;Burkina Faso;Burundi;Cabo Verde;Cameroon;Central African Rep.;Chad;Comoros;Congo;Dem. Rep. Congo;Côte d'Ivoire;Djibouti;Eq. Guinea;Eritrea;eSwatini;Ethiopia;Gabon;Gambia;Ghana;Guinea;Guinea-Bissau;Kenya;Lesotho;Liberia;Libya;Madagascar;Malawi;Mali;Mauritania;Mauritius;Morocco;Mozambique;Namibia;Niger;Nigeria;Rwanda;São Tomé and Principe;Senegal;Seychelles;Sierra Leone;Somalia;Somaliland;South Africa;S. Sudan;Sudan;Tanzania;Togo;Tunisia;Uganda;W. Sahara;Zambia;Zimbabwe;Saint Helena")
R['africa']=AFR
rev={}
for k,v in R.items():
    for n in v:rev[n]=k
feats=[];miss=[]
for g in t['objects']['countries']['geometries']:
    n=g['properties']['name']
    if n in('Antarctica','Fr. S. Antarctic Lands','Heard I. and McDonald Is.','S. Geo. and the Is.','Siachen Glacier'):continue
    polys=g['arcs'] if g['type']=='MultiPolygon' else [g['arcs']] if g['type']=='Polygon' else []
    outp=[]
    for poly in polys:
        rings=[]
        for k,r in enumerate(poly):
            pts=ring(r)
            xs=[p[0] for p in pts];ys=[p[1] for p in pts]
            if max(xs)-min(xs)<0.12 and max(ys)-min(ys)<0.12 and not(k==0 and len(polys)==1):continue
            q=dp(pts,EPS)
            if len(q)<4:continue
            # антимеридиан: разворачиваем скачки долготы >180, чтобы кольцо было непрерывным
            u=[q[0]];off=0
            for a,b in zip(q,q[1:]):
                if b[0]-a[0]>180:off-=360
                elif b[0]-a[0]<-180:off+=360
                u.append((b[0]+off,b[1]))
            mx=max(p[0] for p in u);mn=min(p[0] for p in u)
            if mn<-180 or mx>180 or True:
                shift=0
                if mn>=180 or (mx>180 and mn>0 and mx-180>180-mn):shift=-360
                u=[(x+shift,y) for x,y in u];mx+=shift;mn+=shift
            R=[[round(x,2),round(y,2)] for x,y in u]
            rings.append(R)
            if k==0:
                extra=[]
                if mx>180:extra=[[ [round(x-360,2),y] for x,y in R]]
                elif mn<-180:extra=[[ [round(x+360,2),y] for x,y in R]]
                for e in extra:outp.append([e])
        if rings:outp.append(rings)
    if not outp:continue
    r=rev.get(n)
    if r is None:miss.append(n)
    feats.append({"type":"Feature","properties":{"n":n,"r":r},"geometry":{"type":"MultiPolygon","coordinates":outp}})
json.dump({"type":"FeatureCollection","features":feats},open(sys.argv[2],'w'),separators=(',',':'),ensure_ascii=False)
print(len(feats),'no region:',miss)
