'use strict';

// Read-only operation console data contract. A CI "SUCCESS" is not business
// acceptance, a CRM write, a customer email send or an authenticated E2E test.
const RUN_URL=/^https:\/\/github\.com\/kimtk94\/Codex\/actions\/runs\/[0-9]+$/;

function compact(row, i){return String(row?.[i]??'').trim();}
function projectAutomationConsole(progressRows, trackRows, healthRows, workflowRows){
  const result={
    source:'SFDC_Automation_Followup_2026',
    readOnly:true,
    progress:{available:false,total:0,done:0,partial:0,todo:0,accepted:0,
      baselineOnly:true,sourceNote:'Automation Master Progress is a baseline; no formal acceptance assumed'},
    tracks:{available:false,items:[]},
    workflows:{available:false,items:[]},
    issues:[]
  };
  if(progressRows?.[0]?.[0]==='Task ID'){
    const ids=new Set(), counters={done:0,partial:0,todo:0},areas=new Map();
    for(const row of progressRows.slice(1)){
      const id=compact(row,0);
      if(!id)continue;
      if(!/^A\d{2}$/.test(id)||ids.has(id))throw Error('PROGRESS_TASK_ID_INVALID');
      ids.add(id);
      const area=compact(row,1)||'Other',status=compact(row,3).toLowerCase();
      if(!(status in counters))throw Error('PROGRESS_STATUS_INVALID');
      counters[status]++;
      const entry=areas.get(area)||{name:area,done:0,partial:0,todo:0};
      entry[status]++;
      areas.set(area,entry);
      if(compact(row,4)==='VERIFIED_ACCEPTED')result.progress.accepted++;
    }
    if(ids.size && ids.size===50){
      Object.assign(result.progress,{available:true,total:ids.size,
        done:counters.done,partial:counters.partial,todo:counters.todo,
        areas:[...areas.values()]});
    }else{
      result.progress.accepted=0;
      result.issues.push('MASTER_PROGRESS_INCOMPLETE');
    }
  }else{
    result.issues.push('MASTER_PROGRESS_UNAVAILABLE');
  }
  if(trackRows?.[0]?.[0]==='Track'&&compact(trackRows[0],1)==='Result'){
    const tracks=[], seen=new Set();
    for(const row of trackRows.slice(1,5)){
      const name=compact(row,0),status=compact(row,1).toUpperCase();
      if(!name)continue;
      if(seen.has(name)||!['SUCCESS','FAILURE','SKIPPED','CANCELLED'].includes(status))
        throw Error('TRACK_STATUS_INVALID');
      seen.add(name);
      const candidate=compact(row,3);
      tracks.push({
        name,result:status,checked:compact(row,2),
        runUrl:RUN_URL.test(candidate)?candidate:null,
        scope:compact(row,4),boundary:compact(row,5)
      });
    }
    if(tracks.length===4)Object.assign(result.tracks,{available:true,items:tracks});
    else result.issues.push('PARALLEL_TRACK_STATUS_INCOMPLETE');
  }else{
    result.issues.push('PARALLEL_TRACK_STATUS_UNAVAILABLE');
  }
  if(workflowRows?.[0]?.[0]==='Workflow' && compact(workflowRows[0],2)==='Run State'){
    const states=new Set(['PASS_EXECUTION_ONLY','FAILED','STALE','IN_PROGRESS',
                          'NOT_RUN','CANCELLED','SKIPPED','UNVERIFIED','BLOCKED']);
    const seen=new Set(),items=[];
    for(const row of workflowRows.slice(1)){
      const name=compact(row,0),state=compact(row,2);
      if(!name)continue;
      if(seen.has(name)||!states.has(state))throw Error('WORKFLOW_RUN_SCHEMA_INVALID');
      seen.add(name);
      const raw=compact(row,5);
      items.push({
        name,domain:compact(row,1),state,updated:compact(row,3),
        ageHours:compact(row,4),runUrl:RUN_URL.test(raw)?raw:null,
        checked:compact(row,7),scope:compact(row,8)
      });
      if(state!=='PASS_EXECUTION_ONLY')result.issues.push('GITHUB_WORKFLOW: '+name+' — '+state);
    }
    if(items.length===12)result.workflows={available:true,items};
    else result.issues.push('GITHUB_WORKFLOW_HEALTH_INCOMPLETE');
  }else{
    result.issues.push('GITHUB_WORKFLOW_HEALTH_UNAVAILABLE');
  }
  const selected=new Set(['Revenue Lifecycle','Feishu','SFDC Email Decision Sync',
    'SFDC 3-Report Email Ingest','Lead My Sent Audit','Tax Invoice Due Watch',
    'Parallel Audit D — Web','SFDC Quote']);
  result.health=(healthRows||[]).slice(1).filter(r=>selected.has(compact(r,0)))
    .map(r=>({name:compact(r,0),status:compact(r,2),updated:compact(r,1)}));
  for(const row of result.health){
    if(/FAIL|BLOCK|REVIEW|PARTIAL|NOT_PROMOTED|OFFLINE_ONLY/i.test(row.status))
      result.issues.push(row.name+': '+row.status);
  }
  if(result.tracks.available && result.tracks.items.some(t=>t.result!=='SUCCESS'))
    result.issues.push('PARALLEL_TRACKS_NOT_ALL_SUCCESSFUL');
  return result;
}
module.exports={projectAutomationConsole,RUN_URL};
