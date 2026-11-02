// Proves the stack works end to end: sign in and show the landing page.
// Copy it to start a new scenario. Scenarios for a ticket go in .scratch/demo/, not in the repository.

const { record } = require('/opt/cloud-env/demo/recorder.cjs');

record('smoke', async (demo) => {
    await demo.step('Connexion', async () => {
        await demo.signIn();
    });

    await demo.step('Page de départ', async () => {
        await demo.pause(2500);
        await demo.screenshot('landing');
    });
});
