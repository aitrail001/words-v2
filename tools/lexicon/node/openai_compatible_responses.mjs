import OpenAI from 'openai';
import readline from 'node:readline';

function textFormat(responseSchema) {
  if (!responseSchema) {
    return { type: 'json_object' };
  }
  return {
    type: 'json_schema',
    name: String(responseSchema.name),
    schema: responseSchema.schema,
    strict: responseSchema.strict !== false,
  };
}

function emitEnvelope(envelope) {
  process.stdout.write(`${JSON.stringify(envelope)}\n`);
}

async function handleRequest(rawLine) {
  let payload;
  try {
    payload = JSON.parse(rawLine);
  } catch {
    emitEnvelope({
      request_id: null,
      ok: false,
      error: 'Node OpenAI-compatible transport received invalid JSON payload',
    });
    return;
  }

  const {
    request_id: requestId = null,
    base_url: baseURL,
    api_key: apiKey,
    model,
    prompt,
    system_prompt: systemPrompt,
    reasoning_effort: reasoningEffort,
    response_schema: responseSchema,
  } = payload;

  if (!baseURL || !apiKey || !model || !prompt) {
    emitEnvelope({
      request_id: requestId,
      ok: false,
      error: 'Node OpenAI-compatible transport requires base_url, api_key, model, and prompt',
    });
    return;
  }
  const client = new OpenAI({
    apiKey,
    baseURL,
    defaultHeaders: { 'x-api-key': apiKey },
  });

  try {
    const input = [];
    if (systemPrompt) {
      input.push({
        role: 'system',
        content: [{ type: 'input_text', text: systemPrompt }],
      });
    }
    input.push({
      role: 'user',
      content: [{ type: 'input_text', text: prompt }],
    });

    const request = {
      model,
      input,
      text: { format: textFormat(responseSchema) },
    };
    if (reasoningEffort) {
      request.reasoning = { effort: reasoningEffort };
    }

    const response = await client.responses.create(request);
    emitEnvelope({ request_id: requestId, ok: true, response });
  } catch (error) {
    emitEnvelope({
      request_id: requestId,
      ok: false,
      error: error?.message || String(error),
    });
  }
}

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

for await (const line of rl) {
  if (!line.trim()) {
    continue;
  }
  await handleRequest(line);
}
