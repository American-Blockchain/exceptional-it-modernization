import { NextRequest } from 'next/server';

/**
 * Opaque Server-Side CopilotKit Proxy
 *
 * Architecture:
 *   Browser → Vercel /api/copilotkit [this file]
 *           → C# Orchestrator /copilotkit/ (GATEWAY_URL)
 *           → YARP → Python Specialist /copilotkit/
 *
 * GATEWAY_URL must point at the C# Orchestrator public FQDN.
 * YARP on the C# side handles routing /copilotkit/** → Python Specialist.
 *
 * All redirects are consumed server-side. The browser only ever sees a
 * clean 200 + SSE stream — internal Azure VNet FQDNs never leak.
 */

// The C# Orchestrator is the single public gateway. Its YARP config routes
// /copilotkit/** to the Python Specialist internally over the ACA VNet.
const GATEWAY_URL =
  process.env.GATEWAY_URL ||
  process.env.PYTHON_AGENT_URL ||
  'https://ca-csharp-orchestrator.ashytree-d52b6189.eastus.azurecontainerapps.io';

export async function POST(req: NextRequest) {
  const base = GATEWAY_URL.replace(/\/$/, '');

  // The C# YARP route is mounted at /copilotkit — append trailing slash
  // to prevent FastAPI from issuing a 307 redirect.
  const targetUrl = `${base}/copilotkit/`;

  console.log('[CopilotKit Proxy] Forwarding to:', targetUrl);

  try {
    const bodyText = await req.text();

    const response = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': req.headers.get('Content-Type') || 'application/json',
        // Forward the CopilotKit thread/run headers if present
        ...(req.headers.get('x-copilotkit-runtime-url') && {
          'x-copilotkit-runtime-url': req.headers.get('x-copilotkit-runtime-url')!,
        }),
      },
      body: bodyText,
      // Follow redirects server-side — the C# YARP may issue a 301 from
      // Dapr primary → VNet fallback. We consume it here, never the browser.
      redirect: 'follow',
    });

    const contentType = response.headers.get('Content-Type') || '';

    // Log non-200 responses for diagnostics
    if (!response.ok) {
      const body = await response.text();
      console.error(
        `[CopilotKit Proxy] Upstream error ${response.status}:`,
        body.slice(0, 500)
      );
      return new Response(
        JSON.stringify({ error: 'MAS Gateway returned an error.', status: response.status, detail: body.slice(0, 500) }),
        { status: response.status, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Stream SSE or return JSON — preserve whatever the upstream sends
    return new Response(response.body, {
      status: response.status,
      headers: {
        'Content-Type': contentType || 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        'X-Accel-Buffering': 'no', // Disable Nginx/Vercel edge buffering for SSE
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
