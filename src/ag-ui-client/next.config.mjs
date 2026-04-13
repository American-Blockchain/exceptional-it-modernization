/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/copilotkit/:path*',
        destination: `${process.env.PYTHON_AGENT_URL || 'http://localhost:8000'}/copilotkit/:path*`,
      },
    ];
  },
};

export default nextConfig;
