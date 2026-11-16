import assert from 'node:assert/strict';
import { chromium } from 'playwright';

// End-to-end UI journey against a REAL container stack with a test-only cert.
const host = 'https://chat.family.example.net';
const browser = await chromium.launch({headless: true});
const reports = [];
async function visit(label, viewport) {
  const context = await browser.newContext({
    viewport,
    ignoreHTTPSErrors: true,
    serviceWorkers: 'block',
    locale: 'de-DE'
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.setDefaultTimeout(12000);
  try {
    const response = await page.goto(host, {waitUntil: 'domcontentloaded'});
    assert(response && response.status() < 400, 'Could not load PWA');
    await page.getByRole('textbox', {name: 'Benutzername'}).fill('admin');
    await page.getByPlaceholder('Dein Passwort').fill('IntegrationStrongPassword12345');
    await page.getByRole('button', {name: 'Anmelden'}).click();
    await page.getByRole('button', {name: 'Familie'}).click();
    await page.getByRole('heading', {name: 'Deine Familie'}).waitFor();
    await page.locator('.member-card').filter({hasText:'Familienadmin'}).getByText('Familienadmin',{exact:true}).waitFor({state:'visible'});
    await page.getByRole('button', {name: 'Verwaltung'}).click();
    await page.getByRole('heading', {name: 'Familienverwaltung'}).waitFor();
    if (label === 'mobile') {
      await page.getByRole('button', {name: 'Mitglied anlegen'}).click();
      await page.getByLabel('Anzeigename').fill('E2E Mitglied');
      await page.getByLabel('Benutzername').last().fill('e2e_user');
      await page.getByLabel('Startpasswort (mindestens 12 Zeichen)').fill('StrongE2EPassword123');
      await page.getByRole('button', {name: 'Konto hinzufügen'}).click();
      await page.getByRole('table').getByText('E2E Mitglied',{exact:true}).waitFor({state:'visible'});
      await page.getByRole('button', {name: 'Familie'}).click();
      await page.locator('.member-card').filter({hasText:'E2E Mitglied'}).waitFor({state:'visible'});
      const member = page.locator('.member-card').filter({hasText: 'E2E Mitglied'});
      const extension = (await member.textContent()).match(/[12][0-9]{3}/);
      assert(extension, 'New member missing a 4-digit SIP extension');
      await member.getByRole('button', {name:'Anrufen'}).click();
      await page.getByRole('heading', {name: 'Anrufe'}).waitFor();
      await page.getByRole('textbox', {name: 'Rufnummer'}).waitFor();
      assert.equal(await page.getByRole('textbox', {name: 'Rufnummer'}).inputValue(), extension[0]);
    } else {
      await page.getByRole('button', {name: 'Anrufe'}).click();
      await page.getByRole('heading', {name: 'Anrufe'}).waitFor();
      await page.getByText('Deine Nebenstelle').first().waitFor();
    }
    await page.getByRole('button', {name: 'Nachrichten'}).click();
    await page.locator('converse-root').waitFor({state: 'attached'});
    // Webchat custom element and asset entry must be loadable, rather than just a built bundle.
    await page.waitForFunction(() => Boolean(window.converse), {timeout: 15000});
    assert.deepEqual(errors, [], 'Uncaught errors in ' + label + ' browser: ' + errors.join('; '));
    reports.push(label + ': auth, family, admin, dialing and XMPP entry loaded');
  } catch (error) {
    console.error(label + ' browser failed', error, 'URL:', page.url(), 'pageerrors:', errors);
    throw error;
  } finally {
    await context.close();
  }
}

try {
  await visit('mobile', {width:390, height:844});
  await visit('desktop', {width:1440, height:900});
  console.log('FamiCom browser smoke: ' + reports.join(' / '));
} finally {
  await browser.close();
}
