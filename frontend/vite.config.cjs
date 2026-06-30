const { fileURLToPath, URL } = require("node:url");
const vue = require("@vitejs/plugin-vue");
const { defineConfig } = require("vite");

module.exports = defineConfig({
  plugins: [vue()],
  cacheDir: ".vite-cache",
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", `file://${__filename}`)),
    },
  },
  build: {
    rollupOptions: {
      maxParallelFileOps: 1,
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/vue") || id.includes("node_modules/pinia")) {
            return "vendor-vue";
          }
          if (id.includes("node_modules/element-plus") || id.includes("node_modules/@element-plus")) {
            return "vendor-element-plus";
          }
          if (id.includes("node_modules/axios")) {
            return "vendor-http";
          }
        },
      },
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
      },
    },
  },
});
