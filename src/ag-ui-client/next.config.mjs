/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  compress: true,
  swcMinify: true,
  async rewrites() {
    return [
      {
        source: '/agent-stream',
        destination: `${process.env.PYTHON_AGENT_URL || 'http://localhost:8000'}/copilotkit`,
      },
      {
        source: '/agent-stream/:path+',
        destination: `${process.env.PYTHON_AGENT_URL || 'http://localhost:8000'}/copilotkit/:path+`,
      },
      {
        source: '/agl-dashboard/:path*',
        destination: `${process.env.AGL_STORE_URL || 'http://localhost:8000/lightning-dashboard'}/:path*`, // Corrected to route to the Python Specialist static mount where Vite lives
      }
    ];
  },
};

export default nextConfig;
