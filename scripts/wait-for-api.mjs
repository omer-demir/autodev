const apiBaseUrl = (process.env.WORKBENCH_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const deadline = Date.now() + 60_000;

async function waitForApi() {
  try {
    const response = await fetch(`${apiBaseUrl}/api/runtime-capabilities`, {
      signal: AbortSignal.timeout(2_000),
    });
    if (response.ok) {
      console.log(`API ready at ${apiBaseUrl}`);
      return;
    }
  } catch {
    // The API may still be importing modules or running startup hooks.
  }

  if (Date.now() >= deadline) {
    throw new Error(`API did not become ready at ${apiBaseUrl} within 60 seconds`);
  }
  await new Promise((resolve) => setTimeout(resolve, 250));
  return waitForApi();
}

await waitForApi();