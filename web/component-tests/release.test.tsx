import React from 'react';
import {afterEach,describe,it,expect,vi} from 'vitest';
import {render,screen,waitFor,cleanup,fireEvent} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PracticeWorkspace from '../app/practice-workspace';
import AccountPrivacy from '../app/account-privacy';
import ApplicationTracking from '../app/application-tracking';
import ApplicationRecord from '../app/application-record';
const reply=(data:unknown,status=200)=>Promise.resolve({ok:status<400,json:async()=>data,blob:async()=>new Blob(['test'])} as Response);
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()});
const fact={fact_id:'f1',value:'Used Python for reporting',source:'Used Python for reporting',provenance:'source'};
const answer={id:'a1',question:'Relevant experience?',claims:[{text:fact.value,fact_ids:['f1']}],evidence:[fact],revision:1,status:'draft',findings:[],stale:false};
const practice={answers:[answer],sessions:[],workflows:[]};
describe('release component workflow with mocked HTTP',()=>{
 it('keeps answer approval blocked for unsaved edits and sends revision',async()=>{
  const calls:unknown[]=[];vi.stubGlobal('fetch',vi.fn((url:string,init?:RequestInit)=>{if(url.endsWith('/review')){calls.push(JSON.parse(String(init?.body)));return reply({ok:true})}return reply(practice)}));
  render(<PracticeWorkspace jobId="j1"/>);const text=await screen.findByLabelText('Answer claim 1');await userEvent.type(text,' and more');expect((screen.getByRole('button',{name:'Approve answer'}) as HTMLButtonElement).disabled).toBe(true);await userEvent.click(screen.getByRole('button',{name:'Save answer edits'}));await waitFor(()=>expect(calls.length).toBe(1));expect(calls[0]).toMatchObject({revision:1,action:'edited'});
 });
 it('renders feedback evidence and blocks stale practice response',async()=>{
  vi.stubGlobal('fetch',vi.fn(()=>reply({answers:[],workflows:[],sessions:[{id:'s1',status:'ready',questions:[{id:'q1',text:'Describe your Python work',requirement_ids:['r1'],fact_ids:['f1']}],evidence:[fact],submitted_materials:null,stale:true,responses:[{id:'r1',question_id:'q1',text:'I used Python',status:'completed',feedback:{observations:[{quote:'I used Python',message:'Describe the result',fact_ids:['f1']}],notice:'Coaching only',adapter:'deterministic'}}]}]})));
  render(<PracticeWorkspace jobId="j1"/>);await screen.findByText('Question 1: Describe your Python work');expect(screen.getAllByText('I used Python')).toHaveLength(2);expect((screen.getByRole('button',{name:'Save response and request feedback'}) as HTMLButtonElement).disabled).toBe(true);expect(screen.getByText('Coaching only')).toBeTruthy();
 });
 it('requires exact typed deletion confirmation and calls callback only after success',async()=>{
  const deleted=vi.fn(),calls:unknown[]=[];vi.stubGlobal('fetch',vi.fn((url:string,init?:RequestInit)=>{if(url.endsWith('/delete')){calls.push(JSON.parse(String(init?.body)));return reply({status:'queued'})}return reply([])}));
  render(<AccountPrivacy onDeleted={deleted}/>);await userEvent.click(screen.getByRole('button',{name:'Review account deletion'}));const button=screen.getByRole('button',{name:'Permanently delete my account'}) as HTMLButtonElement;expect(button.disabled).toBe(true);await userEvent.type(screen.getByLabelText('Type DELETE MY ACCOUNT to confirm'),'DELETE MY ACCOUNT');expect(button.disabled).toBe(false);await userEvent.click(button);await waitFor(()=>expect(deleted).toHaveBeenCalledOnce());expect(calls[0]).toEqual({confirmation:'DELETE MY ACCOUNT'});
 });
 it('preserves unsaved tracking input when server reports conflicting revision',async()=>{
  const t={application_id:'app1',revision:2,status:'saved',notes:'Original',next_action:'',follow_up_at:null,submitted_snapshot:null,history:[]};vi.stubGlobal('fetch',vi.fn((url:string,init?:RequestInit)=>url.endsWith('/applications')?reply([{id:'app1',title:'Analyst',status:'saved'}]):init?.method==='POST'?reply({detail:'Application changed; refresh'},409):reply(t)));
  render(<ApplicationTracking/>);await userEvent.selectOptions(await screen.findByLabelText('Application to manage'),'app1');const notes=await screen.findByLabelText('Application notes');await userEvent.clear(notes);await userEvent.type(notes,'My unsaved notes');await userEvent.click(screen.getByRole('button',{name:'Save application update'}));await screen.findByRole('alert');expect((notes as HTMLTextAreaElement).value).toBe('My unsaved notes');expect(screen.getByRole('button',{name:'Reload latest saved state'})).toBeTruthy();
 });
 it('requests PDF only for exact valid approved version and hash',async()=>{
  const artifact={id:'ar1',version:3,status:'approved',claims:[{text:fact.value,fact_ids:['f1']}],evidence:[fact],findings:[],stale:false,content_hash:'hash1'};
  const calls:unknown[]=[];vi.stubGlobal('fetch',vi.fn((url:string,init?:RequestInit)=>{if(url.endsWith('/export')){calls.push(JSON.parse(String(init?.body)));return reply({})}return reply({id:'app1',title:'Analyst',status:'ready',approval:{id:'ap1',artifact_id:'ar1',version:3,content_hash:'hash1',approved_at:100,valid:true},approval_valid:true,approved_artifact:artifact,artifact_versions:[]})}));
  URL.createObjectURL=vi.fn(()=> 'blob:test');URL.revokeObjectURL=vi.fn();vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
  render(<ApplicationRecord applicationId="app1" jobId="j1" revision="3"/>);await userEvent.click(await screen.findByRole('button',{name:'Export approved résumé (.pdf)'}));await waitFor(()=>expect(calls).toEqual([{version:3,content_hash:'hash1',format:'pdf'}]));
 });
 it('ignores a save response after navigating to another application',async()=>{
  let resolveSave:(value:Response)=>void=()=>{};const pending=new Promise<Response>(resolve=>{resolveSave=resolve});
  const tracking=(id:string)=>({application_id:id,revision:0,status:'saved',notes:id==='app1'?'First notes':'Second notes',next_action:'',follow_up_at:null,submitted_snapshot:null,history:[]});
  vi.stubGlobal('fetch',vi.fn((url:string,init?:RequestInit)=>url.endsWith('/applications')?reply([{id:'app1',title:'First role',status:'saved'},{id:'app2',title:'Second role',status:'saved'}]):init?.method==='POST'?pending:reply(tracking(url.includes('app1')?'app1':'app2'))));
  render(<ApplicationTracking/>);await userEvent.selectOptions(await screen.findByLabelText('Application to manage'),'app1');await screen.findByDisplayValue('First notes');await userEvent.click(screen.getByRole('button',{name:'Save application update'}));await userEvent.selectOptions(screen.getByLabelText('Application to manage'),'app2');await screen.findByDisplayValue('Second notes');resolveSave({ok:true,json:async()=>({...tracking('app1'),revision:1,notes:'Old completed save'})} as Response);await new Promise(r=>setTimeout(r,20));expect(screen.queryByDisplayValue('Old completed save')).toBeNull();expect(screen.getByDisplayValue('Second notes')).toBeTruthy();
 });

 it('requires explicit review of OpenAI interview preparation before responses',async()=>{
  let approved=false;const calls:unknown[]=[];
  vi.stubGlobal('fetch',vi.fn((url:string,init?:RequestInit)=>{if(url.endsWith('/interviews/s1/review')){calls.push(JSON.parse(String(init?.body)));approved=true;return reply({status:'ready'})}return reply({answers:[],workflows:[],sessions:[{id:'s1',status:approved?'ready':'needs_review',generation:{adapter:'openai',model:'configured-model'},questions:[{id:'q1',text:'Describe your Python work',requirement_ids:['r1'],fact_ids:['f1']}],evidence:[fact],submitted_materials:null,stale:false,responses:[]}]})}));
  render(<PracticeWorkspace jobId="j1"/>);await screen.findByText('OpenAI-backed output');expect((screen.getByRole('button',{name:'Save response and request feedback'}) as HTMLButtonElement).disabled).toBe(true);await userEvent.click(screen.getByRole('button',{name:'Approve interview preparation'}));await waitFor(()=>expect((screen.getByRole('button',{name:'Save response and request feedback'}) as HTMLButtonElement).disabled).toBe(false));expect(calls).toEqual([{action:'approved'}]);
 });
 it('labels deterministic output and blocks answer approval while evidence revalidation is pending',async()=>{
  vi.stubGlobal('fetch',vi.fn(()=>reply({answers:[{...answer,status:'draft',generation:{adapter:'deterministic'},validation_pending:true}],sessions:[],workflows:[{id:'w1',kind:'answer_validate',status:'running',error:''}]})));
  render(<PracticeWorkspace jobId="j1"/>);await screen.findByText('Deterministic test/development output');expect(screen.getByText('This item was produced by the test adapter, not a live OpenAI call.')).toBeTruthy();expect((screen.getByRole('button',{name:'Approve answer'}) as HTMLButtonElement).disabled).toBe(true);expect(screen.queryByRole('button',{name:'Copy reviewed answer'})).toBeNull();
 });

});
