/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  // GitHub Pages serves at /smartlist/ — all assets must be prefixed.
  basePath: '/smartlist',
  assetPrefix: '/smartlist',
  trailingSlash: true,
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  images: {
    unoptimized: true,
  },
};
export default nextConfig;
