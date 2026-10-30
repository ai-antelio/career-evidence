import {test,expect} from '@playwright/test';
test('job review, all match states and claim approval safeguards (mock API)',async({page})=>{
 const fact={fact_id:'f1',value:'Built Python reporting tools.',source:'Built Python reporting tools.',provenance:'source_supported'};
 const opportunity:any={id:'o1',title:'Data Analyst',description:'Python is required. SQL is preferred. Kubernetes is required. Current license required.',status:'review',revision:0,processing:null,requirements:[{id:'r1',text:'Python is required.',source:'Python is required.',kind:'required',status:'pending',revision:0}],match:null,artifact:null};
 await page.route('http://localhost:8000/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname;let data:any={};
  if(path==='/me')data={email:'synthetic@example.test'};
  else if(['/documents','/proposals','/profile','/applications'].includes(path))data=[];
  else if(path==='/opportunities')data=req.method()==='POST'?{id:'o1'}:[{id:'o1',title:'Data Analyst',status:'review'}];
  else if(path==='/opportunities/o1')data=opportunity;
  else if(path==='/requirements/r1/review'){const body=req.postDataJSON();opportunity.requirements[0]={...opportunity.requirements[0],status:body.action,text:body.text||opportunity.requirements[0].text,kind:body.kind||'required',revision:opportunity.requirements[0].revision+1};}
  else if(path==='/opportunities/o1/match'){opportunity.match={id:'m1',status:'completed',items:['supported','partial','unknown','not_met'].map((status,i)=>({requirement_id:'r'+i,text:['Python','SQL','Kubernetes','Current license'][i],status,explanation:'Evidence-based assessment for '+status,evidence:i<2?[fact]:[]}))};}
  else if(path==='/opportunities/o1/draft'){opportunity.artifact={id:'a1',version:1,status:'draft',claims:[{text:fact.value,fact_ids:['f1']}],evidence:[fact],findings:[],stale:false};}
  else if(path==='/artifacts/a1/edit'){const b=req.postDataJSON();opportunity.artifact={...opportunity.artifact,version:opportunity.artifact.version+1,status:'draft',claims:b.claims,findings:b.claims[0]?.text===fact.value?[]:[{claim_index:0,message:'Claim is not supported by the confirmed fact.'}]};}
  else if(path==='/artifacts/a1/approve')opportunity.artifact.status='approved';
  await route.fulfill({json:data,headers:{'Access-Control-Allow-Origin':'http://localhost:3000','Access-Control-Allow-Credentials':'true'}});
 });
 await page.goto('/');await page.getByRole('button',{name:'Jobs & résumé drafts'}).click();await page.getByLabel('Role title').fill('Data Analyst');await page.getByLabel('Job description',{exact:true}).fill(opportunity.description);await page.getByRole('button',{name:'Extract requirements'}).click();
 const match=page.getByRole('button',{name:'Match confirmed facts'});await expect(match).toBeDisabled();
 await page.getByRole('button',{name:'Defer requirement'}).click();await expect(page.locator('.requirement-card .badge')).toContainText('deferred');await expect(match).toBeDisabled();
 await page.getByRole('button',{name:'Correct requirement'}).click();await page.getByLabel('Corrected requirement').fill('Python experience is required.');await page.getByRole('button',{name:'Save requirement'}).click();await expect(match).toBeEnabled();await page.getByRole('button',{name:'Defer requirement'}).click();await expect(page.locator('.requirement-card')).toContainText('Candidate correction. Original passage is shown for context');await page.getByRole('button',{name:'Accept requirement'}).click();await expect(page.locator('.requirement-card')).toContainText('Candidate correction. Original passage is shown for context');await match.click();
 for(const status of ['Supported','Partial','Unknown','Not met'])await expect(page.locator('.match-item .badge').filter({hasText:new RegExp('^'+status+'$')})).toBeVisible();
 await page.getByRole('button',{name:'Generate tailored résumé draft'}).click();await expect(page.getByLabel('Résumé claim 1')).toHaveValue(fact.value);await expect(page.locator('.artifact-editor .evidence-card summary')).toContainText(fact.value);
 await page.getByLabel('Résumé claim 1').fill('Managed 100 engineers.');await expect(page.getByRole('button',{name:'Approve this version'})).toBeDisabled();await page.getByRole('button',{name:'Save and validate edits'}).click();await expect(page.locator('.artifact-editor [role=alert]')).toContainText('Approval blocked');await expect(page.getByRole('button',{name:'Approve this version'})).toBeDisabled();
 await page.getByLabel('Résumé claim 1').fill(fact.value);await page.getByRole('button',{name:'Save and validate edits'}).click();await page.getByRole('button',{name:'Approve this version'}).click();await expect(page.getByText('Approved exact version 3. Saved to this application record.')).toBeVisible();
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'test-results/matching-mobile.png',fullPage:true});await expect(page.locator('body')).toHaveJSProperty('scrollWidth',390);
});
