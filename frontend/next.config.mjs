/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingRoot: process.cwd(),
  output: 'export',
  images: {
    unoptimized: true,
  },
}

export default nextConfig
