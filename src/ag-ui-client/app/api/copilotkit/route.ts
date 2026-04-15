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
  let gatewayUrl = process.env.PYTHON_AGENT_URL;
  
  if (!gatewayUrl) {
    return new Response(
      JSON.stringify({ error: 'PYTHON_AGENT_URL environment variable is not set.' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }

  // Normalize URL: Ensure protocol is present to avoid fetch parsing errors
  if (!gatewayUrl.startsWith('http://') && !gatewayUrl.startsWith('https://')) {
    gatewayUrl = `https://${gatewayUrl}`;
  }

  try {
    // Append trailing slash to avoid internal FastAPI redirects
    const targetUrl = `${gatewayUrl}${gatewayUrl.endsWith('/') ? '' : '/'}copilotkit/`;
    
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': req.headers.get('Content-Type') || 'application/json',
      },
      body: await req.text(),
      redirect: 'manual', // We handle redirects manually to prevent internal URL leakage
    });

    // If the upstream tries to redirect us to an internal URL, we stop it here
    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get('Location');
      console.warn('[CopilotKit Proxy] Blocked internal redirect to:', location);
      return new Response(
        JSON.stringify({ error: 'Upstream redirected to internal URL.', location }),
        { status: 502, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Stream the SSE response body directly back to the CopilotKit client
    return new Response(response.body, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('Content-Type') || 'text/event-stream',
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
