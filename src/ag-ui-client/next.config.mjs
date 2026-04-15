/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  compress: true,
  swcMinify: true,
  async rewrites() {
    return [
      {
        source: '/agl-dashboard/:path*',
        destination: `${process.env.AGL_STORE_URL || 'http://localhost:8000/lightning-dashboard'}/:path*`,
      }
    ];
  },
};

export default nextConfig;
