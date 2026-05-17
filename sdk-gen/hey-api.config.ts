import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: 'sdk-gen/openapi.json',
  output: { path: 'sdks/typescript', format: 'prettier' },
  plugins: ['@hey-api/client-fetch', '@hey-api/typescript', '@hey-api/sdk'],
});
