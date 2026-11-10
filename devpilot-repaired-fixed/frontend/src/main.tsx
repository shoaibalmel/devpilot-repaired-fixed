import React, {useEffect, useMemo, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {
  Activity, Bot, Cloud, Upload, Plus, Folder, FileText, Image as ImageIcon,
  Trash2, Download, RefreshCw, Rocket, AlertTriangle, CheckCircle2,
  Terminal, Search, ChevronRight, X, Sparkles, Server, HardDrive, Menu, GitBranch
} from 'lucide-react';
import './styles.css';

const API=(import.meta as any).env?.VITE_API_BASE_URL || 'http://127.0.0.1:8765';

async function api(path:string, options:any={}) {
  const r=await fetch(API+path,options);
  const body=await r.json().catch(()=>({detail:r.statusText}));
  if(!r.ok) throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail||body));
  return body;
}

function App(){
  const [page,setPage]=useState('Dashboard');
  const [mobile,setMobile]=useState(false);
  const [aws,setAws]=useState<any>(null);
  useEffect(()=>{api('/api/aws/health').then(setAws).catch(e=>setAws({connected:false,message:e.message}));},[]);
  const nav=[
    ['Dashboard',Activity],['AI Agent',Bot],['GitHub Repositories',GitBranch],['Deployments',Rocket],['Incidents',AlertTriangle],['Cloud Storage',Cloud]
  ];
  return <div className="app">
    <aside className={'sidebar '+(mobile?'open':'')}>
      <div className="brand"><div className="brandIcon"><Sparkles size={20}/></div><div><b>DevPilot</b><span>Agentic DevOps</span></div></div>
      <div className="navLabel">WORKSPACE</div>
      {nav.map(([name,Icon]:any)=><button className={'navItem '+(page===name?'active':'')} onClick={()=>{setPage(name);setMobile(false)}} key={name}><Icon size={18}/><span>{name}</span></button>)}
      <div className="sidebarBottom"><div className="miniStatus"><span className="pulse"></span><div><b>System online</b><small>All services operational</small></div></div></div>
    </aside>
    <main className="main">
      <header className="topbar"><button className="menuBtn" onClick={()=>setMobile(!mobile)}><Menu/></button><div><div className="eyebrow">DEVOPS CONTROL CENTER</div><h1>{page}</h1></div><div className="topActions"><div className="live"><span className="pulse"></span>{aws?.connected?'AWS connected':'AWS not verified'}</div></div></header>
      <div className="content">{page==='Dashboard'?<Dashboard setPage={setPage}/>:page==='AI Agent'?<Agent/>:page==='GitHub Repositories'?<GitHubRepos/>:page==='Deployments'?<Deployments/>:page==='Incidents'?<Incidents/>:<Storage/>}</div>
    </main>
  </div>
}

function Stat({icon:Icon,label,value,sub,kind}:any){return <div className="stat"><div className={'statIcon '+kind}><Icon size={19}/></div><div><small>{label}</small><strong>{value}</strong><span>{sub}</span></div></div>}

function Dashboard({setPage}:any){
 const [health,setHealth]=useState<any>(null); const [storage,setStorage]=useState<any>(null); const [deploys,setDeploys]=useState<any[]>([]); const [incidents,setIncidents]=useState<any[]>([]); const [error,setError]=useState('');
 useEffect(()=>{Promise.all([api('/api/health'),api('/api/storage/summary'),api('/api/deployments'),api('/api/incidents')]).then(([h,s,d,i])=>{setHealth(h);setStorage(s);setDeploys(d);setIncidents(i)}).catch(e=>setError(e.message))},[]);
 return <div>
  <section className="hero"><div><div className="tag"><Sparkles size={14}/> AI-powered operations</div><h2>Ship faster. <em>Recover smarter.</em></h2><p>One workspace for deployments, cloud files, health checks and incident assistance.</p><button className="primary" onClick={()=>setPage('AI Agent')}><Bot size={17}/> Ask the DevOps Agent</button></div><div className="heroOrb"><div className="orb"><Cloud size={38}/></div></div></section>
  {error&&<div className="infoBox">Backend error: {error}</div>}<div className="stats"><Stat icon={Activity} label="System health" value={health?.status==='healthy'?'Healthy':'Checking'} sub="API responding normally" kind="green"/><Stat icon={Rocket} label="Deployments" value={deploys.length} sub="Tracked releases" kind="blue"/><Stat icon={AlertTriangle} label="Incidents" value={incidents.length} sub="Recorded incidents" kind="amber"/><Stat icon={HardDrive} label="Cloud objects" value={storage?.objects??0} sub={storage?.mode==='s3'?'Amazon S3':'Local mode'} kind="violet"/></div>
  <div className="grid2"><div className="panel"><div className="panelHead"><div><h3>Quick actions</h3><p>Jump into common workflows</p></div></div><div className="quickGrid"><button onClick={()=>setPage('AI Agent')}><Bot/><b>Ask Agent</b><span>Run a DevOps request</span></button><button onClick={()=>setPage('Deployments')}><Rocket/><b>New Deployment</b><span>Start a controlled release</span></button><button onClick={()=>setPage('Cloud Storage')}><Upload/><b>Upload to Cloud</b><span>Files, images or folders</span></button><button onClick={()=>setPage('Incidents')}><AlertTriangle/><b>Investigate</b><span>Review incidents & evidence</span></button></div></div>
  <div className="panel"><div className="panelHead"><div><h3>Deployment flow</h3><p>Controlled release pipeline</p></div><span className="chip green">Ready</span></div><div className="pipeline">{['Git','Build','Test','Docker','AWS','Health'].map((x,i)=><React.Fragment key={x}><div className="pipe"><div className="pipeDot">{i+1}</div><span>{x}</span></div>{i<5&&<ChevronRight className="pipeArrow" size={15}/>}</React.Fragment>)}</div><div className="infoBox"><CheckCircle2 size={17}/><span>Risky cloud actions can be protected by approval gates.</span></div></div></div>
 </div>
}

function Agent(){
 const [q,setQ]=useState(''); const [result,setResult]=useState<any>(null); const [loading,setLoading]=useState(false);
 const [error,setError]=useState(''); const ask=async()=>{if(!q.trim())return;setLoading(true);setError('');try{setResult(await api('/api/agent',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request:q})}))}catch(e:any){setError(e.message)}finally{setLoading(false)}};
 return <div className="agentPage"><section className="agentHero"><div className="agentBadge"><Bot size={22}/></div><div><h2>DevOps Agent</h2><p>Describe what you want in plain English. The agent routes your request to the right tool.</p></div></section>
 <div className="agentBox"><div className="agentPrompt"><textarea value={q} onChange={e=>setQ(e.target.value)} placeholder="Try: Check application health, analyze the latest incident, or show cloud storage..." onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask()}}}/><button className="primary" onClick={ask} disabled={loading}>{loading?<RefreshCw className="spin"/>:<Sparkles/>}{loading?'Thinkingâ€¦':'Run agent'}</button></div><div className="suggestions">{['Check application health','Deploy the latest version','Analyze the latest incident','Show my cloud storage'].map(x=><button onClick={()=>setQ(x)} key={x}>{x}</button>)}</div></div>
 {error&&<div className="infoBox">{error}</div>}{result&&<div className="resultCard"><div className="resultTop"><span className="chip blue">{result.intent}</span><span className={'chip '+(result.executed?'green':'amber')}>{result.executed?'Tool executed':'Plan only â€” not executed'}</span></div><h3>{result.message}</h3><div className="resultMeta"><span><Terminal size={14}/> {result.tool}</span><span>Action #{result.action_id}</span></div></div>}
 </div>
}


function GitHubRepos(){
 const [username,setUsername]=useState('');
 const [repos,setRepos]=useState<any[]>([]);
 const [selected,setSelected]=useState<string[]>([]);
 const [status,setStatus]=useState<any>(null);
 const [result,setResult]=useState<any>(null);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const loadStatus=()=>api('/api/github/status').then(setStatus).catch(e=>setError(e.message));
 useEffect(()=>{loadStatus()},[]);
 const discover=async()=>{
  if(!username.trim()){setError('Enter your GitHub username first.');return;}
  setBusy(true);setError('');setResult(null);
  try{const r=await api('/api/github/repos?username='+encodeURIComponent(username.trim()));setRepos(r.repositories||[]);setSelected((r.repositories||[]).map((x:any)=>x.full_name));}
  catch(e:any){setError(e.message)}finally{setBusy(false)}
 };
 const sync=async(all=false)=>{
  if(!username.trim()){setError('Enter your GitHub username first.');return;}
  if(!repos.length){setError('Load your GitHub repositories first.');return;}
  const names=all?repos.map(x=>x.full_name):selected;
  if(!names.length){setError('Select at least one repository.');return;}
  setBusy(true);setError('');setResult(null);
  try{const r=await api('/api/github/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,repositories:names})});setResult(r);await loadStatus();}
  catch(e:any){setError(e.message)}finally{setBusy(false)}
 };
 const toggle=(name:string)=>setSelected(old=>old.includes(name)?old.filter(x=>x!==name):[...old,name]);
 return <div>
  <div className="pageIntro"><div><h2>GitHub Repository Manager</h2><p>Discover GitHub repositories and clone them into DevPilot's persistent Docker-mounted workspace.</p></div><span className="chip blue">Local Docker workspace</span></div>
  <div className="panel" style={{padding:22,marginBottom:18}}>
   <h3><GitBranch size={19} style={{verticalAlign:'middle',marginRight:8}}/>Connect GitHub</h3>
   <p>Enter your GitHub username to discover repositories. Public repositories work without a token. Private repositories require a read-only GitHub token configured on the backend.</p>
   <label>GitHub username<input value={username} onChange={e=>setUsername(e.target.value)} placeholder="your-github-username"/></label>
   <div className="buttonRow" style={{marginTop:14}}><button className="primary" type="button" onClick={discover} disabled={busy}>{busy?'Loadingâ€¦':'Fetch repositories'}</button><button className="secondary" type="button" onClick={()=>{setRepos([]);setSelected([]);setResult(null);setError('')}}>Clear</button></div>
   {status&&<div className="infoBox" style={{marginTop:14}}>Git: {status.git_available?'Available':'Not installed'} Â· Backend token: {status.github_token_configured?'Configured':'Not configured (public repositories only)'} Â· Docker workspace currently contains {status.repository_count} cloned repository/repositories.</div>}
  </div>
  {error&&<div className="infoBox" role="alert">{error}</div>}
  {repos.length>0&&<div className="panel tablePanel" style={{marginBottom:18}}>
   <div className="panelHead"><div><h3>Repositories ({repos.length})</h3><p>{selected.length} selected. Private repository access depends on token permissions.</p></div><div className="buttonRow"><button className="secondary small" type="button" onClick={()=>setSelected(repos.map(x=>x.full_name))}>Select all</button><button className="secondary small" type="button" onClick={()=>setSelected([])}>Clear selection</button></div></div>
   <table><thead><tr><th>Select</th><th>Repository</th><th>Visibility</th><th>Default branch</th><th>Updated</th></tr></thead><tbody>{repos.map(r=><tr key={r.id}><td><input type="checkbox" checked={selected.includes(r.full_name)} onChange={()=>toggle(r.full_name)}/></td><td><a href={r.html_url} target="_blank" rel="noreferrer">{r.full_name}</a>{r.description&&<small>{r.description}</small>}</td><td>{r.private?'Private':'Public'}</td><td>{r.default_branch}</td><td>{r.updated_at?new Date(r.updated_at).toLocaleDateString():'â€”'}</td></tr>)}</tbody></table>
   <div className="buttonRow" style={{padding:18}}><button className="primary" type="button" disabled={busy} onClick={()=>sync(true)}>{busy?'Syncingâ€¦':'Clone / update ALL repositories'}</button><button className="secondary" type="button" disabled={busy||!selected.length} onClick={()=>sync(false)}>Sync selected ({selected.length})</button></div>
  </div>}
  {result&&<div className="panel" style={{padding:20,marginBottom:18}}><h3>Repository sync result</h3><div className="stats"><Stat icon={GitBranch} label="Discovered" value={result.total} sub="Selected repositories" kind="blue"/><Stat icon={CheckCircle2} label="Cloned" value={result.cloned} sub="New local copies" kind="green"/><Stat icon={RefreshCw} label="Updated" value={result.updated} sub="Existing repositories" kind="violet"/><Stat icon={AlertTriangle} label="Failed" value={result.failed} sub="Require attention" kind="amber"/></div><p>Workspace: <code>{result.workspace}</code></p>{result.results?.map((r:any)=><div className="infoBox" key={r.full_name}>{r.full_name}: {r.status}{r.message?' â€” '+r.message:''}{r.path?' Â· '+r.path:''}</div>)}</div>}
  {status?.repositories?.length>0&&<div className="panel tablePanel"><div className="panelHead"><div><h3>Repositories in Docker workspace</h3><p>These working copies are stored in the persistent mounted folder.</p></div><button className="secondary small" onClick={loadStatus}>Refresh</button></div><table><thead><tr><th>Repository</th><th>Branch</th><th>Local path</th></tr></thead><tbody>{status.repositories.map((r:any)=><tr key={r.full_name}><td>{r.full_name}</td><td>{r.branch}</td><td><code>{r.path}</code></td></tr>)}</tbody></table></div>}
  <div className="infoBox">Security: the GitHub token is read only by the backend from backend/.env. It is never sent to the browser or written into the saved Git remote URL. The repository workspace persists on the host through Docker Compose's ./data/repositories bind mount.</div>
 </div>
}

function Deployments(){
 const [rows,setRows]=useState<any[]>([]); const [open,setOpen]=useState(false); const [busy,setBusy]=useState(false); const [error,setError]=useState(''); const [form,setForm]=useState({name:'',repo_url:'',branch:'main',container_port:8000,host_port:8080});
 const load=()=>api('/api/deployments').then(setRows).catch(e=>setError(e.message)); useEffect(()=>{load()},[]);
 const create=async()=>{
  setError('');
  if(!form.name.trim()){setError('Enter a deployment name.');return;}
  let repo:URL;
  try{repo=new URL(form.repo_url.trim())}catch{setError('Enter a valid public GitHub HTTPS repository URL.');return;}
  if(repo.protocol!=='https:'||repo.hostname.toLowerCase()!=='github.com'||repo.pathname.split('/').filter(Boolean).length!==2){setError('Repository URL must look like https://github.com/owner/repository.');return;}
  if(!form.branch.trim()){setError('Enter a branch name.');return;}
  if(!Number.isInteger(form.container_port)||form.container_port<1||form.container_port>65535||!Number.isInteger(form.host_port)||form.host_port<1||form.host_port>65535){setError('Ports must be whole numbers between 1 and 65535.');return;}
  setBusy(true);
  try{await api('/api/deployments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(form)});setOpen(false);setForm({name:'',repo_url:'',branch:'main',container_port:8000,host_port:8080});await load()}
  catch(e:any){setError(e.message||'Deployment request failed.');}
  finally{setBusy(false)}
 };
 return <div><div className="pageIntro"><div><h2>Deployments</h2><p>Real Git checkout â†’ S3 artifact â†’ EC2 SSM â†’ Docker container verification.</p></div><button className="primary" onClick={()=>setOpen(true)}><Plus size={17}/> New deployment</button></div>
 {error&&<div className="infoBox">{error}</div>}<div className="panel tablePanel"><table><thead><tr><th>Deployment</th><th>Repository</th><th>Branch</th><th>Status</th><th>Progress</th><th>Details</th></tr></thead><tbody>{rows.length?rows.map(r=><tr key={r.id}><td><b>{r.name}</b><small>#{r.id}</small></td><td>{r.repo_url||'Not configured'}</td><td>{r.branch}</td><td><span className={'chip '+(r.status==='SUCCESS'?'green':r.status==='FAILED'?'red':'blue')}>{r.status}</span></td><td><div className="progress"><i style={{width:r.progress+'%'}}></i></div></td><td>{r.message}</td></tr>):<tr><td colSpan={6}><div className="empty">No deployments yet. Configure AWS EC2 and create a deployment.</div></td></tr>}</tbody></table></div>
 {open&&<Modal title="Deploy to AWS EC2" close={()=>!busy&&setOpen(false)}>{error&&<div className="infoBox" role="alert">{error}</div>}<label>Deployment name<input value={form.name} onChange={e=>setForm({...form,name:e.target.value})} placeholder="My application"/></label><label>GitHub HTTPS repository URL<input value={form.repo_url} onChange={e=>setForm({...form,repo_url:e.target.value})} placeholder="https://github.com/user/repo"/></label><label>Branch<input value={form.branch} onChange={e=>setForm({...form,branch:e.target.value})}/></label><label>Container port<input type="number" min="1" max="65535" value={form.container_port} onChange={e=>setForm({...form,container_port:Number(e.target.value)})}/></label><label>EC2 host port<input type="number" min="1" max="65535" value={form.host_port} onChange={e=>setForm({...form,host_port:Number(e.target.value)})}/></label><button type="button" className="primary full" onClick={()=>void create()} disabled={busy}>{busy?'Deploying and verifyingâ€¦':'Deploy to EC2'}</button></Modal>}</div>
}

function Incidents(){
 const [rows,setRows]=useState<any[]>([]); const [logs,setLogs]=useState(''); const [title,setTitle]=useState('Application incident'); const [error,setError]=useState(''); const [busy,setBusy]=useState(false); const [analysis,setAnalysis]=useState<any>(null); const [approvals,setApprovals]=useState<any[]>([]);
 const load=()=>Promise.all([api('/api/incidents'),api('/api/approvals')]).then(([a,b])=>{setRows(a);setApprovals(b)}).catch(e=>setError(e.message)); useEffect(()=>{load()},[]);
 const analyze=async()=>{if(!logs.trim()){setError('Paste real application or container logs first.');return;}setBusy(true);setError('');try{setAnalysis(await api('/api/incidents/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,logs})}));setLogs('');await load()}catch(e:any){setError(e.message)}finally{setBusy(false)}};
 const decide=async(id:number,decision:string)=>{try{await api('/api/approvals/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision})});await load()}catch(e:any){setError(e.message)}};
 return <div><div className="pageIntro"><div><h2>Incident assistance</h2><p>Submit actual logs for local diagnosis, retrieve runbook guidance and review approval requests.</p></div></div>
 <div className="panel" style={{padding:20,marginBottom:18}}><h3>Analyze application logs</h3><p>Paste a real error/log excerpt. DevPilot will match known signatures and explain uncertainty; this is local rule-based analysis, not an LLM diagnosis.</p><label>Incident title<input value={title} onChange={e=>setTitle(e.target.value)} /></label><label>Application / Docker logs<textarea rows={7} value={logs} onChange={e=>setLogs(e.target.value)} placeholder="Paste timestamped logs or a traceback hereâ€¦"/></label><button className="primary" onClick={analyze} disabled={busy}>{busy?'Analyzingâ€¦':'Analyze logs'}</button></div>
 {error&&<div className="infoBox">{error}</div>}{analysis&&<div className="resultCard"><span className="chip blue">{analysis.severity} severity</span><h3>{analysis.probable_cause}</h3><p>{analysis.recommendation}</p><small>Evidence saved as incident #{analysis.id}. {analysis.analysis_type}</small></div>}
 <div className="panel tablePanel"><div className="panelHead"><div><h3>Recorded incidents</h3><p>Only submitted evidence is shown.</p></div></div>{rows.length?<table><thead><tr><th>Incident</th><th>Severity</th><th>Status</th><th>Probable cause</th><th>Recommendation</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td>{r.title}</td><td>{r.severity}</td><td>{r.status}</td><td>{r.probable_cause}</td><td>{r.recommendation}</td></tr>)}</tbody></table>:<div className="empty">No recorded incidents yet.</div>}</div>
 <div className="panel tablePanel" style={{marginTop:18}}><div className="panelHead"><div><h3>Human approval queue</h3><p>Approving/rejecting records a decision only; it does not execute a command.</p></div></div>{approvals.length?<table><thead><tr><th>Request</th><th>Tool</th><th>Status</th><th>Decision</th></tr></thead><tbody>{approvals.map(a=><tr key={a.id}><td>{a.request}</td><td>{a.tool}</td><td>{a.status}</td><td>{a.status==='pending_approval'?<><button className="secondary small" onClick={()=>decide(a.id,'approve')}>Approve</button> <button className="secondary small" onClick={()=>decide(a.id,'reject')}>Reject</button></>:'â€”'}</td></tr>)}</tbody></table>:<div className="empty">No pending approval requests.</div>}</div></div>
}

function Storage(){
 const [items,setItems]=useState<any[]>([]); const [prefix,setPrefix]=useState(''); const [error,setError]=useState(''); const [message,setMessage]=useState(''); const [uploading,setUploading]=useState(false); const [modal,setModal]=useState<'file'|'folder'|null>(null); const [name,setName]=useState(''); const [content,setContent]=useState(''); const fileRef=useRef<HTMLInputElement>(null); const folderRef=useRef<HTMLInputElement>(null);
 const load=()=>api('/api/storage?prefix='+encodeURIComponent(prefix)).then(r=>{setItems(r.items);setError('')}).catch(e=>setError(e.message)); useEffect(load,[prefix]);
 const create=async()=>{if(modal==='folder') await api('/api/storage/create-folder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:(prefix?prefix+'/':'')+name})}); else await api('/api/storage/create-file',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:(prefix?prefix+'/':'')+name,content})});setModal(null);setName('');setContent('');load()};
 const upload = async (e:any, folder=false) => {
  const fs = Array.from(e.target.files || []) as File[];
  if (!fs.length) return;

  const input = e.target;
  setUploading(true);
  setError('');
  setMessage('');

  try {
   const fd = new FormData();
   fd.append('prefix', prefix);
   fs.forEach((f) => {
    fd.append('files', f);
    if (folder) fd.append('paths', (f as any).webkitRelativePath || f.name);
   });

   const endpoint = folder ? '/api/storage/upload-folder' : '/api/storage/upload';
   const result = await api(endpoint, {method:'POST', body:fd});
   setMessage(result.message || `${fs.length} file(s) uploaded successfully.`);
   await load();
  } catch (err:any) {
   setError(err.message || 'File upload failed.');
  } finally {
   setUploading(false);
   input.value = '';
  }
 };
 const del=async(k:string)=>{if(confirm('Delete this item?')){await api('/api/storage?key='+encodeURIComponent(k),{method:'DELETE'});load()}};
 return <div>{error&&<div className="infoBox" role="alert" style={{color:'#ff6b6b',marginBottom:12}}>Upload failed: {error}</div>}{message&&<div className="infoBox" role="status" style={{color:'#22c55e',marginBottom:12}}>{message}</div>}<div className="pageIntro"><div><h2>Cloud Storage</h2><p>Manage files, images and folders with local mode or real Amazon S3.</p></div><div className="buttonRow"><button className="secondary" onClick={()=>setModal('folder')}><Plus size={16}/> New folder</button><button className="primary" onClick={()=>setModal('file')}><Plus size={16}/> Create new</button><button className="uploadBtn" disabled={uploading} onClick={()=>fileRef.current?.click()}><Upload size={16}/> {uploading?'Uploading...':'Upload'}</button></div></div>
 <div className="storageDrop"
  onClick={()=>fileRef.current?.click()}
  onDragOver={(e)=>{e.preventDefault();e.stopPropagation();}}
  onDrop={(e)=>{e.preventDefault();e.stopPropagation();if(e.dataTransfer.files?.length){const transfer={target:{files:e.dataTransfer.files,value:''}};void upload(transfer,false);}}}><div className="dropIcon"><Upload/></div><div><b>Drop files here or browse</b><span>Images, PDFs, ZIPs, documents and more</span></div><button>Choose files</button></div>
 <input ref={fileRef} type="file" multiple hidden onChange={e=>upload(e)}/><input ref={folderRef} type="file" multiple hidden {...({webkitdirectory:""} as any)} onChange={e=>upload(e,true)}/>
 <div className="storageToolbar"><div className="breadcrumbs"><button onClick={()=>setPrefix('')}>Cloud</button>{prefix&&<><ChevronRight size={14}/><span>{prefix}</span></>}</div><button className="secondary small" onClick={()=>folderRef.current?.click()}><Folder size={15}/> Upload folder</button></div>
 <div className="fileGrid">{items.map((it,i)=><div className="fileCard" key={it.key+i} onDoubleClick={()=>it.is_folder&&setPrefix(it.key.replace(/\/$/,''))}><div className="fileIcon">{it.is_folder?<Folder/>:it.type?.startsWith('image/')?<ImageIcon/>:<FileText/>}</div><div className="fileName" title={it.name}>{it.name}</div><small>{it.is_folder?'Folder':formatBytes(it.size)}</small><div className="fileActions">{!it.is_folder&&<button onClick={()=>location.href=API+'/api/storage/download?key='+encodeURIComponent(it.key)}><Download size={15}/></button>}<button onClick={()=>del(it.key)}><Trash2 size={15}/></button></div></div>)}{!items.length&&<div className="empty storageEmpty">No objects here yet. Create something new or upload your first file.</div>}</div>
 {modal&&<Modal title={modal==='folder'?'Create folder':'Create new text file'} close={()=>setModal(null)}><label>Name<input value={name} onChange={e=>setName(e.target.value)} placeholder={modal==='folder'?'project-assets':'notes.txt'}/></label>{modal==='file'&&<label>Content<textarea value={content} onChange={e=>setContent(e.target.value)} placeholder="Write your file contentâ€¦"/></label>}<button className="primary full" onClick={create}>Create in cloud</button></Modal>}</div>
}

function Modal({title,close,children}:any){return <div className="overlay"><div className="modal"><button className="close" onClick={close}><X/></button><h2>{title}</h2>{children}</div></div>}
function formatBytes(n:number){if(!n)return '0 B';const u=['B','KB','MB','GB'];const i=Math.floor(Math.log(n)/Math.log(1024));return (n/Math.pow(1024,i)).toFixed(i?1:0)+' '+u[i]}

createRoot(document.getElementById('root')!).render(<App/>);

