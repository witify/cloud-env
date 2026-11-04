// Proves the stack works end to end: the video opens on the landing page, already signed in.
// Copy it to start a new scenario. Scenarios for a ticket go in .scratch/demo/, not in the repository.

const { record } = require('/opt/cloud-env/demo/recorder.cjs');

record('smoke', async (demo) => {
    await demo.step('Page de départ', async () => {
        await demo.pause(2500);
        await demo.screenshot('landing');
    });
}, { startPath: process.env.DEMO_LANDING_PATH || '/' });
