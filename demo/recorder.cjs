// Records a scripted walk through the site. Run it through `demo-video <scenario.cjs>`.
// The browser only records while the scenario runs, so model thinking time never lands in the video.

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const OUTPUT_DIRECTORY = process.env.DEMO_OUTPUT_DIR || path.resolve('.scratch/demo');
const LOGIN_PATH = process.env.DEMO_LOGIN_PATH || '/login';
const VIEWPORT = { width: 1440, height: 900 };
const CURSOR_TRAVEL_MS = 450;
const AFTER_ACTION_PAUSE_MS = 900;
const CAPTION_PAUSE_MS = 1400;

// A visible cursor and a caption bar: a headless recording shows neither by default.
const OVERLAY_SCRIPT = () => {
    window.addEventListener('DOMContentLoaded', () => {
        const cursor = document.createElement('div');
        cursor.id = '__demo_cursor';
        cursor.style.cssText = 'position:fixed;z-index:2147483647;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;background:rgba(239,68,68,.55);border:2px solid #fff;box-shadow:0 0 6px rgba(0,0,0,.5);pointer-events:none;transition:transform .12s;left:50%;top:50%';
        document.documentElement.appendChild(cursor);

        const caption = document.createElement('div');
        caption.id = '__demo_caption';
        // Bottom left: the app's notifications appear in the bottom centre.
        caption.style.cssText = 'position:fixed;z-index:2147483646;left:24px;bottom:24px;max-width:45%;padding:10px 18px;border-radius:8px;background:rgba(17,24,39,.9);color:#fff;font:600 18px/1.3 system-ui,sans-serif;pointer-events:none;display:none';
        document.documentElement.appendChild(caption);

        const stored = sessionStorage.getItem('__demo_caption');
        if (stored) {
            caption.textContent = stored;
            caption.style.display = 'block';
        }

        document.addEventListener('mousemove', (event) => {
            cursor.style.left = `${event.clientX}px`;
            cursor.style.top = `${event.clientY}px`;
        }, true);
        document.addEventListener('mousedown', () => { cursor.style.transform = 'scale(.6)'; }, true);
        document.addEventListener('mouseup', () => { cursor.style.transform = 'scale(1)'; }, true);
    });
};

// PHP and the browser are cold in a new VM: the first load takes about ten seconds. This
// visit is not recorded, so the video does not open on a spinner.
async function warmUp(browser, siteUrl) {
    const context = await browser.newContext();
    const page = await context.newPage();

    await page.goto(`${siteUrl}${LOGIN_PATH}`, { waitUntil: 'networkidle', timeout: 60000 }).catch(() => {});
    await context.close();
}

async function record(name, scenario, options = {}) {
    const siteUrl = options.siteUrl || process.env.DEMO_SITE_URL || 'http://localhost';
    const rawDirectory = path.join(OUTPUT_DIRECTORY, 'raw', name);

    fs.rmSync(rawDirectory, { recursive: true, force: true });
    fs.mkdirSync(rawDirectory, { recursive: true });

    const browser = await chromium.launch();
    await warmUp(browser, siteUrl);

    const context = await browser.newContext({
        viewport: options.viewport || VIEWPORT,
        recordVideo: { dir: rawDirectory, size: options.viewport || VIEWPORT },
        locale: options.locale || 'fr-CA',
    });
    await context.addInitScript(OVERLAY_SCRIPT);

    const page = await context.newPage();
    const problems = { consoleErrors: [], failedRequests: [], steps: [] };

    page.on('console', (message) => {
        if (message.type() === 'error') {
            problems.consoleErrors.push(message.text().slice(0, 400));
        }
    });
    page.on('pageerror', (error) => problems.consoleErrors.push(String(error).slice(0, 400)));
    page.on('response', (response) => {
        if (response.status() >= 400) {
            problems.failedRequests.push(`${response.status()} ${response.url().slice(0, 200)}`);
        }
    });
    page.on('requestfailed', (request) => {
        problems.failedRequests.push(`${request.failure()?.errorText} ${request.url().slice(0, 200)}`);
    });

    const demo = {
        page,
        siteUrl,

        async caption(text) {
            await page.evaluate((value) => {
                try {
                    sessionStorage.setItem('__demo_caption', value);
                } catch {
                    // about:blank has no storage: the caption still shows, for this page only.
                }
                const element = document.getElementById('__demo_caption');
                if (element) {
                    element.textContent = value;
                    element.style.display = value ? 'block' : 'none';
                }
            }, text);
            await page.waitForTimeout(CAPTION_PAUSE_MS);
        },

        // One step of the story: a caption, then its actions. A failed step stops the recording.
        async step(title, actions) {
            await demo.caption(title);
            try {
                await actions();
                problems.steps.push({ title, status: 'ok' });
            } catch (error) {
                problems.steps.push({ title, status: 'failed', error: String(error).slice(0, 600) });
                throw error;
            }
        },

        async goto(pathOrUrl) {
            const url = pathOrUrl.startsWith('http') ? pathOrUrl : `${siteUrl}${pathOrUrl}`;
            await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
            await page.waitForTimeout(AFTER_ACTION_PAUSE_MS);
        },

        async moveTo(locator) {
            const target = typeof locator === 'string' ? page.locator(locator).first() : locator;
            await target.scrollIntoViewIfNeeded();
            const box = await target.boundingBox();
            if (box) {
                await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 18 });
                await page.waitForTimeout(CURSOR_TRAVEL_MS);
            }
            return target;
        },

        async click(locator) {
            const target = await demo.moveTo(locator);
            await target.click();
            await page.waitForLoadState('networkidle').catch(() => {});
            await page.waitForTimeout(AFTER_ACTION_PAUSE_MS);
        },

        // The local login form comes pre-filled, so this replaces the value and never appends.
        async type(locator, text) {
            const target = await demo.moveTo(locator);
            await target.click();
            await target.fill('');
            await target.pressSequentially(String(text), { delay: 35 });
            await page.waitForTimeout(AFTER_ACTION_PAUSE_MS / 2);
        },

        async pause(milliseconds = 2000) {
            await page.waitForTimeout(milliseconds);
        },

        async signIn(email = process.env.DEMO_LOGIN_EMAIL, password = process.env.DEMO_LOGIN_PASSWORD, landingPath = process.env.DEMO_LANDING_PATH || '/') {
            await page.context().clearCookies();
            await demo.goto(LOGIN_PATH);
            await page.locator('input:not([type=checkbox]):not([type=password])').first().fill(email);
            await page.locator('input[type=password]').first().fill(password);
            await demo.click('button[type=submit]');
            await page.waitForURL((url) => !url.pathname.startsWith(LOGIN_PATH), { timeout: 30000 });
            await demo.goto(landingPath);
        },

        // A sensitive change answers 428 and opens this dialog. The 428 in the report is expected.
        async confirmPassword(password = process.env.DEMO_LOGIN_PASSWORD) {
            await page.locator('[role=dialog] input[type=password], input[type=password]:focus').first().fill(password);
            await demo.click('button:has-text("Oui"), button:has-text("Yes")');
        },

        async screenshot(fileName) {
            await page.screenshot({ path: path.join(OUTPUT_DIRECTORY, `${name}-${fileName}.png`) });
        },
    };

    let scenarioError = null;

    try {
        await page.goto(`${siteUrl}${LOGIN_PATH}`, { waitUntil: 'networkidle', timeout: 60000 });
        await scenario(demo);
        await demo.pause(1500);
    } catch (error) {
        scenarioError = error;
    }

    const video = page.video();
    await context.close();
    await browser.close();

    const rawPath = await video.path();
    const report = { name, rawPath, ...problems, error: scenarioError ? String(scenarioError).slice(0, 800) : null };

    fs.writeFileSync(path.join(OUTPUT_DIRECTORY, `${name}.json`), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));

    if (scenarioError) {
        process.exitCode = 1;
    }
}

module.exports = { record };
