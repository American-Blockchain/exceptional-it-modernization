import { NextRequest } from 'next/server';

/**
 * Opaque Server-Side CopilotKit Proxy
 *
 * Why this exists:
 * next.config.mjs rewrites are transparent — when YARP forwards FastAPI's
 * internal 301/307 redirect, Next.js passes it straight through to the browser.
 * The browser then attempts to resolve the internal Azure VNet FQDN
 * (ca-python-specialist.internal.*), which is unreachable and causes a
 * fatal CORS block + net::ERR_FAILED.
 *
 * This route runs on the Vercel Node.js server. All redirects are
 * consumed server-side. The browser only ever sees a clean 200 + SSE stream.
 */
export async function POST(req: NextRequest) {
  const gatewayUrl = process.env.PYTHON_AGENT_URL;

  if (!gatewayUrl) {
    return new Response(
      JSON.stringify({ error: 'PYTHON_AGENT_URL environment variable is not set.' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }

  try {
    const upstream = await fetch(`${gatewayUrl}/copilotkit`, {
      method: 'POST',
      headers: {
        'Content-Type': req.headers.get('Content-Type') || 'application/json',
      },
      body: await req.text(),
      // Node.js fetch follows 30x redirects automatically and internally —
      // the browser never sees the internal Azure VNet address.
    });

    // Stream the SSE response body directly back to the CopilotKit client
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        'Content-Type': upstream.headers.get('Content-Type') || 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('[CopilotKit Proxy Error]:', message);
    return new Response(
      JSON.stringify({ error: 'Failed to connect to MAS Gateway.', detail: message }),
      { status: 502, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
