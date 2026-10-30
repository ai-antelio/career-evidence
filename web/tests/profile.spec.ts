import {test,expect} from '@playwright/test';
import path from 'node:path';
test('account, upload, provenance review, profile and isolated second account',async({page,browser})=>{
 const email=`alex.${Date.now()}@example.test`;
 await page.goto('/');await page.getByLabel('Email',{exact:true}).fill(email);await page.getByLabel('Password',{exact:true}).fill('synthetic-passphrase-2026');await page.getByRole('button',{name:'Create account',exact:true}).click();
 await expect(page.getByRole('heading',{name:'01 / Add your résumé'})).toBeVisible();
 await page.getByLabel('Résumé file').setInputFiles(path.resolve('../fixtures/invalid-resume.pdf'));await page.getByRole('button',{name:'Upload résumé',exact:true}).click();await expect(page.locator('.error[role=alert]')).toContainText('valid text-based');
 await page.getByLabel('Résumé file').setInputFiles(path.resolve('../fixtures/alex-morgan.docx'));await page.getByRole('button',{name:'Upload résumé',exact:true}).click();
 await expect(page.getByText('ready',{exact:true})).toBeVisible({timeout:20000});
 const cards=page.locator('section.review');await expect(cards.first()).toBeVisible();await cards.nth(0).getByRole('button',{name:'Accept original'}).click();await expect(cards.nth(0).locator('.badge')).toHaveText('accepted');
 await cards.nth(1).getByRole('button',{name:'Correct',exact:true}).click();await cards.nth(1).getByLabel('Your correction').fill('Senior Data Analyst | Cedar Labs | April 2021–August 2025');await cards.nth(1).getByRole('button',{name:'Save correction'}).click();await expect(cards.nth(1).locator('.badge')).toHaveText('corrected');await expect(cards.nth(1).getByText('Candidate correction; source shown for context only.')).toBeVisible();
 await cards.nth(2).getByRole('button',{name:'Reject',exact:true}).click();await expect(cards.nth(2).locator('.badge')).toHaveText('rejected');await cards.nth(3).getByRole('button',{name:'Defer',exact:true}).click();await expect(cards.nth(3).locator('.badge')).toHaveText('deferred');
 await page.getByRole('button',{name:'03 / Confirmed profile'}).click();await expect(page.locator('article')).toHaveCount(2);await expect(page.getByText(/original source does not substantiate/)).toBeVisible();
 await page.screenshot({path:'test-results/profile-desktop.png',fullPage:true});
 const context=await browser.newContext();const other=await context.newPage();await other.goto('/');await other.getByLabel('Email',{exact:true}).fill(`other.${Date.now()}@example.test`);await other.getByLabel('Password',{exact:true}).fill('synthetic-passphrase-2026');await other.getByRole('button',{name:'Create account',exact:true}).click();await expect(other.getByText('Your extracted passages will appear here once processing finishes.')).toBeVisible();await expect(other.locator('.document')).toHaveCount(0);await context.close();
 await page.getByRole('button',{name:'Sign out',exact:true}).click();await page.getByRole('button',{name:'Already have an account? Sign in'}).click();await page.getByLabel('Email',{exact:true}).fill(email);await page.getByLabel('Password',{exact:true}).fill('synthetic-passphrase-2026');await page.getByRole('button',{name:'Sign in',exact:true}).click();await expect(page.getByRole('heading',{name:'01 / Add your résumé'})).toBeVisible();
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'test-results/profile-mobile.png',fullPage:true});
});
