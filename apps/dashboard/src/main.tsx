import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
const tasks = [{id:'DEMO-001',title:'Inspect repository checks',status:'Planned'},{id:'DEMO-002',title:'Review proposed changes',status:'Awaiting approval'}];
function App(){return <main><header><small>SUPERVISED DEVELOPMENT</small><h1>DevPilot</h1><p>Autonomous development with human approval for consequential actions.</p></header><section className="notice"><strong>Foundation mode</strong><p>Execution and GitHub writes are disabled. Tasks below are illustrative, not live data.</p></section><h2>Task preview</h2>{tasks.map(t=><article key={t.id}><div><small>{t.id}</small><h3>{t.title}</h3></div><span>{t.status}</span></article>)}<footer>CodeRabbit review required · No automatic merge or production deployment</footer></main>}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
