import { createMDX } from 'fumadocs-mdx/next';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactCompiler: true,
  // Self-contained server bundle: deploy without running a package install on the host.
  output: 'standalone',
};

const withMDX = createMDX();

export default withMDX(nextConfig);
