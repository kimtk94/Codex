const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=v=>Number.isFinite(Number(v))?(Number(v)*100).toFixed(1)+'%':'—';
const num=(v,d=2)=>Number.isFinite(Number(v))?Number(v).toFixed(d):'—';
const time=v=>v?new Date(v).toLocaleString('ko-KR'):'—';

async function load(){
  try{
    const r=await fetch('/api/shadow',{cache:'no-store'});
    const j=await r.json();
    if(!r.ok) throw new Error(j?.error||('HTTP '+r.status));
    $('#status').innerHTML='상태 <b>'+esc(j.status)+'</b> · 추적 '+esc(j.tracking_status||'—')+' · 갱신 '+esc(time(j.updated_at));
    const sig=j.signals||{};
    $('#signals').innerHTML=['US','KR','BTC'].map(m=>{
      const s=sig[m]||{};
      return '<div class="card"><div class="row"><b>'+m+'</b><span class="pill">'+esc(s.signal||'—')+'</span></div>'+
        '<div class="kpi">'+esc(s.symbol||'—')+'</div>'+
        '<div class="row"><span class="muted">Model</span><b>'+esc(s.model_family||'—')+'</b></div>'+
        '<div class="row"><span class="muted">Probability</span><b>'+pct(s.probability)+'</b></div>'+
        '<div class="row"><span class="muted">Missing</span><b>'+pct(s.missing_feature_ratio)+'</b></div>'+
        '<div class="row"><span class="muted">As of</span><b>'+esc(time(s.as_of))+'</b></div></div>';
    }).join('');
    const rows=j.forward_ranking||[];
    $('#ranking').innerHTML='<h2>A/B/C Forward Ranking</h2>'+
      (rows.length?rows.map((x,i)=>'<div class="row"><span>#'+(x.forward_rank==null?i+1:x.forward_rank+1)+' '+esc(x.strategy||'—')+'</span><b>Sharpe '+num(x.sharpe)+' · Return '+pct(x.total_return)+' · MDD '+pct(x.max_drawdown)+'</b></div>').join(''):'<div class="muted">아직 ranking 데이터가 없습니다.</div>');
  }catch(e){
    $('#status').innerHTML='<div class="err">불러오기 실패: '+esc(e.message)+'</div>';
  }
}
load();
setInterval(load,60000);
