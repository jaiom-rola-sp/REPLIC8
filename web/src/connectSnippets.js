// Copy-paste setup for the Connect screen. The token is always a placeholder: the real token is never put on screen.

export const TOKEN_PLACEHOLDER = 'YOUR_GATEWAY_TOKEN';
export const ADDRESS_PLACEHOLDER = 'https://YOUR-GATEWAY-ADDRESS';

// The address an agent should use. `base` is what the dashboard talks to; a path like "/gateway"
// goes through this site's own proxy, so on this site it lives under the page's origin.
export function gatewayAddress(base, origin) {
  const b = String(base || '').replace(/\/+$/, '');
  if (!b) return ADDRESS_PLACEHOLDER;
  return b.startsWith('/') ? `${origin}${b}` : b;
}

// An address that only works on the machine you are sitting at.
export const isLocalAddress = (address) => /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])([:/]|$)/.test(address);

// A tool and an example input to show in the curl call, taken from the first operation with inputs.
export function sampleCall(operations) {
  for (const op of operations || []) {
    const props = op?.input_schema?.properties;
    if (props && Object.keys(props).length) {
      const input = {};
      for (const [name, spec] of Object.entries(props)) {
        const t = Array.isArray(spec?.type) ? spec.type[0] : spec?.type;
        input[name] = t === 'integer' || t === 'number' ? 0 : t === 'boolean' ? true : 'VALUE';
      }
      return { tool: op.tool, input };
    }
  }
  return { tool: 'system.tool_name', input: {} };
}

export function snippets(address, sample) {
  const auth = `Authorization: Bearer ${TOKEN_PLACEHOLDER}`;
  const mcp = `${address}/mcp`;
  return {
    claude: `claude mcp add --transport http replic8 ${mcp} --header "${auth}"`,
    config: JSON.stringify({ mcpServers: { replic8: { type: 'http', url: mcp, headers: { Authorization: `Bearer ${TOKEN_PLACEHOLDER}` } } } }, null, 2),
    curlList: `curl ${address}/v1/operations \\\n  -H "${auth}"`,
    curlCall: `curl -X POST ${address}/v1/operations/${sample.tool} \\\n  -H "${auth}" \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify({ input: sample.input })}'`,
  };
}
