import {test,expect} from '@playwright/test';
test('saved exact approval, DOCX export, history and edit invalidation (mock API)',async({page})=>{
 const fact={fact_id:'f1',value:'Built Python reporting tools.',source:'Built Python reporting tools.',provenance:'source_supported'};
 let artifact:any={id:'a1',version:1,status:'draft',content_hash:'hash1',claims:[{text:fact.value,fact_ids:['f1']}],evidence:[fact],findings:[],stale:false};
 const versions:any[]=[structuredClone(artifact)];
 const application:any={id:'app1',title:'Data Analyst',opportunity_id:'o1',status:'draft',approval_valid:false,approval:null,approved_artifact:null,artifact_versions:[{id:'a1',version:1,status:'draft'}]};
 await page.route('http://localhost:8000/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname;let data:any={};
  if(path==='/me')data={email:'synthetic@example.test'};
  else if(['/documents','/proposals','/profile'].includes(path))data=[];
  else if(path==='/opportunities')data=[{id:'o1',title:'Data Analyst',status:'review'}];
  else if(path==='/opportunities/o1')data={id:'o1',title:'Data Analyst',description:'Python experience required.',status:'review',revision:0,processing:null,requirements:[],match:null,artifact,application:{id:'app1'}};
  else if(path==='/applications')data=[application];
  else if(path==='/applications/app1')data=application;
  else if(path.endsWith('/approve')){application.approval={id:'approval1',artifact_id:artifact.id,version:artifact.version,content_hash:artifact.content_hash,approved_at:1793232000,valid:true};artifact.status='approved';application.approved_artifact=structuredClone(artifact);application.status='ready';application.approval_valid=true;data={application_id:'app1'};}
  else if(path.endsWith('/export')){expect(req.postDataJSON()).toEqual({version:1,content_hash:'hash1'});await route.fulfill({body:'synthetic DOCX bytes',contentType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',headers:{'Access-Control-Allow-Origin':'http://localhost:3000','Access-Control-Allow-Credentials':'true'}});return;}
  else if(path.endsWith('/edit')){const body=req.postDataJSON();artifact={...artifact,id:'a2',version:2,status:'draft',content_hash:'hash2',claims:body.claims,findings:[{message:'Unsupported wording.'}]};application.approval_valid=false;application.approval.valid=false;application.approval.invalidated_reason='Artifact edited.';application.artifact_versions.push({id:'a2',version:2,status:'draft'});}
  else if(path==='/artifacts/a1')data=versions[0];
  await route.fulfill({json:data,headers:{'Access-Control-Allow-Origin':'http://localhost:3000','Access-Control-Allow-Credentials':'true'}});
 });
 await page.goto('/');await page.getByRole('button',{name:'Jobs & résumé drafts'}).click();await page.getByLabel('Saved opportunities').selectOption('o1');
 await expect(page.getByRole('button',{name:'Export approved résumé (.docx)'})).toHaveCount(0);
 await page.getByRole('button',{name:'Approve this version'}).click();await expect(page.locator('.application-record')).toContainText('Saved approval: version 1');await expect(page.locator('.application-record')).toContainText('2026');
 const downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Export approved résumé (.docx)'}).click();expect((await downloadEvent).suggestedFilename()).toBe('approved-resume-v1.docx');
 await page.getByText('Résumé version history',{exact:true}).click();await page.getByRole('button',{name:'Review version 1'}).click();await expect(page.locator('.history-preview')).toContainText(fact.value);await page.locator('.history-preview summary').click();await expect(page.locator('.history-preview')).toContainText('ORIGINAL SOURCE PASSAGE');
 await page.getByLabel('Résumé claim 1').fill('Managed 100 engineers.');await expect(page.locator('.artifact-editor')).toContainText('Unsaved edits are not approved');await page.getByRole('button',{name:'Save and validate edits'}).click();await expect(page.locator('.application-record')).toContainText('Approval is no longer valid');await expect(page.getByRole('button',{name:'Export approved résumé (.docx)'})).toHaveCount(0);await expect(page.getByRole('button',{name:'Approve this version'})).toBeDisabled();
});
