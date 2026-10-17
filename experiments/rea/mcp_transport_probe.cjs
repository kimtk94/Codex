// Probe REA MCP stdio without modifying Codex or server configuration.
const { spawn } = require('node:child_process');
const child = spawn('npx', ['--yes', 'rea-agents@6.5.0', '--mcp'], {
  stdio: ['pipe', 'pipe', 'pipe'],
  env: { ...process.env, npm_config_update_notifier: 'false' }
});
let stdout='', stderr='', done=false;
const fixture = process.env.REA_FIXTURE_PATH;
let analysisTool = null;
const stop = (error) => {
  if (done) return;
  done = true;
  child.kill('SIGTERM');
  if (error) { console.error(error); process.exitCode=1; }
};
const timer = setTimeout(()=>stop('REA_MCP_TIMEOUT'),45000);
const send = (value) => child.stdin.write(JSON.stringify(value)+'\n');
child.stdout.on('data', chunk=>{
  stdout+=chunk.toString();
  let idx;
  while((idx=stdout.indexOf('\n'))>=0) {
    const line=stdout.slice(0,idx).trim(); stdout=stdout.slice(idx+1);
    if(!line) continue;
    let message; try {message=JSON.parse(line)} catch {stop('REA_MCP_NON_JSON_STDOUT');return}
    if(message.id===1){
      if(message.error) return stop('REA_MCP_INIT_ERROR='+JSON.stringify(message.error));
      if(!message.result?.protocolVersion) return stop('REA_MCP_NO_PROTOCOL_VERSION');
      console.log('REA_MCP_INITIALIZED='+message.result.protocolVersion);
      send({jsonrpc:'2.0',method:'notifications/initialized'});
      send({jsonrpc:'2.0',id:2,method:'tools/list',params:{}});
    } else if(message.id===2) {
      if(message.error) return stop('REA_MCP_TOOLS_ERROR='+JSON.stringify(message.error));
      if(!Array.isArray(message.result?.tools)) return stop('REA_MCP_TOOLS_INVALID');
      console.log('REA_MCP_TOOL_COUNT='+message.result.tools.length);
      console.log('REA_MCP_TOOL_NAMES='+message.result.tools.map(t=>t.name).join(','));
      if(!message.result.tools.length) return stop('REA_MCP_NO_TOOLS');
      console.log('REA_MCP_TRANSPORT_PASS=true');
      analysisTool=message.result.tools.find(t=>t.name==='analyze_javascript_application');
      if(!fixture || !analysisTool){clearTimeout(timer);stop();return;}
      const schema=analysisTool.inputSchema || {};
      console.log('REA_ANALYZE_SCHEMA='+JSON.stringify(schema).slice(0,1800));
      const props=schema.properties||{};
      const required=schema.required||[];
      const candidate=['input_path','path','application_path','target_path','root_path','directory','artifact_path'].find(k=>k in props);
      console.log('REA_ANALYZE_REQUIRED='+JSON.stringify(required));
      if(!candidate || required.some(k=>k!==candidate)) {clearTimeout(timer);stop('REA_MCP_TOOL_SCHEMA_REQUIRES_REVIEW');return;}
      send({jsonrpc:'2.0',id:3,method:'tools/call',params:{name:analysisTool.name,arguments:{[candidate]:fixture}}});
    } else if(message.id===3){
      if(message.error || message.result?.isError) return stop('REA_MCP_TOOL_CALL_FAILED='+JSON.stringify(message.error||message.result).slice(0,1200));
      if(!Array.isArray(message.result?.content)||!message.result.content.length) return stop('REA_MCP_TOOL_RESULT_EMPTY');
      console.log('REA_MCP_TOOL_CALL_PASS=true');clearTimeout(timer);stop();
    }
  }
});
child.stderr.on('data',v=>{stderr+=v.toString();});
child.on('error',e=>{clearTimeout(timer);stop('REA_MCP_SPAWN_ERROR='+e.message)});
child.on('exit',(code)=>{ if(!done) {clearTimeout(timer);stop('REA_MCP_EARLY_EXIT='+code+' '+stderr.slice(-500))}});
send({jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'rea-ci-probe',version:'1.0'}}});
