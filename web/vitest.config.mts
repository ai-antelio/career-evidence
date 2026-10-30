import {defineConfig} from 'vitest/config';
export default defineConfig({test:{environment:'jsdom',include:['component-tests/**/*.test.tsx'],globals:true}});
