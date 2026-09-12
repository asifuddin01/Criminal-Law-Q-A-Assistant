/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Exported as static files and served by the API process itself. One process,
  // one port — which is what a Hugging Face Space gives you, and it removes the
  // cross-origin setup entirely: the page and the API share an origin.
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
