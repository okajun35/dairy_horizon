import {mkdir, readFile} from 'node:fs/promises';
import {chromium} from 'playwright';

const appUrl = 'http://127.0.0.1:8080/check?lactating_cows=60&lane_count=2&existing_fan_count=10&first_phase_fan_count=5&future_target_cow_count=45';
const root = new URL('.', import.meta.url).pathname;
const stillDir = `${root}captures/stills`;
const videoDir = `${root}captures/video`;
const viewport = {width: 1280, height: 1080};

await mkdir(stillDir, {recursive: true});
await mkdir(videoDir, {recursive: true});

const browser = await chromium.launch({
  executablePath: '/snap/bin/chromium',
  headless: true,
  args: ['--no-sandbox', '--disable-gpu'],
});

async function capture(number, name, prepare) {
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 1,
    recordVideo: {dir: videoDir, size: viewport},
  });
  const page = await context.newPage();
  await prepare(page);
  await page.waitForTimeout(700);
  await page.screenshot({path: `${stillDir}/scene-${number}-${name}.png`});
  await page.waitForTimeout(1100);
  const video = page.video();
  await context.close();
  await video.saveAs(`${videoDir}/scene-${number}-${name}.webm`);
}

async function appPage(page, target) {
  await page.goto(appUrl, {waitUntil: 'networkidle'});
  await page.locator(target).scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
}

await capture('01', 'title', async (page) => {
  const titleData = await readFile(`${root}title.png`, 'base64');
  await page.setContent(`<!doctype html><style>html,body{margin:0;background:#07171d;height:100%;display:grid;place-items:center}img{width:100%;height:100%;object-fit:contain}</style><img src="data:image/png;base64,${titleData}" alt="Dairy Horizon">`);
});

await capture('02', 'natural-input', async (page) => {
  await appPage(page, '#step-1');
  await page.locator('#farm-description').focus();
  await page.screenshot({path: `${stillDir}/scene-02-before-submit.png`});
  await page.locator('.chat-composer button[type="submit"]').click();
  await page.locator('.candidate-confirmation').waitFor();
  await page.locator('#step-1').evaluate((node) => {
    window.scrollTo({top: window.scrollY + node.getBoundingClientRect().top - 48, behavior: 'instant'});
  });
  await page.waitForTimeout(500);
  await page.screenshot({path: `${stillDir}/scene-02-candidate-confirmation.png`});
});

await capture('03', 'climate-outlook', async (page) => {
  await page.goto(appUrl, {waitUntil: 'networkidle'});
  await page.locator('.chat-composer button[type="submit"]').click();
  await page.locator('.candidate-confirmation').waitFor();
  await page.locator('#climate-outlook-heading').evaluate((node) => {
    window.scrollTo({top: window.scrollY + node.getBoundingClientRect().top - 72, behavior: 'instant'});
  });
  await page.waitForTimeout(500);
});

await capture('04', 'current-barn', async (page) => {
  await appPage(page, '#step-2');
  await page.locator('#current-barn-viewer .cow').last().click();
});

await capture('05', 'two-horizons', async (page) => {
  await appPage(page, '#step-3');
});

await capture('06', 'comparison-switch', async (page) => {
  await page.goto(appUrl, {waitUntil: 'networkidle'});
  await page.locator('[data-comparison-barn-heading]').evaluate((node) => {
    window.scrollTo({top: window.scrollY + node.getBoundingClientRect().top - 72, behavior: 'instant'});
  });
  await page.waitForTimeout(1200);
  await page.locator('[data-plan="first_phase"]').click();
  await page.waitForTimeout(900);
  await page.locator('[data-plan="full_coverage"]').click();
});

await capture('07', 'financial-screening', async (page) => {
  await appPage(page, '.financial-comparison');
  await page.locator('.financial-comparison').evaluate((node) => { node.parentElement.open = true; });
  await page.locator('.financial-comparison').scrollIntoViewIfNeeded();
});

await capture('08', 'next-step', async (page) => {
  await page.goto(appUrl, {waitUntil: 'networkidle'});
  await page.locator('#step-four-options-heading').evaluate((node) => {
    window.scrollTo({top: window.scrollY + node.getBoundingClientRect().top - 48, behavior: 'instant'});
  });
  for (const [key, name] of [['current', 'current'], ['first_phase', 'first-phase'], ['full_coverage', 'full-coverage']]) {
    await page.locator(`[data-next-step-plan="${key}"]`).click();
    await page.waitForTimeout(350);
    await page.screenshot({path: `${stillDir}/scene-08-next-step-${name}.png`});
  }
});

await capture('09', 'barn-background', async (page) => {
  await page.goto(appUrl, {waitUntil: 'networkidle'});
  await page.locator('[data-comparison-barn-heading]').evaluate((node) => {
    window.scrollTo({top: window.scrollY + node.getBoundingClientRect().top - 72, behavior: 'instant'});
  });
  for (const [key, name] of [['first_phase', 'first-phase'], ['full_coverage', 'full-coverage']]) {
    await page.locator(`[data-plan="${key}"]`).click();
    await page.waitForTimeout(350);
    await page.screenshot({path: `${stillDir}/scene-09-comparison-${name}.png`});
  }
});

await browser.close();
console.log(`Captured 9 stills in ${stillDir} and 9 WebM clips in ${videoDir}`);
