/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export for GitHub Pages deployment.
  // The app fetches presentation_snapshot.json at runtime from the same origin.
  output: 'export',
  trailingSlash: true,
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  images: {
    // Required for static export — no server-side image optimization.
    unoptimized: true,
  },
};
export default nextConfig;
