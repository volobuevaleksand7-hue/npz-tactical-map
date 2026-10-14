(function(){
'use strict';
var LANG=(document.documentElement.getAttribute("lang")==="en")?"en":"ru";
var EN=LANG==="en";
var TX={
 ru:{world:"Мировой индекс",of100:"из 100",low:"мало данных",nodata:"нет данных",perDay:"за сутки",cover:"покрытие данных",calc:"расчёт:",meth:"методика:",
  comps:"Компоненты",compsPick:"Компоненты · выберите регион",compsHint:"Выберите регион в списке или нажмите на страну на карте: здесь появится разбивка по компонентам (балл × вес).",
  noReg:"Нет данных по региону.",contrib:"вклад",wNoRedist:"вес {w}% не перераспределяется",allWorld:"Весь мир",outside:"вне регионов индекса",noneYet:"данных пока нет",
  confirmed:"подтверждено",reported:"по сообщениям, один источник",close:"Закрыть",effFuel:"Влияние на топливо",effIdx:"Влияние на индекс",photoAlt:"Иллюстрация к событию",
  license:"Лицензия",notSet:"не указана",author:"Автор",authorNone:"не указан",filePage:"страница файла",sources:"Источники",prec:"Точность места",zone:"зона, радиус ≈ {r} км",point:"точка",
  est:"ОЦЕНКА · OSINT",ev1:"событие",ev2:"события",ev5:"событий",noEv:"Событий пока нет.",evFail:"Не удалось загрузить события.",geoFail:"Границы стран не загрузились",
  slice:"Срез: ",idxNone:"Индекс: данных пока нет",methVer:"версия методики ",influences:"Влияет на: ",computing:"Индекс считается — данных пока нет.",
  now:"Сейчас",untr:""},
 en:{world:"World index",of100:"out of 100",low:"insufficient data",nodata:"no data",perDay:"24h",cover:"data coverage",calc:"computed:",meth:"methodology:",
  comps:"Components",compsPick:"Components · select a region",compsHint:"Select a region in the list or click a country on the map to see the component breakdown (score × weight).",
  noReg:"No data for this region.",contrib:"contribution",wNoRedist:"weight {w}% is not redistributed",allWorld:"Whole world",outside:"outside the index regions",noneYet:"no data yet",
  confirmed:"confirmed",reported:"reported, single source",close:"Close",effFuel:"Effect on fuel",effIdx:"Effect on the index",photoAlt:"Event illustration",
  license:"License",notSet:"not specified",author:"Author",authorNone:"not specified",filePage:"file page",sources:"Sources",prec:"Location accuracy",zone:"zone, radius ≈ {r} km",point:"point",
  est:"ESTIMATE · OSINT",ev1:"event",ev2:"events",ev5:"events",noEv:"No events yet.",evFail:"Could not load events.",geoFail:"Country borders failed to load",
  slice:"Snapshot: ",idxNone:"Index: no data yet",methVer:"methodology version ",influences:"Affects: ",computing:"The index is being computed — no data yet.",
  now:"Now",untr:"Not yet translated — shown in Russian."}};
function t(k,v){var s=TX[LANG][k];if(s===undefined)s=TX.ru[k];if(v)for(var x in v)s=s.replace("{"+x+"}",v[x]);return s;}
var RAW="https://raw.githubusercontent.com/volobuevaleksand7-hue/npz-tactical-map/main/";
var LOCAL=/^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
var DEMO=/[?&]demo=1\b/.test(location.search);
var REGIONS=EN?[["europe","Europe"],["russia_cis","Russia / CIS"],["middle_east","Middle East"],["east_asia","East Asia"],["south_asia","South Asia"],["north_america","North America"],["latin_america","Latin America"],["africa","Africa"]]:[["europe","Европа"],["russia_cis","Россия / СНГ"],["middle_east","Ближний Восток"],["east_asia","Восточная Азия"],["south_asia","Южная Азия"],["north_america","Северная Америка"],["latin_america","Латинская Америка"],["africa","Африка"]];
var RNAME={asia:EN?"Asia":"Азия"};REGIONS.forEach(function(r){RNAME[r[0]]=r[1];});
var RBOUNDS={europe:[[34,-12],[71,45]],russia_cis:[[36,24],[74,150]],middle_east:[[10,24],[42,66]],east_asia:[[-45,92],[54,155]],south_asia:[[4,60],[37,93]],north_america:[[14,-168],[72,-52]],latin_america:[[-56,-118],[33,-34]],africa:[[-36,-20],[37,52]]};
var LEVELS=EN?{calm:["calm","#367866"],tense:["tense","#b38b38"],crisis:["crisis","#cb6035"],critical:["critical","#a92522"]}:{calm:["спокойно","#367866"],tense:["напряжённо","#b38b38"],crisis:["кризис","#cb6035"],critical:["критично","#a92522"]};
var COMPS=EN?[["chokepoints","Chokepoints",30],["shortage_news","Shortage news",15],["retail","Retail prices",15],["stocks","Stocks",15],["prices","Prices",10],["diesel_crack","Diesel crack",5],["georisk","Geopolitical risk",5],["phys_premium","Physical premium",5]]:[["chokepoints","Узкие места",30],["shortage_news","Новости о дефиците",15],["retail","Розница",15],["stocks","Запасы",15],["prices","Цены",10],["diesel_crack","Крэк дизеля",5],["georisk","Геориск",5],["phys_premium","Физическая премия",5]];
var CHOKE=[
 {id:"hormuz",n:EN?"Strait of Hormuz":"Ормузский пролив",ll:[26.57,56.25],r:EN?"Middle East, South Asia, East Asia":"Ближний Восток, Южная Азия, Восточная Азия"},
 {id:"bab",n:EN?"Bab el-Mandeb":"Баб-эль-Мандеб",ll:[12.58,43.33],r:EN?"Europe, Middle East":"Европа, Ближний Восток"},
 {id:"suez",n:EN?"Suez Canal":"Суэцкий канал",ll:[30.5,32.34],r:EN?"Europe":"Европа"},
 {id:"malacca",n:EN?"Strait of Malacca":"Малаккский пролив",ll:[2.4,101.9],r:EN?"East Asia":"Восточная Азия"},
 {id:"bosporus",n:EN?"Bosporus":"Босфор",ll:[41.12,29.07],r:EN?"Europe, Russia / CIS":"Европа, Россия / СНГ"},
 {id:"cape",n:EN?"Cape of Good Hope":"Мыс Доброй Надежды",ll:[-34.36,18.47],r:EN?"Africa (traffic growth = rerouting)":"Африка (рост трафика = обход)"}];
var ICONS={
 attack_shipping:'<path d="M3 15l2 5h14l2-5zM12 3v9M8 12h8"/>',
 strike:'<path d="M12 2l2.5 6.5L21 9l-5 4.5L17.5 21 12 17l-5.5 4L8 13.5 3 9l6.5-.5z"/>',
 outage:'<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
 shortage:'<path d="M12 3c4 5 6 8 6 11a6 6 0 0 1-12 0c0-3 2-6 6-11z"/>',
 stocks_release:'<path d="M12 4v12M6 11l6 6 6-6M5 20h14"/>',
 opec:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
 other:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>'};

var BRAND_FALLBACK={short:"ИТН",short_en:"FTI",ru:"Индекс топливной напряжённости",en:"Fuel Tension Index"};
var NOW_PARAM=(/[?&]now=([^&]+)/.exec(location.search)||[])[1];
var NOW_MS=NOW_PARAM&&!isNaN(Date.parse(decodeURIComponent(NOW_PARAM)))?Date.parse(decodeURIComponent(NOW_PARAM)):null;
function nowMs(){return NOW_MS!==null?NOW_MS:Date.now();}
var FRESH_MS=72*3600*1000,HOT_TYPES={strike:1,attack_shipping:1,naval:1,seizure:1,outage:1};
function isFresh(e){var t=Date.parse(e.occurred_at);if(isNaN(t))return false;var d=nowMs()-t;return d<=FRESH_MS&&d>=-86400000;}
function isHot(e){return !!HOT_TYPES[e.type];}
var CHOKE_REG={hormuz:["middle_east","south_asia","east_asia"],bab:["europe","middle_east"],suez:["europe"],malacca:["east_asia"],bosporus:["europe","russia_cis"],cape:["africa"]};
function brand(){var b=IDX&&IDX.brand||{};return {short:EN?(b.short_en||BRAND_FALLBACK.short_en):(b.short||BRAND_FALLBACK.short),ru:b.ru||BRAND_FALLBACK.ru,en:b.en||BRAND_FALLBACK.en};}
function brandName(){var b=brand();return (EN?b.en:b.ru)+" · "+b.short;}
function chokeHot(id){var rs=CHOKE_REG[id]||[],m=0;rs.forEach(function(r){var i=regionInfo(r);((i&&i.components)||[]).forEach(function(c){if(c.id==="chokepoints"&&c.score>m)m=c.score;});});return m>=75;}
function renderBrand(){
  var n=brandName(),els=document.querySelectorAll("[data-brand]");for(var i=0;i<els.length;i++)els[i].textContent=n;
  $("h1Brand").textContent=EN?brand().en:brand().ru;
}
if(/[?&]still=1\b/.test(location.search))document.documentElement.classList.add("still");
var touched=false,IDX=null,EVENTS=[],SEL=null,ACTIVE=null,MARK={},ZONE={},GEO=null;

function $(id){return document.getElementById(id);}
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function safeUrl(u){return /^https?:\/\//i.test(u||"")?u:"#";}
var MON=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function fmtDate(d){var m=/^(\d{4})-(\d{2})-(\d{2})/.exec(d||"");return m?(EN?(+m[3])+" "+MON[+m[2]-1]+" "+m[1]:m[3]+"."+m[2]+"."+m[1]):esc(d||"");}
function fmtUtc(iso){var d=new Date(iso);if(isNaN(d))return "";var p=function(n){return (n<10?"0":"")+n;};return (EN?d.getUTCDate()+" "+MON[d.getUTCMonth()]+" "+d.getUTCFullYear():p(d.getUTCDate())+"."+p(d.getUTCMonth()+1)+"."+d.getUTCFullYear())+" "+p(d.getUTCHours())+":"+p(d.getUTCMinutes())+" UTC";}
function levelOf(v){return v<25?"calm":v<50?"tense":v<75?"crisis":"critical";}
function getJSON(name,rel){
  var urls=LOCAL?["/data/world/"+name]:[RAW+"data/world/"+name,"/data/world/"+name];
  if(rel)urls=[rel];
  var p=Promise.reject(new Error("start"));
  urls.forEach(function(u){p=p.catch(function(){return fetch(u,{cache:"no-cache"}).then(function(r){if(!r.ok)throw new Error(u+" "+r.status);return r.json();});});});
  return p;
}
function regionInfo(r){return IDX&&IDX.regions&&IDX.regions[r]||null;}
function regionVal(r){var i=regionInfo(r);return i&&typeof i.value==="number"?i.value:null;}

/* ---------- карта ---------- */
var map=L.map("map",{zoomSnap:.25,zoomDelta:.5,minZoom:0,maxZoom:10,worldCopyJump:false,maxBounds:[[-85,-180],[85,180]],maxBoundsViscosity:1,zoomControl:false,attributionControl:true});
var WORLD=[[-56,-170],[76,178]];
function coverZoom(){var sz=map.getSize();return Math.ceil(Math.log(Math.max(sz.x,sz.y,200)/256)/Math.LN2*4)/4;}
function fitWorld(anim){var z=coverZoom();map.setMinZoom(z);if(anim)map.flyTo([24,14],z,{duration:.8});else map.setView([24,14],z,{animate:false});}
fitWorld(false);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"© <a href=\"https://www.openstreetmap.org/copyright\" target=\"_blank\" rel=\"noopener\">OpenStreetMap</a>"}).addTo(map);
L.control.zoom({position:"topright"}).addTo(map);
map.createPane("zones").style.zIndex=410;
map.createPane("choke").style.zIndex=450;
var zonesGroup=L.layerGroup().addTo(map),evGroup=L.layerGroup().addTo(map),chokeGroup=L.layerGroup().addTo(map);

function styleFor(f){
  var r=f.properties.r,v=r?regionVal(r):null,sel=SEL&&r===SEL;
  if(!r||v===null)return {fillColor:"#b9b4a6",fillOpacity:r?(sel?.5:.32):.12,color:sel?"#2c2a24":"#7b776b",weight:sel?1.4:.5,opacity:1};
  var c=LEVELS[levelOf(v)][1];
  return {fillColor:c,fillOpacity:sel?.62:.45,color:sel?"#2c2a24":"#5b574c",weight:sel?1.6:.5,opacity:1};
}
function tipFor(layer){
  var p=layer.feature.properties,r=p.r;
  if(!r)return esc(p.n)+" · "+t("outside");
  var v=regionVal(r),info=regionInfo(r);
  if(!IDX)return esc(p.n)+" · "+esc(RNAME[r])+": "+t("noneYet");
  if(v===null)return esc(p.n)+" · "+esc(RNAME[r])+": "+t("low");
  return esc(p.n)+" · "+esc(RNAME[r])+": "+v+" ("+LEVELS[levelOf(v)][0]+")";
}
function loadCountries(){
  return fetch("/lab/world-countries.geojson").then(function(r){if(!r.ok)throw new Error("geojson "+r.status);return r.json();}).then(function(gj){
    GEO=L.geoJSON(gj,{style:styleFor,onEachFeature:function(f,layer){
      layer.bindTooltip(function(l){return tipFor(l);},{sticky:true,direction:"top"});
      layer.on("click",function(){if(f.properties.r){selectRegion(f.properties.r,true);}});
    }}).addTo(map);
    GEO.bringToBack();
    // штриховка для «мало данных»
    var svg=document.querySelector("#map svg");
    if(svg&&!document.getElementById("wl-hatch")){
      var NS="http://www.w3.org/2000/svg",defs=document.createElementNS(NS,"defs"),pat=document.createElementNS(NS,"pattern");
      pat.setAttribute("id","wl-hatch");pat.setAttribute("width","6");pat.setAttribute("height","6");pat.setAttribute("patternUnits","userSpaceOnUse");pat.setAttribute("patternTransform","rotate(45)");
      var rc=document.createElementNS(NS,"rect");rc.setAttribute("width","6");rc.setAttribute("height","6");rc.setAttribute("fill","#d7d3c6");
      var ln=document.createElementNS(NS,"rect");ln.setAttribute("width","2");ln.setAttribute("height","6");ln.setAttribute("fill","#9c978a");
      pat.appendChild(rc);pat.appendChild(ln);defs.appendChild(pat);svg.insertBefore(defs,svg.firstChild);
    }
  });
}
function restyle(){
  if(!GEO)return;
  GEO.setStyle(styleFor);
  GEO.eachLayer(function(l){var r=l.feature.properties.r,nd=!r||regionVal(r)===null;if(l._path)l._path.classList.toggle("c-nodata",nd);});
}

/* узкие места */
function placeChoke(){
chokeGroup.clearLayers();
CHOKE.forEach(function(c){
  var ic=L.divIcon({className:"cp-wrap",html:'<div class="cp'+(chokeHot(c.id)?' hotcp':'')+'"><i></i><span>'+esc(c.n)+'</span></div>',iconSize:[16,16],iconAnchor:[8,8]});
  var m=L.marker(c.ll,{icon:ic,pane:"choke",keyboard:true,title:c.n}).addTo(chokeGroup);
  m.bindTooltip(esc(c.n)+"<br>"+t("influences")+esc(c.r),{direction:"top",offset:[0,-6]});
});
}
placeChoke();

/* события */
function shortTitle(t){var s=String(t||"").split(/\s[—–]\s|:\s|;\s/)[0];return s.length>42?s.slice(0,40).replace(/\s+\S*$/,"")+"…":s;}
function pinHtml(e){
  var st=e.status==="confirmed"?"confirmed":"reported";
  var fresh=isFresh(e);
  var svg='<svg viewBox="0 0 24 24" aria-hidden="true">'+(ICONS[e.type]||ICONS.other)+'</svg>';
  var img=e.photo&&e.photo.url?'<img src="'+esc(safeUrl(e.photo.url))+'" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">':'';
  var head='<div class="pin-head">'+svg+img+'</div>';
  var pul=fresh?'<span class="pulse r1"></span><span class="pulse r2"></span>':'';
  return '<div class="pin '+st+(fresh&&isHot(e)?' hot':'')+'" data-id="'+esc(e.id)+'">'+pul+head+'<span class="pin-lbl">'+esc(shortTitle(e.title))+'</span></div>';
}
/* события: стопки (почти одна точка) раскрываются веером, близкие на экране — в кластер с числом */
var CL_PX=56;
function evUnits(){
  var u=[];
  EVENTS.forEach(function(e){
    var g=null;for(var i=0;i<u.length;i++){if(Math.abs(u[i].lat-e.lat)<.3&&Math.abs(u[i].lon-e.lon)<.3){g=u[i];break;}}
    if(!g){g={lat:e.lat,lon:e.lon,list:[]};u.push(g);}g.list.push(e);
  });
  return u;
}
function pinMarker(e,dx,dy,ll){
  var ic=L.divIcon({className:"ev-wrap",html:pinHtml(e),iconSize:[40,50],iconAnchor:[20-dx,50-dy]});
  var m=L.marker(ll||[e.lat,e.lon],{icon:ic,keyboard:true,title:e.title,riseOnHover:true,zIndexOffset:Math.round(dy)}).addTo(evGroup);
  m.on("click",function(){openCard(e.id,false);});
  MARK[e.id]=m;
}
function clusterMarker(c){
  var n=c.list.length,lat=0,lon=0,hot=false,rep=false,ids=[];
  c.list.forEach(function(e){lat+=e.lat;lon+=e.lon;ids.push(e.id);if(isFresh(e)&&isHot(e))hot=true;if(e.status!=="confirmed")rep=true;});
  lat/=n;lon/=n;
  var sz=n<5?38:n<10?44:50;
  var ic=L.divIcon({className:"ev-wrap",html:'<div class="clu'+(rep?' reported':'')+(hot?' hot':'')+'" data-ids="'+esc(ids.join(" "))+'" style="width:'+sz+'px;height:'+sz+'px">'+(hot?'<span class="pulse r1"></span>':'')+'<b class="num">'+n+'</b></div>',iconSize:[sz,sz],iconAnchor:[sz/2,sz/2]});
  var m=L.marker([lat,lon],{icon:ic,keyboard:true,title:n+" "+(EN?t("ev5"):(n%10>=2&&n%10<=4&&(n%100<10||n%100>=20)?t("ev2"):n%10===1&&n%100!==11?t("ev1"):t("ev5"))),riseOnHover:true,zIndexOffset:500}).addTo(evGroup);
  var tip=c.list.slice(0,5).map(function(e){return "· "+esc(shortTitle(evT(e,"title")));}).join("<br>")+(n>5?"<br>…":"");
  m.bindTooltip(tip,{direction:"top",offset:[0,-sz/2]});
  m.on("click",function(){
    var b=L.latLngBounds(c.list.map(function(e){return [e.lat,e.lon];}));
    map.flyToBounds(b,{padding:[80,80],maxZoom:Math.min(map.getMaxZoom(),Math.max(map.getZoom()+2,6)),duration:.7});
  });
  c.list.forEach(function(e){MARK[e.id]=m;});
}
function drawEvents(){
  if(!EVENTS.length)return;
  evGroup.clearLayers();MARK={};
  var z=map.getZoom(),units=evUnits(),cl=[];
  units.forEach(function(u){
    var p=map.project([u.lat,u.lon],z),g=null;
    for(var i=0;i<cl.length;i++){if(cl[i].p.distanceTo(p)<CL_PX){g=cl[i];break;}}
    if(!g){g={p:p,units:[],list:[]};cl.push(g);}
    g.units.push(u);g.list=g.list.concat(u.list);
  });
  /* на крупном масштабе кластер больше не дробится приближением — раскрываем веером вокруг центра */
  var fanZ=z>=7;
  cl.forEach(function(c){
    if(c.units.length>1&&!fanZ){clusterMarker(c);return;}
    var n=c.list.length,ll=null;
    if(c.units.length>1){var la=0,lo=0;c.list.forEach(function(e){la+=e.lat;lo+=e.lon;});ll=[la/n,lo/n];}
    c.list.forEach(function(e,i){
      var dx=0,dy=0;
      if(n>1){var a=-Math.PI/2+i*2*Math.PI/n,r=n===2?24:Math.max(36,n*8);dx=Math.cos(a)*r;dy=Math.sin(a)*r-(n>2?10:0);}
      pinMarker(e,dx,dy,ll);
    });
  });
  markActive();
}
function placeEvents(){
  zonesGroup.clearLayers();ZONE={};
  EVENTS.forEach(function(e){
    if(e.precision==="zone"&&e.radius_km>0){
      var col=e.status==="confirmed"?"#367866":"#b38b38";
      ZONE[e.id]=L.circle([e.lat,e.lon],{radius:e.radius_km*1000,pane:"zones",color:col,weight:1.2,dashArray:"4 4",fillColor:col,fillOpacity:.1,interactive:false,className:isFresh(e)?"zone-pulse":""}).addTo(zonesGroup);
    }
  });
  drawEvents();
}
map.on("zoomend",drawEvents);
function zoomClasses(){
  var z=map.getZoom(),c=map.getContainer();
  c.classList.toggle("z-labels",z>=6);c.classList.toggle("z-cplabels",z>=3.5);
}
map.on("zoomend",zoomClasses);zoomClasses();

/* тексты событий: EN берёт *_en, иначе русский + пометка */
function evT(e,f){if(EN&&e[f+"_en"])return e[f+"_en"];return e[f];}
function evUntr(e){return EN&&!(e.title_en&&e.summary_en);}

/* карточка */
function openCard(id,fly){
  var e=null;for(var i=0;i<EVENTS.length;i++){if(EVENTS[i].id===id){e=EVENTS[i];break;}}
  if(!e)return;
  ACTIVE=id;
  var st=e.status==="confirmed"?["confirmed",t("confirmed")]:["reported",t("reported")];
  var h='<div class="card-head"><span>'+esc(RNAME[e.region]||e.region)+' · '+fmtDate(e.occurred_at)+'</span><button class="card-close" type="button" id="cardClose">'+t("close")+'</button></div><div class="card-body">';
  h+='<span class="badge '+st[0]+'">'+st[1]+'</span><h3'+(evUntr(e)?' lang="ru"':'')+'>'+esc(evT(e,"title"))+'</h3>'+(evUntr(e)?'<p class="note">'+esc(t("untr"))+'</p>':'')+'<p'+(evUntr(e)?' lang="ru"':'')+'>'+esc(evT(e,"summary"))+'</p>';
  if(e.fuel_effect)h+='<h4>'+t("effFuel")+'</h4><p class="eff"'+(EN&&!e.fuel_effect_en?' lang="ru"':'')+'>'+esc(evT(e,"fuel_effect"))+'</p>';
  if(e.index_effect&&(!EN||e.index_effect_en))h+='<h4>'+t("effIdx")+'</h4><p class="eff">'+esc(EN?e.index_effect_en:e.index_effect)+'</p>';
  if(e.photo&&e.photo.url){
    h+='<figure><img src="'+esc(safeUrl(e.photo.url))+'" alt="'+t("photoAlt")+'" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display=\'none\'"><figcaption>'+t("license")+': '+esc(e.photo.license||t("notSet"))+' · '+t("author")+': '+esc(e.photo.author||t("authorNone"))+(e.photo.page?' · <a href="'+esc(safeUrl(e.photo.page))+'" target="_blank" rel="noopener">'+t("filePage")+'</a>':'')+'</figcaption></figure>';
  }
  if(e.sources&&e.sources.length){
    h+='<h4>'+t("sources")+'</h4><ul>';
    e.sources.forEach(function(s){h+='<li><a href="'+esc(safeUrl(s.url))+'" target="_blank" rel="noopener">'+esc(s.publisher||s.url)+'</a>'+(s.date?' <span class="num" style="color:var(--muted);font-size:11px">· '+fmtDate(s.date)+'</span>':'')+'</li>';});
    h+='</ul>';
  }
  h+='<p class="note">'+t("prec")+': '+(e.precision==="zone"?t("zone",{r:esc(e.radius_km)}):t("point"))+'. '+t("est")+'.</p></div>';
  var card=$("card");card.innerHTML=h;card.hidden=false;card.scrollTop=0;
  $("cardClose").addEventListener("click",closeCard);
  markActive();
  if(fly){map.flyTo([e.lat,e.lon],Math.max(map.getZoom(),e.precision==="zone"?5:5.5),{duration:.8});}
}
function closeCard(){ACTIVE=null;$("card").hidden=true;markActive();}
function markActive(){
  var cs=document.querySelectorAll(".clu");for(var k=0;k<cs.length;k++){cs[k].classList.toggle("active",!!ACTIVE&&(" "+cs[k].getAttribute("data-ids")+" ").indexOf(" "+ACTIVE+" ")>=0);}
  var ps=document.querySelectorAll(".pin");for(var i=0;i<ps.length;i++){ps[i].classList.toggle("active",ps[i].getAttribute("data-id")===ACTIVE);}
  var ts=document.querySelectorAll(".t-item");for(var j=0;j<ts.length;j++){ts[j].classList.toggle("active",ts[j].getAttribute("data-id")===ACTIVE);}
}
document.addEventListener("keydown",function(ev){if(ev.key==="Escape"&&ACTIVE)closeCard();});
map.on("click",function(){/* клик по пустой карте карточку не закрывает: только кнопка/Esc */});

/* хроника */
function renderTimeline(){
  var list=EVENTS.slice().sort(function(a,b){return a.occurred_at<b.occurred_at?1:a.occurred_at>b.occurred_at?-1:(a.id<b.id?1:-1);});
  $("chronCount").textContent=list.length+" "+(EN?(list.length===1?t("ev1"):t("ev5")):(list.length%10===1&&list.length%100!==11?t("ev1"):(list.length%10>=2&&list.length%10<=4&&(list.length%100<10||list.length%100>=20)?t("ev2"):t("ev5"))));
  var h="";
  list.forEach(function(e){var fr=isFresh(e);h+='<button type="button" class="t-item '+(e.status==="confirmed"?"":"reported")+(fr?" fresh"+(isHot(e)?" hot":""):"")+'" data-id="'+esc(e.id)+'"><span class="t-meta">'+esc(RNAME[e.region]||e.region)+' · '+fmtDate(e.occurred_at)+'</span><strong'+(evUntr(e)?' lang="ru"':'')+'>'+esc(evT(e,"title"))+'</strong></button>';});
  $("timeline").innerHTML=h||'<p class="rail-intro">'+t("noEv")+'</p>';
  var items=$("timeline").querySelectorAll(".t-item");
  for(var i=0;i<items.length;i++){items[i].addEventListener("click",function(ev){
    var id=ev.currentTarget.getAttribute("data-id");openCard(id,true);
    if(window.matchMedia("(max-width:760px)").matches){$("map").scrollIntoView({block:"start",behavior:"smooth"});}
  });}
  markActive();
}

/* баннер «сейчас» */
var nowTimer=null,nowI=0,NOWLIST=[];
function renderNow(){
  NOWLIST=EVENTS.filter(isFresh).sort(function(a,b){return a.occurred_at<b.occurred_at?1:-1;});
  var b=$("nowBanner"),st=$("stage");
  clearInterval(nowTimer);
  if(!NOWLIST.length){b.hidden=true;st.classList.remove("has-now");return;}
  b.hidden=false;st.classList.add("has-now");nowI=0;showNow();
  if(NOWLIST.length>1&&!(window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches))nowTimer=setInterval(function(){
    var t=$("nowTxt");t.classList.add("out");setTimeout(function(){nowI=(nowI+1)%NOWLIST.length;showNow();t.classList.remove("out");},400);},6000);
  setTimeout(function(){map.invalidateSize();},50);
}
function showNow(){var e=NOWLIST[nowI];$("nowTxt").textContent=(RNAME[e.region]||e.region)+" · "+evT(e,"title");$("nowN").textContent=NOWLIST.length>1?(nowI+1)+"/"+NOWLIST.length:"";}
$("nowBanner").addEventListener("click",function(){var e=NOWLIST[nowI];if(e)openCard(e.id,true);});

/* индикатор и панели */
function renderSelect(){
  var h='<option value="">'+t("allWorld")+''+(IDX&&IDX.world&&typeof IDX.world.value==="number"?" · "+IDX.world.value:"")+'</option>';
  REGIONS.forEach(function(r){var v=regionVal(r[0]);h+='<option value="'+r[0]+'"'+(SEL===r[0]?" selected":"")+'>'+esc(r[1])+(IDX?" · "+(v===null?t("low"):v):"")+'</option>';});
  $("regionSelect").innerHTML=h;
}
function setNeedle(v){
  var n=$("needle");
  if(v===null){n.setAttribute("visibility","hidden");return;}
  var a=Math.PI*(1-v/100),cx=125,cy=120,r1=80,r2=112;
  n.setAttribute("d","M"+(cx+r1*Math.cos(a)).toFixed(1)+" "+(cy-r1*Math.sin(a)).toFixed(1)+"L"+(cx+r2*Math.cos(a)).toFixed(1)+" "+(cy-r2*Math.sin(a)).toFixed(1));
  n.setAttribute("visibility","visible");
}
function renderGauge(){
  var src=null,title=t("world");
  if(IDX){src=SEL?regionInfo(SEL):IDX.world;title=SEL?(RNAME[SEL]||SEL):t("world");}
  $("gaugeTitle").textContent=title;
  $("noIdx").hidden=!!IDX;
  var v=src&&typeof src.value==="number"?src.value:null;
  $("gaugeNum").firstChild.nodeValue=v===null?"—":String(v);
  $("gaugeCap").textContent=v===null?(IDX?t("low"):t("nodata")):t("of100");
  setNeedle(v);
  var dot=document.querySelector("#gaugeStatus .status-dot"),lv=v===null?null:levelOf(v);
  var d=src&&typeof src.delta_1d==="number"?src.delta_1d:null;
  $("gaugeStatus").innerHTML='<span class="status-dot" style="background:'+(lv?LEVELS[lv][1]:"#9a968a")+'"></span>'+(lv?LEVELS[lv][0]:(IDX?t("low"):t("nodata")))+(d!==null&&v!==null?'<span class="delta '+(d>0?"up":d<0?"down":"")+'">'+(d>0?"+":"")+d+' '+t("perDay")+'</span>':'');
  var m="";
  if(src&&typeof src.coverage==="number")m+=t("cover")+' <b>'+Math.round(src.coverage*100)+'%</b><br>';
  if(IDX&&IDX.generated_at)m+=t("calc")+' <b>'+fmtUtc(IDX.generated_at)+'</b><br>';
  if(IDX&&IDX.methodology_version)m+=t("meth")+' <b>v'+esc(IDX.methodology_version)+'</b>';
  $("gaugeMeta").innerHTML=m;
}
function renderComps(){
  var title=SEL?t("comps")+" · "+(RNAME[SEL]||SEL):t("compsPick");
  $("compTitle").textContent=title;
  var box=$("compList");
  if(!IDX){box.innerHTML='<p class="note">'+t("computing")+'</p>';return;}
  if(!SEL){box.innerHTML='<p class="note">'+t("compsHint")+'</p>';return;}
  var info=regionInfo(SEL);if(!info){box.innerHTML='<p class="note">'+t("noReg")+'</p>';return;}
  var have={};(info.components||[]).forEach(function(c){have[c.id]=c;});
  var h="";
  COMPS.forEach(function(b){
    var c=have[b[0]];
    if(c&&typeof c.score==="number"){
      var w=Math.round((typeof c.weight==="number"?c.weight:b[2]/100)*100),col=LEVELS[levelOf(c.score)][1];
      h+='<div class="comp-row"><div class="comp-top"><strong>'+esc(EN?b[1]:(c.label||b[1]))+'</strong><span class="num">'+Math.round(c.score)+' × '+w+'%</span></div><div class="comp-bar"><span style="width:'+Math.max(2,Math.min(100,c.score))+'%;background:'+col+'"></span></div><div class="comp-sub"><span>'+(EN?esc(c.raw_en||[c.source,c.as_of].filter(Boolean).join(" · ")):esc(c.raw||""))+'</span><span>'+t("contrib")+' '+(c.score*(c.weight||b[2]/100)).toFixed(1)+'</span></div></div>';
    }else{
      h+='<div class="comp-row comp-miss"><div class="comp-top"><strong>'+esc(b[1])+'</strong><span>'+t("nodata")+'</span></div><div class="comp-bar"></div><div class="comp-sub"><span>'+t("wNoRedist",{w:b[2]})+'</span></div></div>';
    }
  });
  box.innerHTML=h;
}
function renderAll(){renderBrand();placeChoke();renderSelect();renderGauge();renderComps();restyle();
  var ht=IDX&&IDX.generated_at?t("slice")+fmtUtc(IDX.generated_at):t("idxNone");$("headTime").textContent=ht;
  $("methodVer").textContent=IDX&&IDX.methodology_version?t("methVer")+IDX.methodology_version:"";}
function selectRegion(r,fit){
  if(fit)touched=true;
  SEL=r||null;renderSelect();renderGauge();renderComps();restyle();
  if(fit){if(SEL&&RBOUNDS[SEL])map.flyToBounds(RBOUNDS[SEL],{padding:[10,10],duration:.8});else if(!SEL)fitWorld(true);}
}
$("regionSelect").addEventListener("change",function(){selectRegion(this.value,true);});
$("resetMap").addEventListener("click",function(){selectRegion(null,true);});
$("tCountries").addEventListener("change",function(){if(!GEO)return;if(this.checked)GEO.addTo(map);else map.removeLayer(GEO);if(this.checked)GEO.bringToBack();});
$("tZones").addEventListener("change",function(){if(this.checked)zonesGroup.addTo(map);else map.removeLayer(zonesGroup);});
function openMethod(ev){ev.preventDefault();var d=$("method");d.open=true;d.scrollIntoView({behavior:"smooth",block:"start"});}
$("methodTop").addEventListener("click",openMethod);$("methodLink").addEventListener("click",openMethod);
if(location.hash==="#method")$("method").open=true;

/* ---------- загрузка ---------- */
var msg=$("mapMsg");
if(DEMO)$("demoBanner").hidden=false;
renderAll();renderTimeline();
loadCountries().then(restyle).catch(function(e){msg.textContent=t("geoFail");console.warn(e);});
getJSON("events.json").then(function(d){EVENTS=(d&&d.events)||[];placeEvents();renderTimeline();renderNow();}).catch(function(e){$("timeline").innerHTML='<p class="rail-intro">'+t("evFail")+'</p>';console.warn(e);});
(DEMO?getJSON("index.json","/lab/fixtures/index-demo.json"):getJSON("index.json")).then(function(d){IDX=d;renderAll();}).catch(function(e){IDX=null;renderAll();console.info("index.json пока нет:",e&&e.message);});
map.getContainer().addEventListener("pointerdown",function(){touched=true;},{passive:true});
function relayout(){map.invalidateSize();if(!touched)fitWorld(false);else map.setMinZoom(coverZoom());}
window.addEventListener("load",relayout);
window.addEventListener("resize",relayout);
if(window.ResizeObserver){new ResizeObserver(relayout).observe(map.getContainer());}
})();
