import OpenAI from 'openai';

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

const raw = await readStdin();
if (!raw.trim()) {
  fail('Node OpenAI-compatible transport received empty stdin payload');
}

let payload;
try {
  payload = JSON.parse(raw);
} catch {
  fail('Node OpenAI-compatible transport received invalid JSON payload');
}

const { base_url: baseURL, api_key: apiKey, model, prompt, system_prompt: systemPrompt } = payload;
if (!baseURL || !apiKey || !model || !prompt) {
  fail('Node OpenAI-compatible transport requires base_url, api_key, model, and prompt');
}

const client = new OpenAI({
  apiKey,
  baseURL,
  defaultHeaders: { 'x-api-key': apiKey },
});

const combinedPrompt = systemPrompt ? `${systemPrompt}\n\n${prompt}` : prompt;

try {
  const resp = await client.responses.create({
    model,
    input: [
      {
        role: 'user',
        content: [{ type: 'input_text', text: combinedPrompt }],
      },
    ],
  });
  process.stdout.write(JSON.stringify(resp));
} catch (error) {
  const message = error?.message || String(error);
  fail(message);
}
